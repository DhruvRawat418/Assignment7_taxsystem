"""Deterministic 2025 course-scope tools. Arithmetic belongs here, not in the agent."""

from decimal import Decimal, ROUND_HALF_UP

from src.agents.computation_contract import Profile, parse_money

D = Decimal
ZERO = D("0")
CENT = D("0.01")
ASSIGNMENT = "https://canvas.cornell.edu/courses/88689/assignments/977982"
IRS_INSTRUCTIONS = "https://www.irs.gov/instructions/i1040gi"
IRS_RATES = "https://www.irs.gov/irb/2024-45_IRB"


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def response(value: Decimal, method: str, references: list[str], **details) -> dict:
    return {"value": money(value), "method": method,
            "rule_references": references, "details": details}


def sum_amounts(values: list[str]) -> dict:
    """Sum validated decimal amounts, including raw values from multiple documents."""
    if not values:
        raise ValueError("At least one explicit amount is required")
    return response(sum((parse_money(v) for v in values), ZERO),
                    "sum(values)", [ASSIGNMENT])


def difference(left: str, right: str, floor_zero: bool = False) -> dict:
    """Subtract amounts; clamp only lines whose instructions require a zero floor."""
    result = parse_money(left) - parse_money(right)
    if floor_zero:
        result = max(ZERO, result)
    return response(result, "max(0, left - right)" if floor_zero else "left - right",
                    [ASSIGNMENT])


def standard_deduction(profile: dict) -> dict:
    """2025 standard deduction, separate from the Schedule 1-A senior deduction."""
    p = Profile.model_validate(profile)
    base = {"single": D("15750"), "mfs": D("15750"), "mfj": D("31500"),
            "qss": D("31500"), "hoh": D("23625")}[p.filing_status]
    boxes = int(p.taxpayer_65_or_older) + int(p.taxpayer_blind)
    if p.filing_status == "mfj":
        boxes += int(p.spouse_65_or_older) + int(p.spouse_blind)
    elif p.filing_status == "mfs" and (p.spouse_65_or_older or p.spouse_blind):
        if not p.mfs_spouse_allowance_approved:
            raise ValueError("Rules must approve MFS spouse additional deduction")
        boxes += int(p.spouse_65_or_older) + int(p.spouse_blind)
    increment = D("2000") if p.filing_status in ("single", "hoh") else D("1600")
    return response(base + D(boxes) * increment, "base + age/blindness boxes * increment",
                    [ASSIGNMENT, IRS_INSTRUCTIONS], boxes=boxes,
                    base=money(base), per_box=money(increment))


def senior_deduction(agi: str, profile: dict) -> dict:
    """Schedule 1-A Part V; MAGI equals AGI within this restricted return profile."""
    p = Profile.model_validate(profile)
    income = parse_money(agi)
    if p.filing_status == "mfs":
        return response(ZERO, "MFS is not eligible for the enhanced senior deduction",
                        [IRS_INSTRUCTIONS])
    people = int(p.taxpayer_65_or_older)
    if p.filing_status == "mfj":
        people += int(p.spouse_65_or_older)
    threshold = D("150000") if p.filing_status == "mfj" else D("75000")
    excess = max(ZERO, income - threshold)
    per_person = max(ZERO, D("6000") - excess * D("0.06"))
    return response(per_person * D(people),
                    "qualifying_people * max(0, 6000 - 0.06 * max(0, MAGI - threshold))",
                    [ASSIGNMENT, IRS_INSTRUCTIONS], qualifying_people=people,
                    magi=money(income), threshold=money(threshold), per_person=money(per_person))


def social_security_taxable(benefits: str, other_income: str, tax_exempt_interest: str,
                            adjustments: str, profile: dict) -> dict:
    """1040 Social Security Benefits Worksheet, with MFS living-status treatment."""
    p = Profile.model_validate(profile)
    benefits_d, other, exempt, adjustments_d = map(
        parse_money, (benefits, other_income, tax_exempt_interest, adjustments))
    if min(benefits_d, exempt, adjustments_d) < ZERO:
        raise ValueError("Benefits, exempt interest, and adjustments cannot be negative")
    provisional = max(ZERO, other + exempt + benefits_d * D("0.5") - adjustments_d)
    if p.filing_status == "mfs" and p.mfs_lived_with_spouse:
        taxable = min(benefits_d * D("0.85"), provisional * D("0.85"))
    else:
        base, width = ((D("32000"), D("12000")) if p.filing_status == "mfj"
                       else (D("25000"), D("9000")))
        above_base = max(ZERO, provisional - base)
        lower = min(benefits_d * D("0.5"), min(above_base, width) * D("0.5"))
        higher = max(ZERO, above_base - width) * D("0.85")
        taxable = min(benefits_d * D("0.85"), lower + higher)
    return response(taxable, "2025 Social Security Benefits Worksheet",
                    [ASSIGNMENT, IRS_INSTRUCTIONS], provisional_income=money(provisional))


BRACKETS = {
    "single": ("11925", "48475", "103350", "197300", "250525", "626350"),
    "mfj": ("23850", "96950", "206700", "394600", "501050", "751600"),
    "mfs": ("11925", "48475", "103350", "197300", "250525", "375800"),
    "hoh": ("17000", "64850", "103350", "197300", "250500", "626350"),
    "qss": ("23850", "96950", "206700", "394600", "501050", "751600"),
}
RATES = tuple(map(D, ("0.10", "0.12", "0.22", "0.24", "0.32", "0.35", "0.37")))
DIVIDEND_THRESHOLDS = {
    "single": (D("48350"), D("533400")),
    "mfj": (D("96700"), D("600050")),
    "mfs": (D("48350"), D("300000")),
    "hoh": (D("64750"), D("566700")),
    "qss": (D("96700"), D("600050")),
}


def ordinary_tax(income: Decimal, filing_status: str) -> Decimal:
    tax, lower = ZERO, ZERO
    for upper, rate in zip((*map(D, BRACKETS[filing_status]), D("Infinity")), RATES):
        if income <= lower:
            break
        tax += (min(income, upper) - lower) * rate
        lower = upper
    return tax


def income_tax(taxable_income: str, qualified_dividends: str, filing_status: str) -> dict:
    """Assignment rate-schedule calculation, with qualified-dividend stacking.

    Deliberately not an IRS Tax Table lookup for income below $100,000: the
    assignment specifies a rate schedule. This distinction is documented.
    """
    if filing_status not in BRACKETS:
        raise ValueError("Unsupported filing status")
    income, dividends = map(parse_money, (taxable_income, qualified_dividends))
    if min(income, dividends) < ZERO:
        raise ValueError("Taxable income and qualified dividends cannot be negative")
    qualified = min(income, dividends)
    ordinary = income - qualified
    zero_limit, fifteen_limit = DIVIDEND_THRESHOLDS[filing_status]
    at_zero = min(qualified, max(ZERO, zero_limit - ordinary))
    at_fifteen = min(qualified - at_zero, max(ZERO, fifteen_limit - ordinary - at_zero))
    at_twenty = qualified - at_zero - at_fifteen
    preferred = ordinary_tax(ordinary, filing_status) + at_fifteen * D("0.15") + at_twenty * D("0.20")
    return response(min(preferred, ordinary_tax(income, filing_status)),
                    "2025 assignment rate schedules with qualified-dividend stacking",
                    [ASSIGNMENT, IRS_RATES, IRS_INSTRUCTIONS],
                    ordinary_taxable_income=money(ordinary), dividends_at_zero=money(at_zero),
                    dividends_at_fifteen=money(at_fifteen), dividends_at_twenty=money(at_twenty))
