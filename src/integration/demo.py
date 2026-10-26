"""Explicitly synthetic graph smoke; four providers are fixtures, NOT agents.

Computation and deterministic Audit use the actual local MCP server. No OCR,
LLM, external service or taxpayer is involved. These bundled test fixtures must
never be used as real Rules clearance or evidence.
"""
from langgraph.types import Command
from src.integration.contracts import ProviderResult, Providers
from src.integration.graph import build_graph
from src.integration.state import new_case


async def run_synthetic(case_id="synthetic-demo", *, human_review=False):
    # Intentional test-only dependencies: all made-up evidence stays labelled.
    from tests.integration.fixtures import extracted, intake_data, rules_data

    async def intake(state):
        return ProviderResult("ready", intake_data())

    async def rules(state):
        if human_review and not state.get("human_response"):
            return ProviderResult("needs_human_review", issue_codes=("synthetic_clarification",))
        return ProviderResult("ready", rules_data())

    def extraction(state):
        return {"extractions": {"w2-1": extracted()}}

    async def adversarial(state):
        # An empty test finding set is NOT an adversarial LLM evaluation.
        return ProviderResult("ready", {"findings": []})

    p = Providers(intake=intake, rules=rules, extraction=extraction,
                  adversarial=adversarial, mode="synthetic")
    graph = build_graph(p)
    config = {"configurable": {"thread_id": case_id}}
    state = await graph.ainvoke(new_case(case_id), config)
    resumed = False
    if human_review and state.get("__interrupt__"):
        payload = state["__interrupt__"][0].value
        state = await graph.ainvoke(Command(resume=dict(action="resolve", owner=payload["owner"],
            revision=payload["revision"], response={"resolution": "synthetic-test-resolution"})), config)
        resumed = True  # Test driver, not a real person's approval.
    return state, {
        "test_only_providers": ["intake", "rules", "extraction", "adversarial_review"],
        "computation": "actual_local_mcp", "audit": "actual_local_mcp_replay",
        "llm_called": False, "ocr_used": False, "human_interrupt_resumed": resumed,
        "approval_source": "synthetic_test_driver" if resumed else "none",
    }
