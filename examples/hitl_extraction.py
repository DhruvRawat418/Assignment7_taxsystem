"""Small extraction-only interrupt/resume demo, separate from the team graph.

No human-entered dollar amount can bypass the original source requirement.
Resume by supplying a clearer/replacement image under a new upload ID.
"""
from __future__ import annotations

from typing import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.agents.document_extraction import (
    DocumentRequest, ExtractionState, make_extraction_node,
)


class HandoffState(ExtractionState, total=False):
    attempts: int
    stopped: bool


def build_graph(engine_factory=None):
    graph = StateGraph(HandoffState)
    graph.add_node("extract", make_extraction_node() if engine_factory is None
                   else make_extraction_node(engine_factory), input_schema=HandoffState)

    def human_review(state):
        result = state["extractions"][state["document"]["document_id"]]
        decision = interrupt({"kind": "extraction_review", "issues": result["issues"],
            "instruction": "Provide replacement_path to a synthetic W-2 image, or action=stop."})
        if decision.get("action") == "stop":
            return {"stopped": True}
        attempt = state.get("attempts", 0) + 1
        if not isinstance(decision.get("replacement_path"), str):
            return {"stopped": True}
        return {"document": {"document_id": f"W2#replacement-{attempt}",
                "path": decision["replacement_path"]}, "attempts": attempt}

    def route_after_extract(state):
        result = state["extractions"][state["document"]["document_id"]]
        if result["status"] == "extracted" or state.get("attempts", 0) >= 3:
            return END
        return "human_review"

    graph.add_node("human_review", human_review)
    graph.add_edge(START, "extract")
    graph.add_conditional_edges("extract", route_after_extract, ["human_review", END])
    graph.add_conditional_edges("human_review",
        lambda state: END if state.get("stopped") else "extract", ["extract", END])
    return graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    graph = build_graph()
    config = {"configurable": {"thread_id": "extraction-demo"}, "recursion_limit": 20}
    result = graph.invoke({"document": {"document_id": "W2#original",
        "path": "demo/w2_missing_withholding.jpg"}, "attempts": 0, "extractions": {}}, config)
    assert result.get("__interrupt__"), "Expected a missing-amount interrupt."
    print("Paused for human review:", result["__interrupt__"][0].value)
    print("Demo operator supplies a complete replacement synthetic W-2 image.")
    result = graph.invoke(Command(resume={"replacement_path": "demo/w2_clean.jpg"}), config)
    active = result["extractions"][result["document"]["document_id"]]
    print("Final extraction status:", active["status"])
    print("Original upload retained for audit:", "W2#original" in result["extractions"])
    assert active["status"] == "extracted"
