"""Attributed document edits with checkpoint checks and review invalidation.

Saving never invokes a model. Original files and source records remain historical.
Local single-operator service; it is not a multi-process transaction coordinator.
"""
from copy import deepcopy
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from demo.run_intake import build_graph as build_interview
from src.agents.intake import FORM_QUESTIONS, DELETE, provenance
from src.agents.intake_guards import validate_staff_metadata
from src.agents.intake_parser import RuleParser
from src.agents.intake_contract import not_ready_reason
from src.agents.eligibility import make_eligibility_node
from src.integration.case_service import CaseService, case_activity, _pending
from src.integration.contracts import Providers
from src.integration.graph import build_graph
from src.integration.state import invalidate
from src.integration.task_division import task_board

FORM_CHOICES = ('W-2','SSA-1099','1099-INT','1099-DIV','1099-R','1099-NEC','1099-B','1099-MISC')
DOCUMENT_UPDATE_CODES = {'documents_changed','document_answers_required'}
LIMIT_CODES = {'hop_limit','review_limit','no_progress','document_history_limit'}


def _token(snapshot):
    return snapshot.config['configurable']['checkpoint_id'] if snapshot and snapshot.values else None


def _readonly(source, workflow=None):
    if source.values.get('intake_paused') or any(p.get('type')=='escalation' for p in _pending(source)):
        return 'Resolve or stop the current interview review before editing documents.'
    if workflow and workflow.values:
        state=workflow.values;pending=_pending(workflow)
        if state.get('status')=='stopped':return 'Stopped cases retain their documents and cannot be edited.'
        if any(i.get('code') in LIMIT_CODES for i in state.get('issues',[])):
            return 'A workflow limit was reached. Inspect this case before changing it.'
        if pending:
            if len(pending)!=1 or pending[0].get('owner')!='rules':
                return 'Resolve this agent review before editing documents.'
        elif state.get('status') not in ('ready_for_human_review','needs_input','blocked'):
            return 'Checks are running. Wait for them to finish before editing documents.'
    return None


def _staged(values,code):
    result=dict(status='needs_input',next_stage='intake',pending_owner='intake',
                issues=[{'code':code,'owner':'intake'}],rules_output={},human_response={},**invalidate())
    result['task_plan']=task_board({**values,**result})
    return result


class DocumentService(CaseService):
    def document_context(self,case_id):
        config=self._config(case_id)
        with self._interview() as graph:source=graph.get_state(config)
        if not source.values:raise ValueError('The saved interview was not found.')
        workflow=None
        if self.workflow_db.is_file():
            with SqliteSaver.from_conn_string(str(self.workflow_db)) as saver:
                workflow=build_graph(checkpointer=saver).get_state(config)
        answers=source.values.get('answers',{})
        return dict(case_id=case_id,intake_token=_token(source),workflow_token=_token(workflow),
            forms=deepcopy(answers.get('documents',{}).get('value') or []),
            checks_ready=not_ready_reason(source.values) is None and not source.next,
            paths=deepcopy(answers.get('w2_files',{}).get('value') or []),
            read_only_reason=_readonly(source,workflow),interview_complete=bool(source.values.get('intake_complete')))

    async def save_documents(self,case_id,intake_token,workflow_token,*,forms,files=None,staff,reason,confirmed):
        staff,reason=validate_staff_metadata(staff,reason)
        if confirmed is not True:raise ValueError('Confirm the document correction and synthetic assignment data before saving.')
        if (not isinstance(forms,list) or len(forms)>16
                or any(not isinstance(f,str) or not f.strip() or len(f)>100 for f in forms)
                or len(set(forms))!=len(forms)):
            raise ValueError('Choose a valid list of tax forms.')
        if files and 'W-2' not in forms:raise ValueError('Include W-2 in the tax-form list when uploading W-2 images.')
        decoded=self._prepare_images(files) if files else None
        config=self._config(case_id)
        with case_activity(self.root,case_id):
            return await self._save_documents(config,intake_token,workflow_token,forms,decoded,staff,reason)

    async def _save_documents(self,config,intake_token,workflow_token,forms,decoded,staff,reason):
        case_id=config['configurable']['thread_id']
        async with AsyncSqliteSaver.from_conn_string(str(self.intake_db)) as intake_saver:
            interview=build_interview(RuleParser(),intake_saver)
            async with AsyncSqliteSaver.from_conn_string(str(self.workflow_db)) as workflow_saver:
                workflow=build_graph(Providers(rules=make_eligibility_node()),checkpointer=workflow_saver)
                source=await interview.aget_state(config);before=await workflow.aget_state(config)
                if not source.values or _token(source)!=intake_token or _token(before)!=workflow_token:
                    raise ValueError('This case changed. Refresh the documents page before saving.')
                if reason_blocked:=_readonly(source,before):raise ValueError(reason_blocked)
                answers=source.values.get('answers',{});old_forms=answers.get('documents',{}).get('value') or []
                if any(f not in FORM_CHOICES and f not in old_forms for f in forms):
                    raise ValueError('Select a listed tax form; existing unrecognized entries can be retained or explicitly corrected.')
                if set(forms)==set(old_forms) and decoded is None:
                    raise ValueError('Change the tax forms or attach replacement W-2 images before saving.')
                # Revoke export BEFORE changing the source. A failed second database
                # write must leave an inspection-needed case, never an old approval.
                if before.values:
                    if _pending(before):
                        pending=_pending(before)[0]
                        await workflow.ainvoke(Command(resume={'action':'resolve','owner':'rules',
                            'revision':pending['revision'],'response':{'reload_intake':True}}),
                            config,interrupt_before=['intake'])
                        current=await workflow.aget_state(config)
                        if current.values.get('status')!='running' or _pending(current):
                            raise ValueError('The review could not be resumed safely; inspect the case before continuing.')
                    current=await workflow.aget_state(config)
                    await workflow.aupdate_state(config,_staged(current.values,'documents_changed'),as_node='supervisor')
                who='SilverFile staff: '+staff
                updates={};history=[]
                def record(field,value):
                    previous=deepcopy(answers.get(field))
                    item=provenance(value,'Recorded staff document correction',who)
                    updates[field]=item
                    history.append(dict(field=field,old=previous.get('value') if previous else None,
                        new=deepcopy(value),previous_record=previous,staff=staff,reason=reason,at=item['entered_at']))
                def remove(field):
                    if field in answers:
                        previous=deepcopy(answers[field]);updates[field]=DELETE
                        stamp=provenance(None,'Retired with document correction',who)
                        history.append(dict(field=field,old=previous.get('value'),new=None,previous_record=previous,
                                            staff=staff,reason=reason,at=stamp['entered_at']))
                record('documents',list(forms))
                for form,questions in FORM_QUESTIONS.items():
                    if form not in forms:
                        for field,*_ in questions:remove(field)
                if 'W-2' not in forms:remove('w2_files')
                elif decoded is not None:
                    try:record('w2_files',self._save_images(case_id,decoded))
                    except (OSError,ValueError) as error:
                        raise ValueError('The images could not be saved. The previous review is revoked; inspect the case before retrying.') from error
                try:
                    order=deepcopy(source.values.get('answered_order',[]))
                    history[0]['previous_answered_order']=deepcopy(order)
                    if before.values or source.values.get('intake_complete'):
                        # Backtracking may revisit newly collected document answers,
                        # never delete an already completed interview's other facts.
                        order=[]
                    else:
                        order=[field for field in order if updates.get(field)!=DELETE]
                    await interview.aupdate_state(config,dict(answers=updates,answer_history=history,
                        answered_order=order,intake_complete=False,
                        preface='Documents saved. Your earlier answers are kept; continue the interview.'),as_node='intake')
                    await interview.ainvoke(None,config)
                    updated=await interview.aget_state(config)
                    if before.values:
                        current=await workflow.aget_state(config)
                        code='documents_changed' if updated.values.get('intake_complete') else 'document_answers_required'
                        await workflow.aupdate_state(config,_staged(current.values,code),as_node='supervisor')
                except Exception as error:
                    raise ValueError('Document changes could not finish. The previous review is revoked; inspect the saved interview before retrying.') from error
        return self.document_context(case_id)
