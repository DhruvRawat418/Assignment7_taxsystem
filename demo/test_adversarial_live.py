"""Live AI test with deliberately contradictory synthetic evidence."""

import asyncio
import json

from src.agents.adversarial import make_adversarial_provider
from src.agents.openai_transport import openai_review_call


async def main():
    # Deliberately inconsistent test data.
    # These statuses are fabricated, not real computation/audit results.
    state = {
        "rules_output": {
            "profile": {
                "filing_status": "single",
                "taxpayer_65_or_older": True,
            },
            "clearance": {
                "approved": False,
                "blocking_conditions": [
                    "Rental income is outside the supported scope."
                ],
                "citations": ["Assignment brief section 3.3"],
            },
            "box_dispositions": {},
        },
        "computation_input": {
            "tax_year": 2025,
            "rules": {
                "approved": False,
                "blocking_conditions": [
                    "Rental income is outside the supported scope."
                ],
            },
        },
        "computation_result": {
            "status": "completed",
            "draft_only": True,
            "lines": {},
        },
        "audit_result": {
            "status": "passed",
            "issues": [],
        },
        "projection_notes": [],
    }

    reviewer = make_adversarial_provider(openai_review_call)
    result = await reviewer(state)

    print("SYNTHETIC ADVERSARIAL TEST — not a real return")
    print("Provider status:", result.status)
    print(json.dumps(result.data, indent=2))

    if result.status != "ready":
        print("INCONCLUSIVE: the reviewer failed to return a valid report.")
        print("Issue codes:", result.issue_codes)
    elif not result.data["findings"]:
        print("FAIL: the reviewer missed the deliberately flawed case.")
    else:
        print(
            "Findings returned. Check that they identify the blocked "
            "eligibility clearance, not merely the incomplete test data."
        )


if __name__ == "__main__":
    asyncio.run(main())