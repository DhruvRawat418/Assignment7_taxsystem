"""Opt-in real MCP + LangGraph smoke test against a separate Computation checkout.

Not a full-system evaluation: extraction evidence is a synthetic test fixture.
Run: python -m tests.audit.integration_with_computation --computation-root PATH
Requires the team's mcp/pydantic/langgraph dependencies; no LLM or API key.
"""
import argparse
import asyncio
from copy import deepcopy
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from typing import TypedDict

from tests.audit.fixtures import clean_state


async def run(root):
    # The explicit checkout supplies namespace packages; no source is copied or merged.
    sys.path.append(str(root))
    os.environ["LANGSMITH_TRACING"] = "false"
    from langgraph.graph import END, START, StateGraph
    from src.agents.computation import compute, computation_tools
    from src.agents.audit import make_audit_node

    request = json.loads((root / "demo/computation_clean.json").read_text())
    state = clean_state()
    state["computation_input"] = request
    state["audit_source_bindings"] = [
        dict(reference=request["amounts"][line][0]["sources"][0]["reference"],
             field=request["amounts"][line][0]["sources"][0]["field"], document_id="w2-1", amount_key=key)
        for line, key in (("1z", "box_1"), ("25a", "box_2"))]

    class ProbeState(TypedDict, total=False):
        computation_input: dict
        computation_result: dict
        extractions: dict
        audit_source_bindings: list
        audit_result: dict

    async with computation_tools() as client:
        result = await compute(request, client)
        assert result.status == "completed", "Upstream computation did not complete"
        state["computation_result"] = result.model_dump(mode="json")
        builder = StateGraph(ProbeState)
        builder.add_node("audit", make_audit_node(client))
        builder.add_edge(START, "audit")
        builder.add_edge("audit", END)
        graph = builder.compile()
        clean = (await graph.ainvoke(deepcopy(state)))["audit_result"]
        assert clean["status"] == "passed", clean["issues"]
        assert len(clean["verified_lines"]) == 40
        tampered = deepcopy(state)
        tampered["computation_result"]["lines"]["1z"]["value"] = "99999.00"
        for call in tampered["computation_result"]["tool_calls"]:
            if call["output_key"] == "1z":
                call["arguments"]["values"] = ["99999.00"]
                call["result"]["value"] = "99999.00"
        rejected = (await graph.ainvoke(tampered))["audit_result"]
        assert rejected["status"] == "revision_required"
        assert "recomputed_value_mismatch" in {i["code"] for i in rejected["issues"]}
    return dict(clean_status=clean["status"], verified_lines=len(clean["verified_lines"]),
                tampered_status=rejected["status"], execution="real_stdio_mcp_and_langgraph",
                extraction="synthetic_fixture_not_real_OCR", llm_calls=0,
                versions={key: version(key) for key in ("mcp", "langgraph", "pydantic")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--computation-root", type=Path, required=True)
    root = parser.parse_args().computation_root.resolve()
    print(json.dumps(asyncio.run(run(root)), indent=2))


if __name__ == "__main__":
    main()
