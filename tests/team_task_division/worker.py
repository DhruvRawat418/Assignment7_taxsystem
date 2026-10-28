"""Opt-in integration probe, run in a temporary workspace by the pytest driver.

Real teammate Intake/Rules/Computation, our real image extraction, and real MCP
Audit. Only Adversarial Review is a labelled test double. The second run uses an
explicit TEST-ONLY metadata projection to isolate the known Rules interface bug.
It is not a production workaround or evidence of adversarial LLM evaluation.
"""
import asyncio
from copy import deepcopy
import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.agents.eligibility import eligibility
from src.agents.intake import IntakeState, initial_intake_state, make_intake_node
from src.agents.intake_contract import make_intake_provider
from src.agents.intake_parser import RuleParser
from src.document_extraction import extract_w2
from src.integration.contracts import ProviderResult, Providers
from src.integration.graph import build_graph
from src.integration.state import new_case


def interview():
    builder = StateGraph(IntakeState)
    builder.add_node("intake", make_intake_node(RuleParser()))
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", lambda s: END if s.get("intake_complete") else "intake", [END, "intake"])
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "team-interview"}}
    state = graph.invoke(initial_intake_state(), config)
    # Synthetic replies, delivered through the real Intake interrupt/resume node.
    replies = ["single", "March 5, 1955", "no", "no", *(["no"] * 7),
               "W-2 and SSA-1099", "demo/w2_clean.jpg", "$24,000", "none", "no"]
    for reply in replies:
        assert state["__interrupt__"], "Interview ended before all supplied answers"
        state = graph.invoke(Command(resume=reply), config)
    assert state["intake_complete"] and not state.get("__interrupt__")
    return state


async def main():
    session = interview()
    intake = make_intake_provider(lambda case_id: session)
    packet = intake(new_case("peer-contract")).data
    document = packet["documents"][0]
    # Real OCR, cached for the two contract runs; no fabricated OCR evidence.
    result = extract_w2(document["path"], document["document_id"]).model_dump(mode="json")
    assert result["status"] == "extracted", result["issues"]

    def extraction(state):
        assert state["document"] == document
        return {"extractions": {document["document_id"]: deepcopy(result)}}

    def adversarial_test_double(state):
        return ProviderResult("ready", {"findings": []})

    metadata = []
    def projected_rules_for_test_only(state):
        output = eligibility(state)
        assert output.status == "ready"
        data = deepcopy(output.data)
        metadata.append(data.pop("line_12d_boxes"))
        return ProviderResult("ready", data)

    reports = {}
    for name, rules in (("raw_contract", eligibility), ("projected_smoke", projected_rules_for_test_only)):
        providers = Providers(intake=intake, rules=rules, extraction=extraction,
                              adversarial=adversarial_test_double, mode="synthetic")
        final = await build_graph(providers).ainvoke(new_case(name), {"configurable": {"thread_id": name}})
        reports[name] = {"status": final["status"], "issues": final["issues"],
                         "stages": [e["stage"] for e in final["events"]], "task_plan": final["task_plan"],
                         "tool_calls": len(final["computation_result"].get("tool_calls", [])),
                         "audit_status": final["audit_result"].get("status", "not_run")}
    reports.update(real_ocr=True, real_intake_rule_parser=True, real_rules=True,
                   real_computation_mcp_and_audit=True, test_only_adversarial=True,
                   projected_metadata=metadata, production_workaround_installed=False,
                   llm_called=False, full_system_verified=False)
    print(json.dumps(reports))


if __name__ == "__main__":
    asyncio.run(main())
