"""Human approval alone must not override an out-of-scope case."""

from copy import deepcopy

from src.agents.eligibility import make_eligibility_node


def test_approval_does_not_clear_rental_income():
    rules = make_eligibility_node()

    state = {
        "intake_snapshot": {
            "facts": {
                "filing_status": "single",
                "taxpayer_date_of_birth": "1955-01-01",
                "taxpayer_blind": False,
                "has_rental_income": True,
            }
        },
        "documents": [],
        "extractions": {},
    }

    original = rules(state)
    assert original.status == "needs_human_review"
    assert "rental_income_out_of_scope" in original.issue_codes

    attempted_override = deepcopy(state)
    attempted_override["human_response"] = {
        "owner": "rules",
        "response": {
            "approved": True,
            "resolution": "Please proceed anyway.",
        },
    }

    reviewed = rules(attempted_override)

    assert reviewed.status == "needs_human_review"
    assert "rental_income_out_of_scope" in reviewed.issue_codes