"""Safe component demo for Eligibility & Rules. Deterministic; no model, no network."""
import argparse
import json
from pathlib import Path

from src.agents.eligibility import eligibility, explain

SCENARIOS = {
    "clean": ("Single filer aged 65 or older with one clean W-2", {}),
    "ineligible": ("Nobody on the return meets the 1040-SR age test",
                   {"taxpayer_date_of_birth": "1970-03-15"}),
    "out-of-scope": ("Rental income and a request for advice",
                     {"has_rental_income": True, "requested_advice": True}),
    "bereaved": ("A spouse died during the tax year, so the status is ambiguous",
                 {"filing_status": "mfj", "spouse_date_of_birth": "1955-01-03",
                  "spouse_blind": False, "spouse_died_during_tax_year": True}),
    "needs-intake": ("A joint return with no spouse details collected",
                     {"filing_status": "mfj"}),
}


def report(result, rules=False):
    print(f"status: {result.status}")
    if result.issue_codes:
        print("issues: " + ", ".join(result.issue_codes))
    if result.status == "ready":
        profile = result.data["profile"]
        print(f"filing status: {profile['filing_status']}")
        print("line 12d boxes: " + (", ".join(result.data["line_12d_boxes"]) or "none"))
        print("clearance cites: " + ", ".join(result.data["clearance"]["citations"]))
        for document_id, decisions in result.data["box_dispositions"].items():
            print(f"  {document_id}: " + ", ".join(
                f"box {box}=" + (d["line"] if d["action"] == "use" else "not used")
                for box, d in sorted(decisions.items())))
    else:
        for condition in result.data.get("blocking_conditions", []):
            print("  - " + condition)
        for key in ("missing_facts", "detail"):
            if key in result.data:
                print(f"  {key}: {result.data[key]}")
    if rules:
        print("\nauthority:")
        cited = result.data.get("citations") or result.data.get("clearance", {}).get("citations", [])
        for rule_id in cited:
            rule = explain(rule_id)
            print(f"  {rule['rule_id']} ({rule['source']}): {rule['text']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", nargs="?", help="JSON case state to evaluate")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS),
                        help="Run a built-in synthetic scenario instead of a file")
    parser.add_argument("--rules", action="store_true", help="Print the text of every cited rule")
    args = parser.parse_args(argv)
    if bool(args.state) == bool(args.scenario):
        parser.error("Choose a state file OR --scenario")

    if args.scenario:
        from tests.eligibility.fixtures import clean_state
        description, overrides = SCENARIOS[args.scenario]
        print(f"{args.scenario}: {description}\n")
        state = clean_state(**overrides)
    else:
        try:
            state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            parser.error("Could not read that state file as JSON")
            return 2

    report(eligibility(state), rules=args.rules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
