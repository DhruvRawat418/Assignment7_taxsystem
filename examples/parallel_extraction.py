"""Runnable extraction fan-out/aggregate example, not the full six-agent system.

Run from repo root: python -m examples.parallel_extraction
"""
import json
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.agents.document_extraction import ExtractionState, make_extraction_node


def build_graph(engine_factory=None):
    graph = StateGraph(ExtractionState)
    node = make_extraction_node() if engine_factory is None else make_extraction_node(engine_factory)
    graph.add_node("extract", node)
    graph.add_node("aggregate", lambda state: {})
    graph.add_conditional_edges(START,
        lambda state: [Send("extract", {"document": doc}) for doc in state["documents"]]
        or "aggregate", ["extract", "aggregate"])
    graph.add_edge("extract", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()


if __name__ == "__main__":
    result = build_graph().invoke({"documents": [
        {"document_id": "W2#1", "path": "demo/w2_clean.jpg"},
        {"document_id": "W2#2", "path": "demo/w2_missing_withholding.jpg"},
    ], "extractions": {}})
    print(json.dumps(result["extractions"], indent=2))
