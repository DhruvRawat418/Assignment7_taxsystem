"""Integration CLI. Default blocks; demos are labelled and never file anything."""
import argparse
import asyncio
import json
from src.integration.contracts import IntegrationError, Providers
from src.integration.graph import build_graph
from src.integration.state import new_case


def summary(state):
    computation, audit = state.get("computation_result", {}), state.get("audit_result", {})
    return dict(status=state["status"], mode=state["mode"], revision=state["revision"],
                issues=state.get("issues", []), supervisor_hops=state.get("hops", 0),
                computation_tool_calls=len(computation.get("tool_calls", [])),
                audit_status=audit.get("status", "not_run"), audit_checks=len(audit.get("rechecks", [])),
                draft_only=True, filed=False, production_ready=False,
                form_renderer="not_implemented", dashboard="not_implemented")


async def execute(args):
    if args.readiness:
        return dict(providers=Providers().readiness(), production_ready=False,
                    note="Configuration report, not a runtime health check."), 0
    initial = new_case(args.case_id)
    if args.synthetic_demo or args.synthetic_hitl_demo:
        from src.integration.demo import run_synthetic
        state, labels = await run_synthetic(args.case_id, human_review=args.synthetic_hitl_demo)
        output = summary(state) | labels
    else:
        state = await build_graph().ainvoke(initial, {"configurable": {"thread_id": args.case_id}})
        output = summary(state)
    return output, 0 if state["status"] == "ready_for_human_review" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--readiness", action="store_true")
    group.add_argument("--synthetic-demo", action="store_true")
    group.add_argument("--synthetic-hitl-demo", action="store_true")
    parser.add_argument("--case-id", default="integration-demo")
    args = parser.parse_args()
    try:
        output, code = asyncio.run(execute(args))
    except IntegrationError as error:
        output, code = dict(status="blocked", issues=[dict(code=error.code, owner=error.owner)],
                            production_ready=False, filed=False), 2
    except Exception:
        output, code = dict(status="blocked", issues=[dict(code="runtime_unavailable", owner="orchestrator")],
                            production_ready=False, filed=False), 2
    print(json.dumps(output, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
