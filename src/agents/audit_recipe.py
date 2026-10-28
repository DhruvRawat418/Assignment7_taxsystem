"""Expected operations reconstructed from inputs and newly verified values."""
from src.agents.audit_contract import INPUT_LINES, money, normalized_profile


def expected_arguments(request, key, tool, dependencies, verified):
    """No recorded tool arguments or recorded derived values are trusted here."""
    if key in INPUT_LINES:
        return {"values": [str(money(entry["value"])) for entry in request["amounts"][key]]}
    values = [verified[dependency] for dependency in dependencies]
    if tool == "sum_amounts":
        return {"values": values}
    if tool == "difference":
        return dict(left=values[0], right=values[1], floor_zero=key in ("15", "22", "34", "37"))
    profile = normalized_profile(request["profile"])
    if tool == "social_security_taxable":
        return dict(benefits=values[0], other_income=values[1], tax_exempt_interest=values[2],
                    adjustments=values[3], profile=profile)
    if tool == "standard_deduction":
        return {"profile": profile}
    if tool == "senior_deduction":
        return {"agi": values[0], "profile": profile}
    if tool == "income_tax":
        return dict(taxable_income=values[0], qualified_dividends=values[1], filing_status=profile["filing_status"])
    raise ValueError("Unknown expected operation")


def arguments_equal(recorded, expected):
    """Exact shapes/types, with numerical equality for monetary strings only."""
    if isinstance(expected, dict):
        return (isinstance(recorded, dict) and set(recorded) == set(expected)
                and all(arguments_equal(recorded[k], value) for k, value in expected.items()))
    if isinstance(expected, list):
        return (isinstance(recorded, list) and len(recorded) == len(expected)
                and all(arguments_equal(a, b) for a, b in zip(recorded, expected)))
    if isinstance(expected, str):
        try:
            money(expected)
        except ValueError:
            return type(recorded) is str and recorded == expected
        try:
            return money(recorded) == money(expected)
        except ValueError:
            return False
    return type(recorded) is type(expected) and recorded == expected
