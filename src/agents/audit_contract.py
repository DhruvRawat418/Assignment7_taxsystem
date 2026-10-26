"""Audit's own boundary; does not redefine the team's global LangGraph state."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json

INPUT_LINES = ("1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a",
               "8", "10", "17", "19", "20", "23", "25a", "25b", "25c", "26", "32", "ss_adjustments")
# Independent orchestration specification, not a tax-math implementation.
DERIVED = (
    ("income_before_ss", "sum_amounts", ("1z", "2b", "3b", "4b", "5b", "8")),
    ("6b", "social_security_taxable", ("6a", "income_before_ss", "2a", "ss_adjustments")),
    ("9", "sum_amounts", ("income_before_ss", "6b")),
    ("11a", "difference", ("9", "10")), ("11b", "sum_amounts", ("11a",)),
    ("12e", "standard_deduction", ()), ("13b", "senior_deduction", ("11b",)),
    ("14", "sum_amounts", ("12e", "13b")), ("15", "difference", ("11b", "14")),
    ("16", "income_tax", ("15", "3a")), ("18", "sum_amounts", ("16", "17")),
    ("21", "sum_amounts", ("19", "20")), ("22", "difference", ("18", "21")),
    ("24", "sum_amounts", ("22", "23")), ("25d", "sum_amounts", ("25a", "25b", "25c")),
    ("33", "sum_amounts", ("25d", "26", "32")), ("34", "difference", ("33", "24")),
    ("37", "difference", ("24", "33")),
)
SPECS = tuple((key, "sum_amounts", ()) for key in INPUT_LINES) + DERIVED
ALL_LINES = frozenset(key for key, _, _ in SPECS)
INTERMEDIATES = frozenset(("income_before_ss", "ss_adjustments"))


def money(value):
    """Validate and compare money, never calculate tax inside this component."""
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Invalid money type")
    if len(str(value)) > 80:
        raise ValueError("Money too long")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or abs(amount) >= Decimal("1000000000000"):
            raise ValueError("Money out of bounds")
        with localcontext() as context:
            context.prec = 40
            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError("Money precision")
        return amount
    except InvalidOperation:
        raise ValueError("Invalid money") from None


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError("Invalid text")
    return value


def references(value):
    if not isinstance(value, list) or not value or len(value) > 256:
        raise ValueError("Missing references")
    for item in value:
        text(item)


def source_key(source):
    if not isinstance(source, dict) or source.get("kind") not in ("document", "user_input"):
        raise ValueError("Invalid source")
    if set(source) - {"kind", "reference", "field", "entered_by", "recorded_at"}:
        raise ValueError("Unknown source field")
    for key in ("reference", "field"):
        text(source.get(key))
    if source["kind"] == "user_input":
        text(source.get("entered_by"))
        timestamp = datetime.fromisoformat(text(source.get("recorded_at")).replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError("Missing input timezone")
    # Pydantic includes optional document fields as null when serializing.
    normalized = {key: source.get(key) for key in ("kind", "reference", "field", "entered_by", "recorded_at")}
    if source["kind"] == "user_input":
        normalized["recorded_at"] = timestamp.astimezone(timezone.utc).isoformat()
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def normalized_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Missing profile")
    allowed = {"filing_status", "taxpayer_65_or_older", "taxpayer_blind", "spouse_65_or_older",
               "spouse_blind", "mfs_lived_with_spouse", "mfs_spouse_allowance_approved"}
    if set(profile) - allowed or profile.get("filing_status") not in ("single", "mfj", "mfs", "hoh", "qss"):
        raise ValueError("Invalid profile")
    out = dict(profile)
    for key in ("taxpayer_65_or_older", "taxpayer_blind", "spouse_65_or_older", "spouse_blind"):
        if type(out.get(key)) is not bool:
            raise ValueError("Explicit checkbox required")
    out.setdefault("mfs_lived_with_spouse", None)
    out.setdefault("mfs_spouse_allowance_approved", False)
    if type(out["mfs_spouse_allowance_approved"]) is not bool:
        raise ValueError("Invalid spouse approval")
    if out["mfs_lived_with_spouse"] is not None and type(out["mfs_lived_with_spouse"]) is not bool:
        raise ValueError("Invalid living status")
    if out["filing_status"] == "mfs" and out["mfs_lived_with_spouse"] is None:
        raise ValueError("Missing living status")
    if out["filing_status"] not in ("mfj", "mfs") and (out["spouse_65_or_older"] or out["spouse_blind"]):
        raise ValueError("Inapplicable spouse flags")
    if out["filing_status"] != "mfs" and out["mfs_spouse_allowance_approved"]:
        raise ValueError("Inapplicable spouse approval")
    return out


def issue(code, line=None, route_to="computation", unavailable=False):
    """Fixed messages and pointers only: never echo raw documents/errors/PII."""
    safe_line = line if line in ALL_LINES else None
    return dict(code=code, line=safe_line, message=code.replace("_", " ").capitalize() + ".",
                evidence_refs=["computation_result" + (".lines." + safe_line if safe_line and safe_line not in INTERMEDIATES else "")],
                route_to=route_to, unavailable=unavailable)
