"""Browser adapters for the existing saved interview and team workflow.

No taxpayer questions, tax rules or calculations are reimplemented here.
Credentials and model callables never enter a checkpoint. Local single-operator use.
"""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import hashlib
import re
import sqlite3
import threading
import uuid

from PIL import Image, UnidentifiedImageError
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from demo.run_intake import build_graph as build_interview
from src.agents.intake import initial_intake_state, summarize, provenance, DELETE, QUESTIONS
from src.agents.intake_guards import scan_ssns, validate_staff_metadata
from src.agents.intake_contract import make_intake_provider, not_ready_reason, to_packet
from src.agents.intake_parser import RuleParser
from src.agents.eligibility import make_eligibility_node
from src.agents.adversarial import make_adversarial_provider
from src.integration.contracts import Providers
from src.integration.graph import build_graph
from src.integration.state import new_case

_LOCK = threading.RLock()
_ACTIVE_RUNS = set()
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@contextmanager
def case_activity(root,case_id):
    """Reserve one case across asynchronous checks or staff mutations."""
    key=(str(Path(root).resolve()),validate_case_id(case_id))
    with _LOCK:
        if key in _ACTIVE_RUNS:
            raise ValueError('A case update or checks are already running. Refresh before trying again.')
        _ACTIVE_RUNS.add(key)
    try:
        yield
    finally:
        with _LOCK:_ACTIVE_RUNS.discard(key)


def validate_case_id(case_id):
    if (not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', case_id)
            or scan_ssns(case_id).real_ssn_found or scan_ssns(case_id).test_ssns):
        raise ValueError('Use a case ID of 1–80 letters, digits, hyphens or underscores; do not use an SSN.')
    return case_id


def _pending(snapshot):
    return [i.value for task in snapshot.tasks for i in task.interrupts]


def _summary(snapshot):
    state = snapshot.values
    pending = _pending(snapshot)
    return dict(status='paused_for_human_review' if pending else state.get('status', 'not_started'),
        revision=state.get('revision', 0), issues=state.get('issues', []), pending_reviews=pending,
        stages=[e['stage'] for e in state.get('events', [])])


class CaseService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.intake_db = self.root / 'intake_sessions.db'
        self.workflow_db = self.root / 'workflow_sessions.db'

    @contextmanager
    def _interview(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(self.intake_db)) as saver:
            yield build_interview(RuleParser(), saver)

    @staticmethod
    def _config(case_id):
        return {'configurable': {'thread_id': validate_case_id(case_id)}}

    def _ensure_idle(self,case_id):
        if (str(self.root),validate_case_id(case_id)) in _ACTIVE_RUNS:
            raise ValueError('A case update or checks are already running. Refresh before trying again.')

    def workflow_state(self, case_id):
        if not self.workflow_db.is_file():
            return {}
        with SqliteSaver.from_conn_string(str(self.workflow_db)) as saver:
            return build_graph(checkpointer=saver).get_state(self._config(case_id)).values

    def create(self, case_id):
        config = self._config(case_id)
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            if graph.get_state(config).values or self.workflow_state(case_id):
                raise ValueError('This case ID already exists. Resume the saved interview or choose a new ID.')
            graph.invoke(initial_intake_state(), config)
        return self.view(case_id)

    def view(self, case_id):
        with self._interview() as graph:
            snapshot = graph.get_state(self._config(case_id))
        if not snapshot.values:
            raise ValueError('This saved interview could not be found.')
        state = snapshot.values
        pending = _pending(snapshot)
        prompt = pending[0] if pending else None
        uncertain=[key for key,record in state.get('answers',{}).items() if record.get('status')=='unsure']
        if prompt and prompt.get('type') == 'escalation':
            status = 'intake_needs_review'
        elif state.get('intake_paused'):
            status = 'intake_stopped'
        elif state.get('intake_complete'):
            status = 'intake_needs_review' if uncertain else 'ready_for_checks'
            if not uncertain and not_ready_reason(state) in ('intake_missing_direct_amounts', 'intake_missing_scope_answers') and not self.workflow_state(case_id):
                status = 'interview_update_required'
        else:
            status = 'interview_in_progress'
        return dict(case_id=case_id, status=status, pending=deepcopy(prompt),
            token=snapshot.config['configurable']['checkpoint_id'],
            answer_count=len(state.get('answers', {})), summary=summarize(state),
            preface=state.get('preface', ''), uncertain_fields=uncertain)

    def list(self):
        if not self.intake_db.is_file():
            return []
        with sqlite3.connect(self.intake_db) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='checkpoints'").fetchone():
                return []
            ids = [row[0] for row in conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns='' ORDER BY thread_id")]
        views=[]
        for case_id in ids:
            try:validate_case_id(case_id)
            except ValueError:continue
            views.append(self.view(case_id))
        return views

    def continue_remaining(self, case_id, token):
        """Explicitly resume a pre-extension interview, preserving its answers."""
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            snap = graph.get_state(self._config(case_id))
            if (not snap.values or snap.config['configurable']['checkpoint_id'] != token
                    or _pending(snap) or self.workflow_state(case_id)
                    or not_ready_reason(snap.values) not in ('intake_missing_direct_amounts', 'intake_missing_scope_answers')):
                raise ValueError('Only an unchanged interview with missing questions can continue here.')
            graph.update_state(self._config(case_id), {'intake_complete': False}, as_node='intake')
            graph.invoke(None, self._config(case_id))
        return self.view(case_id)

    def _checked_snapshot(self, graph, case_id, token, field=None):
        snapshot = graph.get_state(self._config(case_id))
        if not snapshot.values or snapshot.config['configurable']['checkpoint_id'] != token:
            raise ValueError('This interview changed. Refresh and answer the current question.')
        pending = _pending(snapshot)
        if len(pending) != 1 or pending[0].get('type') != 'ask_user':
            raise ValueError('This interview is not waiting for a taxpayer answer.')
        if field and pending[0].get('field') != field:
            raise ValueError('This action does not match the current question.')
        workflow = self.workflow_state(case_id)
        document_questions = (workflow.get('status') == 'needs_input' and workflow.get('issues') ==
            [{'code': 'document_answers_required', 'owner': 'intake'}])
        if workflow and not document_questions:
            raise ValueError('The case has already entered workflow review. Use its supported review actions.')
        return snapshot

    def answer(self, case_id, token, reply):
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 4000:
            raise ValueError('Enter an answer of at most 4,000 characters.')
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            snapshot = self._checked_snapshot(graph, case_id, token)
            field = _pending(snapshot)[0]['field']
            if field == 'w2_files':
                raise ValueError('Upload the W-2 image instead of entering a file path.')
            # Resume payloads are checkpointed BEFORE the Intake node runs.
            # Reject/redact here as well as in Intake so raw identifiers never
            # enter the checkpointer's pending-write table.
            scan = scan_ssns(reply)
            if scan.real_ssn_found:
                view = self.view(case_id)
                view['notice'] = 'Do not enter a real Social Security number. It was not saved. Please answer the same question again.'
                return view
            if field != 'dependent_ssn' and scan.test_ssns:
                reply = scan.redacted_text
            graph.invoke(Command(resume=reply), self._config(case_id))
        return self.view(case_id)

    def _prepare_images(self, files):
        if not isinstance(files, list) or not 1 <= len(files) <= 10:
            raise ValueError('Upload between 1 and 10 synthetic W-2 images.')
        decoded = []
        total = 0
        for _, raw in files:
            if not isinstance(raw, bytes) or not raw or len(raw) > MAX_UPLOAD_BYTES:
                raise ValueError('Each image must be nonempty and no larger than 20 MiB.')
            total += len(raw)
            if total > 50 * 1024 * 1024:
                raise ValueError('The combined upload must be no larger than 50 MiB.')
            try:
                with Image.open(BytesIO(raw)) as image:
                    extension = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}.get(image.format)
                    if not extension or image.width * image.height > 20_000_000 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError
                    image.verify()
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
                raise ValueError('Use a valid single-frame PNG, JPEG or WEBP image, up to 20 million pixels.') from None
            decoded.append((raw, extension))
        return decoded

    def _save_images(self, case_id, decoded):
        base = self.root / 'uploads'
        if base.is_symlink() or not base.resolve().is_relative_to(self.root):
            raise ValueError('The upload destination is invalid.')
        case_dir = base / validate_case_id(case_id)
        if case_dir.is_symlink() or not case_dir.resolve().is_relative_to(self.root):
            raise ValueError('The upload destination is invalid.')
        directory = base / validate_case_id(case_id) / uuid.uuid4().hex
        directory.mkdir(parents=True, mode=0o700)
        if not directory.resolve().is_relative_to(base.resolve()):
            raise ValueError('The upload destination is invalid.')
        paths = []
        for raw, extension in decoded:
            path = directory / (hashlib.sha256(raw).hexdigest() + extension)
            if path.is_symlink():
                raise ValueError('The upload destination is invalid.')
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(raw)
                path.chmod(0o600)
            if str(path) not in paths:
                paths.append(str(path))
        return paths

    def upload_w2(self, case_id, token, files):
        decoded = self._prepare_images(files)
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            self._checked_snapshot(graph, case_id, token, 'w2_files')
            paths = self._save_images(case_id, decoded)
            graph.invoke(Command(resume={'uploaded_w2_paths':paths}), self._config(case_id))
        return self.view(case_id)

    def reopen_uncertain(self, case_id, token, field):
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            snap=graph.get_state(self._config(case_id))
            record=snap.values.get('answers',{}).get(field)
            if (not snap.values or snap.config['configurable']['checkpoint_id']!=token
                    or self.workflow_state(case_id) or _pending(snap) or not snap.values.get('intake_complete')
                    or field not in QUESTIONS or not record or record.get('status')!='unsure'):
                raise ValueError('Only a completed interview with that uncertain answer can revisit it here.')
            graph.update_state(self._config(case_id),dict(answers={field:DELETE},intake_complete=False,
                answer_history=[dict(field=field,previous_record=deepcopy(record),reason='Revisit uncertain answer')]),as_node='intake')
            graph.invoke(None,self._config(case_id))
        return self.view(case_id)

    def resolve_intake(self, case_id, token, *, staff, reason, stop=True):
        staff, reason = validate_staff_metadata(staff, reason)
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            snapshot = graph.get_state(self._config(case_id))
            if not snapshot.values or snapshot.config['configurable']['checkpoint_id'] != token:
                raise ValueError('The interview changed. Refresh before resolving it.')
            pending = _pending(snapshot)
            if len(pending) != 1 or pending[0].get('type') != 'escalation':
                raise ValueError('This interview has no pending staff review.')
            # No arbitrary fact overrides; the original agent retains all scope signals.
            graph.invoke(Command(resume=dict(staff=staff.strip(), resolution=reason.strip(),
                                            resume=not stop, updates={})), self._config(case_id))
        return self.view(case_id)

    def replace_w2(self, case_id, token, files, *, staff, reason):
        decoded = self._prepare_images(files)
        staff, reason = validate_staff_metadata(staff, reason)
        with _LOCK, self._interview() as graph:
            self._ensure_idle(case_id)
            snapshot = graph.get_state(self._config(case_id))
            if not snapshot.values or snapshot.config['configurable']['checkpoint_id'] != token:
                raise ValueError('The interview changed. Refresh before replacing documents.')
            workflow = self.workflow_state(case_id)
            if (workflow.get('status') != 'needs_input'
                    or not any(i.get('code')=='document_requires_attention' for i in workflow.get('issues', []))
                    or not snapshot.values.get('intake_complete') or _pending(snapshot)):
                raise ValueError('Only a completed case awaiting replacement documents can use this action.')
            old = snapshot.values['answers'].get('w2_files')
            if not old: raise ValueError('This case did not supply W-2 documents.')
            paths = self._save_images(case_id, decoded)
            record = provenance(paths, 'Uploaded replacement synthetic documents', 'SilverFile staff: '+staff.strip())
            graph.update_state(self._config(case_id), dict(answers={'w2_files':record},
                answer_history=[dict(field='w2_files',previous_record=deepcopy(old),staff=staff.strip(),
                                     reason=reason.strip(),at=record['entered_at'])]), as_node='intake')
        return self.view(case_id)

    async def run_checks(self,case_id,model_call):
        with case_activity(self.root,case_id):
            return await self._run_checks(case_id,model_call)

    async def _run_checks(self, case_id, model_call):
        if model_call is None:
            raise ValueError('Connect your OpenAI key in Model settings before running AI review.')
        config = self._config(case_id)
        async with AsyncSqliteSaver.from_conn_string(str(self.intake_db)) as intake_saver:
            interview = build_interview(RuleParser(), intake_saver)
            source = await interview.aget_state(config)
            if (not_ready_reason(source.values) is not None or source.next
                    or any(r.get('status')=='unsure' for r in source.values.get('answers',{}).values())):
                raise ValueError('Complete the taxpayer interview and resolve its pending questions first.')

            async def saved_intake(state):
                saved = await interview.aget_state(self._config(state['case_id']))
                return make_intake_provider(lambda _: saved.values)(state)

            p = Providers(intake=saved_intake, rules=make_eligibility_node(),
                          adversarial=make_adversarial_provider(model_call))
            async with AsyncSqliteSaver.from_conn_string(str(self.workflow_db)) as saver:
                graph = build_graph(p, checkpointer=saver)
                before = await graph.aget_state(config)
                if not before.values:
                    await graph.ainvoke(new_case(case_id), config)
                elif before.values.get('status') == 'ready_for_human_review':
                    return _summary(before)
                elif _pending(before):
                    raise ValueError('Open this case in Review & actions to resolve its pending staff request.')
                elif (before.values.get('status') == 'blocked' and before.values.get('issues') ==
                        [{'code':'provider_failed','owner':'adversarial'}]):
                    if sum(e.get('stage')=='adversarial' for e in before.values.get('events', [])) >= 3:
                        raise ValueError('The model-review attempt limit was reached. Inspect this case before continuing.')
                    from demo.retry_review import retry_review
                    return await retry_review(self.root, case_id, p)
                elif before.values.get('status') == 'needs_input':
                    if to_packet(source.values) == before.values.get('intake_snapshot'):
                        raise ValueError('Provide new information or upload replacement documents before rerunning checks.')
                    await graph.ainvoke(dict(status='running',next_stage='intake',human_response={}),config)
                else:
                    raise ValueError('This saved case cannot be restarted here. Inspect its current review or stop state.')
                return _summary(await graph.aget_state(config))
