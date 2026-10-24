"""Run only the Computation Agent against a structured, synthetic input file."""

import argparse
import asyncio
import json
from pathlib import Path

from src.agents.computation import computation_node


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON audit record destination")
    args = parser.parse_args()
    state = await computation_node({"computation_input": json.loads(args.input.read_text())})
    result = state["computation_result"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "draft_only": result["draft_only"],
                      "lines": {line: data["value"] for line, data in result["lines"].items()},
                      "issues": result["issues"], "mcp_tool_calls": len(result["tool_calls"])}, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
