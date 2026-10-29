"""Local, single-operator CLI: correct a saved scope answer, then recheck it.

Copy into silverfile-app/demo/. This is not an authenticated staff dashboard.
"""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from demo.run_intake import build_graph as build_interview
from src.agents.intake import SCOPE_FIELDS
from src.agents.intake_contract import make_intake_provider, not_ready_reason, to_packet
from src.agents.intake_corrections import prepare_scope_correction
from src.agents.intake_parser import RuleParser
from src.integration.graph import build_graph


async def resolve_scope(root, case_id, field, expected_old, new_value, staff, reason, workers):
    """workers supplies real agents in the CLI, explicit doubles in tests."""
    root = Path(root)
    intake_db = root / "intake_sessions.db"
    workflow_db = root / "workflow_sessions.db"
    if not intake_db.is_file() or not workflow_db.is_file():
        raise ValueError("Both saved interview and workflow databases must exist.")
    config = {"configurable": {"thread_id": case_id}}

    async with AsyncSqliteSaver.from_conn_string(str(intake_db)) as intake_saver:
        interview = build_interview(RuleParser(), intake_saver)

        async def saved_intake(state):
            saved = await interview.aget_state(
                {"configurable": {"thread_id": state["case_id"]}}
            )
            return make_intake_provider(lambda _: saved.values)(state)

        async with AsyncSqliteSaver.from_conn_string(str(workflow_db)) as saver:
            graph = build_graph(replace(workers, intake=saved_intake), checkpointer=saver)
            before = await graph.aget_state(config)
            interrupts = [i.value for task in before.tasks for i in task.interrupts]
            if len(interrupts) != 1 or interrupts[0].get("owner") != "rules":
                raise ValueError("Case must be paused for exactly one Rules-owned review.")
            pending = interrupts[0]
            if before.values.get("status") != "running":
                raise ValueError("Stopped or completed cases cannot be corrected here.")

            snapshot = await interview.aget_state(config)
            session = snapshot.values
            if not_ready_reason(session) is not None or snapshot.next:
                raise ValueError("The intake interview must be complete and not paused.")

            # Detect intervening edits; do not silently reload unrelated changes.
            original_packet = before.values["intake_snapshot"]
            if to_packet(session) != original_packet:
                raise ValueError("Intake changed since this pause; reconcile it before retrying.")

            update = prepare_scope_correction(
                session, field=field, expected_old=expected_old, new_value=new_value,
                staff=staff, reason=reason,
            )
            # Intake reducers merge the answer and append history.
            await interview.aupdate_state(config, update, as_node="intake")

            # The saved answer is durable before the workflow resumes. Never
            # insert an approval or tax result into graph state.
            try:
                await graph.ainvoke(Command(resume={
                    "action": "resolve", "owner": pending["owner"],
                    "revision": pending["revision"],
                    "response": {"reload_intake": True},
                }), config)
            except Exception:
                return {
                    "status": "correction_saved_resume_failed",
                    "message": "Correction history is saved. Inspect the workflow before retrying; do not repeat the edit.",
                }

            after = await graph.aget_state(config)
            pending_after = [i.value for task in after.tasks for i in task.interrupts]
            return {
                "status": "paused_for_human_review" if pending_after else after.values["status"],
                "corrected_field": field,
                "revision": after.values.get("revision"),
                "issues": after.values.get("issues", []),
                "pending_reviews": pending_after,
                "stages": [e["stage"] for e in after.values.get("events", [])],
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("--field", choices=SCOPE_FIELDS, required=True)
    parser.add_argument("--old", choices=["yes", "no"], required=True)
    parser.add_argument("--new", choices=["yes", "no"], required=True)
    parser.add_argument("--staff", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    from src.agents.adversarial import make_adversarial_provider
    from src.agents.eligibility import make_eligibility_node
    from src.agents.openai_transport import openai_review_call
    from src.integration.contracts import Providers

    workers = Providers(
        rules=make_eligibility_node(),
        adversarial=make_adversarial_provider(openai_review_call),
    )
    try:
        result = asyncio.run(resolve_scope(
            Path(__file__).resolve().parents[1], args.case_id, args.field,
            args.old == "yes", args.new == "yes", args.staff, args.reason, workers,
        ))
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
