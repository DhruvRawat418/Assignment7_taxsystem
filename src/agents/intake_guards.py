"""Deterministic guardrails and validators for the Intake agent.

Nothing in this file calls an LLM. These checks run on every reply, before the
LLM sees it, so they cannot be talked around by a clever prompt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TAX_YEAR = 2025

# --------------------------------------------------------------------------
# SSN handling
# --------------------------------------------------------------------------
# 9 digits, optionally split 3-2-4 by dashes or spaces, not part of a longer number.
SSN_PATTERN = re.compile(r"(?<!\d)(\d{3})[- ]?(\d{2})[- ]?(\d{4})(?!\d)")


@dataclass
class SSNScan:
    redacted_text: str
    test_ssns: list[str] = field(default_factory=list)  # 900-999 series, "9XX-XX-XXXX"
    real_ssn_found: bool = False


def is_test_ssn(area: str) -> bool:
    """The US government reserves the 900-999 area numbers; the only ones we accept."""
    return 900 <= int(area) <= 999


def scan_ssns(text: str) -> SSNScan:
    """Find SSN-shaped numbers. Real ones are redacted and never stored or sent to the LLM.
    Test (900-series) ones are also replaced by a token so the LLM never sees any SSN."""
    scan = SSNScan(redacted_text=text)

    def _replace(m: re.Match) -> str:
        area, group, serial = m.groups()
        if is_test_ssn(area):
            scan.test_ssns.append(f"{area}-{group}-{serial}")
            return "[TEST-SSN]"
        scan.real_ssn_found = True
        return "[SSN-REDACTED]"

    scan.redacted_text = SSN_PATTERN.sub(_replace, text)
    return scan


def mask_ssn(ssn: str) -> str:
    return "***-**-" + ssn[-4:]


# --------------------------------------------------------------------------
# Keyword backstops (the LLM also flags these; either one is enough)
# --------------------------------------------------------------------------
ADVICE_PATTERNS = [
    r"\broth\b",
    r"\bshould (i|we)\b",
    r"\bwould (i|we) (pay|save|owe|get)\b",
    r"\bcan (i|we) deduct\b",
    r"\b(lower|reduce|minimi[sz]e|cut) (my|our) tax",
    r"\bis it better\b",
    r"\bwhat'?s (the )?best\b",
    r"\bsave (me |us )?(money|on tax)",
]
THIRD_PARTY_PATTERNS = [
    r"\b(i'?m|i am) (answering|filling (this|it) (out|in)|doing this|typing) for\b",
    r"\bon (his|her|their) behalf\b",
    r"\b(he|she) (can'?t|cannot|doesn'?t|does not) (understand|talk|come|hear|type)\b",
    r"\bmy (son|daughter|nephew|niece|grandson|granddaughter|caregiver|neighbou?r|friend) "
    r"(says|said|told me|wants|handles|takes care|is doing)\b",
]
AUTHORITY_PATTERNS = [
    r"\bpower of attorney\b",
    r"\bpoa\b",
    r"\b(legal )?guardian\b",
    r"\bconservator\b",
]
REFUND_CONCERN_PATTERNS = [
    r"\b(don'?t|do not) know (whose|which|what) account\b",
    r"\b(refund|money|check)\b.*\b(to|into)\b.*\b(son'?s|daughter'?s|nephew'?s|niece'?s|friend'?s|"
    r"caregiver'?s|someone else'?s|his|her|their)\b.*\baccount\b",
    r"\baccount\b.*\b(isn'?t|is not|not) mine\b",
]
SPOUSE_DEATH_PATTERNS = [
    r"\b(husband|wife|spouse|partner)\b.*\b(passed|died|death|lost)\b",
    r"\b(passed|died|lost)\b.*\b(husband|wife|spouse|partner)\b",
    r"\bwidow(ed|er)?\b",
]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


@dataclass
class Flags:
    advice: bool = False
    third_party: bool = False
    stated_authority: str | None = None
    refund_concern: bool = False
    spouse_death: bool = False


def detect_flags(text: str) -> Flags:
    authority = None
    for p in AUTHORITY_PATTERNS:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            authority = m.group(0)
            break
    return Flags(
        advice=_any(ADVICE_PATTERNS, text),
        third_party=_any(THIRD_PARTY_PATTERNS, text) or authority is not None,
        stated_authority=authority,
        refund_concern=_any(REFUND_CONCERN_PATTERNS, text),
        spouse_death=_any(SPOUSE_DEATH_PATTERNS, text),
    )


# --------------------------------------------------------------------------
# Validators: normalise a reply, or return None so we re-ask.
# Parsing a number the user typed is not arithmetic; adding numbers would be.
# --------------------------------------------------------------------------
FILING_STATUS_MAP = [
    (r"head of (the )?household|\bhoh\b", "head_of_household"),
    (r"surviving spouse|\bqss\b|qualifying widow", "qualifying_surviving_spouse"),
    (r"separate", "married_filing_separately"),
    # "single" is checked before "married" so that "I'm not married" is read as single.
    (r"single|not married|never married|divorced|on my own|alone|by myself", "single"),
    (r"married|joint|together|\bmfj\b", "married_filing_jointly"),
]


def parse_filing_status(text: str) -> str | None:
    for pattern, value in FILING_STATUS_MAP:
        if re.search(pattern, text, re.IGNORECASE):
            return value
    return None


def parse_yes_no(text: str) -> bool | None:
    t = text.strip().lower()
    # Negatives first, so "she is not blind" is not read as a yes.
    if re.search(r"\b(no|nope|not|none|never)\b|n'?t\b", t):
        return False
    if re.search(r"\b(yes|yeah|yep|correct|i am|i do|i did|she is|he is|they are|sure)\b", t):
        return True
    return None


DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y",
                "%b %d %Y", "%d %B %Y", "%d %b %Y"]


def parse_date(text: str) -> str | None:
    """Return an ISO date string, or None. Sanity-checks the year only (no age maths here:
    deciding who is 65+ is the Eligibility agent's job)."""
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().rstrip("."))
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        if date(1900, 1, 1) <= d <= date(TAX_YEAR, 12, 31):
            return d.isoformat()
    return None


AMOUNT_PATTERN = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")


@dataclass
class AmountParse:
    value: str | None  # e.g. "1500.00"
    multiple_amounts: bool = False


def parse_amount(text: str) -> AmountParse:
    if re.search(r"\b(none|nothing|zero|no)\b", text, re.IGNORECASE) and not re.search(r"\d", text):
        return AmountParse("0.00")
    matches = AMOUNT_PATTERN.findall(text)
    if len(matches) > 1:
        # Several amounts: we do NOT add them up. We ask the person for the total.
        return AmountParse(None, multiple_amounts=True)
    if not matches:
        return AmountParse(None)
    whole, cents = matches[0]
    try:
        value = Decimal(whole.replace(",", "") + "." + (cents or "0").ljust(2, "0"))
    except InvalidOperation:
        return AmountParse(None)
    return AmountParse(f"{value:.2f}")


KNOWN_FORMS = {
    "W-2": r"\bw[- ]?2\b",
    "SSA-1099": r"\bssa[- ]?1099\b|social security (statement|benefit)",
    "1099-R": r"\b1099[- ]?r\b|pension|ira (distribution|statement)",
    "1099-INT": r"\b1099[- ]?int\b|interest",
    "1099-DIV": r"\b1099[- ]?div\b|dividend",
    "1099-NEC": r"\b1099[- ]?nec\b",
    "1099-B": r"\b1099[- ]?b\b",
    "1099-MISC": r"\b1099[- ]?misc\b",
}


def parse_documents(text: str) -> list[str] | None:
    """Record which forms the person says they have. We do not judge scope here:
    the Eligibility agent decides what is in or out of scope."""
    if re.search(r"\b(none|nothing|no forms)\b", text, re.IGNORECASE):
        return []
    found = [name for name, pattern in KNOWN_FORMS.items() if re.search(pattern, text, re.IGNORECASE)]
    other = re.findall(r"(?<!ssa-)(?<!ssa )\b(1099-[a-z]{1,4}|schedule [a-z]|k-1)\b", text, re.IGNORECASE)
    for o in other:
        label = o.upper().replace(" ", "-")
        if not any(label.replace("-", "") == f.replace("-", "") for f in found):
            found.append(f"OTHER: {o}")
    if not found and text.strip():
        found = [f"OTHER: {text.strip()}"]  # recorded as said; Eligibility decides if it's in scope
    return found or None


def parse_files(text: str) -> list[str] | None:
    """File names of uploaded W-2 images, as typed. In a real UI these come from the upload widget."""
    names = [n.strip().strip("\"'") for n in re.split(r",|\band\b", text)]
    names = [n for n in names if n]
    return list(dict.fromkeys(names)) or None
