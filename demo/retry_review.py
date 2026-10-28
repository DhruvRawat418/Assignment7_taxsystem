"""Explicitly retry a failed reviewer without clearing saved cases or guards."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.agents.audit import input_fingerprint
from src.integration.adapters import prepare_packet
from src.integration.graph import build_graph
from src.integration.state import active_extractions, context_fingerprint


async def retry_review(root, case_id, workers):
    database = Path(root) / "workflow_sessions.db"
    if not database.is_file():
        raise ValueError("The workflow database does not exist.")
    config = {"configurable": {"thread_id": case_id}}
    async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_graph(workers, checkpointer=saver)
        snapshot = await graph.aget_state(config)
        state = snapshot.values
        if (snapshot.next or any(task.interrupts for task in snapshot.tasks)
                or state.get("status") != "blocked"
                or state.get("issues") != [{"code": "provider_failed", "owner": "adversarial"}]):
            raise ValueError("This command only retries a saved adversarial provider failure.")
        fingerprint = context_fingerprint(state)
        if (state.get("computed_for") != fingerprint or state.get("audit_for") != fingerprint
                or state.get("computation_result", {}).get("status") != "completed"):
            raise ValueError("The computation is stale or incomplete; it cannot be reused.")
        packet = prepare_packet(state["intake_snapshot"], state["rules_output"], active_extractions(state))
        packet["computation_result"] = state["computation_result"]
        audit_packet = {key: packet[key] for key in
                        ("computation_input", "computation_result", "extractions", "audit_source_bindings")}
        audit = state.get("audit_result", {})
        if (audit.get("status") != "passed" or audit.get("issues") != []
                or audit.get("input_fingerprint") != input_fingerprint(audit_packet)):
            raise ValueError("The audit no longer matches this return; retry was refused.")
        # A fresh invocation resumes at the supervisor. All saved history,
        # fingerprints, revision, and loop counters remain in place.
        await graph.ainvoke({"status": "running", "next_stage": "adversarial",
                            "issues": [], "adversarial_result": {}}, config)
        after = await graph.aget_state(config)
        pending = [item.value for task in after.tasks for item in task.interrupts]
        return {"status": "paused_for_human_review" if pending else after.values["status"],
                "revision": after.values.get("revision"),
                "issues": after.values.get("issues", []), "pending_reviews": pending,
                "stages": [event["stage"] for event in after.values.get("events", [])]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    args = parser.parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        parser.exit(2, "OPENAI_API_KEY is missing in this terminal.\n")
    from src.agents.adversarial import make_adversarial_provider
    from src.agents.openai_transport import openai_review_call
    from src.agents.eligibility import make_eligibility_node
    from src.agents.intake_contract import make_intake_provider, sqlite_sessions
    from src.integration.contracts import Providers
    root = Path(__file__).resolve().parents[1]
    workers = Providers(intake=make_intake_provider(sqlite_sessions(str(root / "intake_sessions.db"))),
                        rules=make_eligibility_node(),
                        adversarial=make_adversarial_provider(openai_review_call))
    try:
        result = asyncio.run(retry_review(root, args.case_id, workers))
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
