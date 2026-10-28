"""Task allocation policy used by the shared supervisor.

Inputs are the CaseState already checked at the Intake/provider boundaries.
This module assigns work; it never extracts facts, interprets tax rules, performs
arithmetic, or changes a provider's result. The supervisor still owns routing.
"""
from dataclasses import dataclass

from src.integration.state import context_fingerprint


@dataclass(frozen=True)
class ExtractionPlan:
    pending: tuple[dict, ...]
    completed: tuple[str, ...]
    needs_input: tuple[str, ...]

    @property
    def ready_for_rules(self):
        return not self.pending and not self.needs_input


def plan_extraction(documents, extractions):
    """One task per active upload, reusing prior results without retrying them.

    A failed upload requires Intake attention and a new upload ID. Historical
    uploads remain in the reducer but cannot block or enter the active batch.
    An empty inventory is allowed: the existing Rules adapter still checks that
    every monetary input has an explicit source; no zero is invented here.
    """
    pending, completed, needs_input = [], [], []
    for document in documents:
        document_id = document["document_id"]
        if document_id not in extractions:
            pending.append(dict(document))
        else:
            result = extractions[document_id]
            target = completed if result["status"] == "extracted" and not result["issues"] else needs_input
            target.append(document_id)
    return ExtractionPlan(tuple(pending), tuple(completed), tuple(needs_input))


def task_board(state):
    """Return the current revision's task/dependency view for UI and handoff.

    `done` describes available evidence at this revision, not a filed return.
    Only the supervisor's selected stage is ready; other agents cannot use this
    view to skip routing, source checks, clearance, or the final audit gate.
    The board contains task IDs and issue codes, never document paths or amounts.
    """
    plan = plan_extraction(state["documents"], state["extractions"])
    stage, status = state["next_stage"], state["status"]
    current = context_fingerprint(state)
    computed = bool(state["computation_result"]) and state["computed_for"] == current
    audited = computed and state["audit_result"].get("status") == "passed" and state["audit_for"] == current
    reviewed = audited and state["adversarial_result"] == {"findings": []}
    tasks = []

    def add(task_id, owner, depends_on, done, selected):
        task_status = "done" if done else "waiting"
        if status == "running" and selected:
            task_status = "ready"
        elif status == "needs_input" and owner == "intake":
            task_status = "needs_input"
        elif status in ("blocked", "stopped") and not done:
            task_status = status
        tasks.append(dict(task_id=task_id, owner=owner, depends_on=depends_on, status=task_status))

    add("intake", "intake", [], bool(state["intake_snapshot"]), stage == "intake")
    pending_ids = {d["document_id"] for d in plan.pending}
    extraction_ids = []
    for document in state["documents"]:
        document_id = document["document_id"]
        task_id = "extract:" + document_id
        extraction_ids.append(task_id)
        add(task_id, "document_extraction", ["intake"], document_id in plan.completed,
            stage == "extract" and document_id in pending_ids)
        if document_id in plan.needs_input and status not in ("blocked", "stopped"):
            tasks[-1]["status"] = "needs_input"
            tasks[-1]["request_owner"] = "intake"
    add("aggregate", "orchestrator", extraction_ids or ["intake"],
        bool(state["intake_snapshot"]) and plan.ready_for_rules,
        stage == "extract" and not plan.pending and bool(plan.needs_input))
    add("rules", "rules", ["aggregate"], plan.ready_for_rules and bool(state["rules_output"]), stage == "rules")
    add("compute", "computation", ["rules"], computed, stage == "compute")
    add("audit", "audit", ["compute"], audited, stage == "audit")
    add("adversarial", "adversarial", ["audit"], reviewed, stage == "adversarial")
    add("final_review", "human", ["adversarial"], False, False)
    if status == "ready_for_human_review":
        tasks[-1]["status"] = "ready"
    if stage == "human":
        add("clarification", "human", [], False, True)
        tasks[-1]["return_to"] = state["pending_owner"]
    return dict(revision=state["revision"], case_status=status, tasks=tasks,
                issue_codes=[issue["code"] for issue in state["issues"]])
