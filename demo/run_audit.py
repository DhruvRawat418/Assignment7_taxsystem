"""Safe component demo. A real packet without an injected MCP client cannot pass."""
import argparse
import asyncio
import json
from pathlib import Path
from src.agents.audit import audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", nargs="?", help="JSON audit packet; no MCP client is configured by this CLI")
    parser.add_argument("--synthetic-demo", action="store_true", help="Use test fixtures and a test-only tool double, NOT MCP")
    parser.add_argument("--tamper", action="store_true", help="Tamper with the synthetic trace to demonstrate rejection")
    args = parser.parse_args(argv)
    if bool(args.packet) == args.synthetic_demo or (args.tamper and not args.synthetic_demo):
        parser.error("Choose a packet OR --synthetic-demo; --tamper requires --synthetic-demo")
    client = None
    if args.synthetic_demo:
        from tests.audit.fixtures import clean_state
        from tests.audit.test_agent import SyntheticToolClient
        state, client = clean_state(), SyntheticToolClient()
        if args.tamper:
            state["computation_result"]["lines"]["1z"]["value"] = "99999.00"
            call = state["computation_result"]["tool_calls"][0]
            call["arguments"]["values"] = ["99999.00"]
            call["result"]["value"] = "99999.00"
    else:
        try:
            with Path(args.packet).open("rb") as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Too large")
            state = json.loads(raw)
        except (OSError, ValueError, RecursionError):
            state = {}  # No exception text or submitted content in CLI output.
    result = asyncio.run(audit(state, client))
    result["execution_mode"] = "synthetic_test_double" if args.synthetic_demo else "no_mcp_client"
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
