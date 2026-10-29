"""Conservative, label-anchored W-2 transcription with per-box provenance."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .models import ExtractionResult, Issue, MoneyFact, Source, TextFact, W2Record
from .ocr import OCREngine, RapidOCREngine, Token, load_image

# Printed box labels are anchors; coordinates are discovered, not template constants.
LABELS = {
    "1": r"^1wagestips",
    "2": r"^2federalincometax",
    "3": r"^3socialsecuritywages",
    "4": r"^4socialsecuritytax",
    "5": r"^5medicarewages",
    "6": r"^6medicaretax",
    "7": r"^7socialsecuritytips",
    "8": r"^8allocatedtips",
    "10": r"^10dependentcare",
    "11": r"^11nonqualifiedplans",
}
# Lower row labels stop the preceding amount region from consuming another box.
BOUNDARIES = list(LABELS.values()) + [
    r"^9$", r"^12[abcd]", r"^13statutory", r"^14other",
    r"^15state", r"^16statewages", r"^17stateincome",
]
SSN = re.compile(r"(?<!\d)(\d{3})[- ]*(\d{2})[- ]*(\d{4})(?!\d)")
EIN = re.compile(r"(?<!\d)\d{2}-\d{7}(?!\d)")
MONEY = re.compile(r"^\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?$")
LABEL_CONTINUATIONS = {
    "compensation", "othercompensation", "tipsothercompensation", "withheld",
    "taxwithheld", "incometaxwithheld", "wages", "andtips", "benefits", "plans",
}


def parse_money(text: str) -> Decimal | None:
    """No OCR character repair, rounding, arithmetic, or inferred zeroes."""
    text = text.strip()
    if MONEY.fullmatch(text):
        return Decimal(text.replace("$", "").replace(",", "").strip())
    return None


def _matches(token: Token, pattern: str) -> bool:
    return re.search(pattern, re.sub(r"[^a-z0-9]", "", token.text.lower())) is not None


def _field_region(label: Token, anchors: list[Token], image_size: tuple[int, int]):
    width, height = image_size
    lh = max(1., label.bbox[3] - label.bbox[1])
    left = label.bbox[0] - .4 * lh
    right_candidates = [a.bbox[0] - .3 * lh for a in anchors
                        if a.bbox[0] > label.bbox[0] + lh
                        and abs(a.cy - label.cy) < 1.2 * lh]
    right = min(right_candidates, default=float(width))
    # Either column's next label bounds the row. Always cap its height too:
    # a missing label must not extend the search into a distant unrelated row.
    lower_candidates = [a.bbox[1] for a in anchors
                        if a.bbox[1] > label.bbox[3] + .3 * lh]
    bottom = min([height, label.bbox[3] + 4 * lh, *lower_candidates])
    return left, label.bbox[3], right, bottom


def _inside(token: Token, region) -> bool:
    left, top, right, bottom = region
    return left <= token.bbox[0] and token.bbox[2] <= right and top <= token.cy < bottom


def transcribe_tokens(
    tokens: list[Token], *, document_id: str, sha256: str,
    image_size: tuple[int, int], engine: str, min_confidence: float = .90,
) -> ExtractionResult:
    """Internal OCR parser; image/config validation belongs to extract_w2."""
    now = datetime.now(timezone.utc)
    issues: list[Issue] = []
    anchors = [t for t in tokens if any(_matches(t, p) for p in BOUNDARIES)]
    regions = {t: _field_region(t, anchors, image_size) for t in anchors
               if any(_matches(t, p) for p in LABELS.values())}
    money_values = {}
    for token in tokens:
        value = parse_money(token.text)
        if value is not None:
            money_values[token] = value

    # Validate before constructing records or persisting raw evidence.
    # A nine-digit dollar amount inside a labeled monetary box is not an SSN.
    # Formatted SSNs remain blocked even when placed inside a monetary box.
    ssns = [(t, m) for t in tokens for m in SSN.finditer(t.text)
            if not (t in money_values
                    and any(_inside(t, region) for region in regions.values()))]
    if any(not 900 <= int(m[1]) <= 999 for _, m in ssns):
        return ExtractionResult(document_id=document_id, sha256=sha256,
            status="rejected", issues=(Issue(code="unsafe_ssn", field="employee_ssn",
                message="Only synthetic SSNs beginning with 900 through 999 are allowed. Replace the document."),))

    if not any(re.search(r"(?:^|form)w2(?:wage|20|$)|wageandtaxstatement",
                        re.sub(r"[^a-z0-9]", "", t.text.lower())) for t in tokens):
        return ExtractionResult(document_id=document_id, sha256=sha256,
            status="needs_review", issues=(Issue(code="unrecognized_document",
                message="A single W-2 copy could not be identified. Ask Intake for a clearer W-2 image."),))

    def source(box: str, evidence: list[Token]) -> Source:
        return Source(document_id=document_id, sha256=sha256, box=box,
            bbox=(min(t.bbox[0] for t in evidence), min(t.bbox[1] for t in evidence),
                  max(t.bbox[2] for t in evidence), max(t.bbox[3] for t in evidence)),
            image_size=image_size, raw_text=" | ".join(t.text for t in evidence),
            confidence=min(t.confidence for t in evidence), engine=engine, timestamp=now)

    def text_fact(field: str, candidates: list[tuple[str, Token]], *, required: bool = True) -> TextFact | None:
        values = {value for value, _ in candidates}
        if not values:
            if required:
                issues.append(Issue(code="missing_field", field=field,
                    message=f"{field} needs a clear, unique printed value."))
            return None
        if len(values) > 1:
            issues.append(Issue(code="ambiguous_field",
                field=field, message=f"{field} needs a clear, unique printed value."))
            return None
        value, token = candidates[0]
        if token.confidence < min_confidence:
            issues.append(Issue(code="low_confidence", field=field,
                message=f"{field} needs human verification or a clearer image."))
            return None
        return TextFact(value=value, source=source(field, [token]))

    year_candidates = []
    for token in tokens:
        # A year must be a standalone heading/footer value or explicitly part of
        # the form title. A monetary value or SSN suffix is never year evidence.
        if any(_inside(token, region) for region in regions.values()):
            continue
        text = SSN.sub("", EIN.sub("", token.text)).strip()
        compact = re.sub(r"[^a-z0-9]", "", text.lower())
        if re.fullmatch(r"20\d{2}", text):
            year_candidates.append((text, token))
        elif re.search(r"taxyear|wageandtaxstatement|(?:^|form)w2", compact):
            # FormW22025 can be emitted without a gap after the form number.
            title_text = re.sub(r"(?i)w\s*[-–]?\s*2", "W-2 ", text)
            year_candidates.extend((m[0], token) for m in
                re.finditer(r"(?<!\d)20\d{2}(?!\d)", title_text))
    year = text_fact("tax_year", year_candidates)
    employee_ssn = text_fact("employee_ssn", [
        (f"{m[1]}-{m[2]}-{m[3]}", t) for t, m in ssns], required=False)
    ein = text_fact("employer_ein", [(m[0], t) for t in tokens for m in EIN.finditer(t.text)], required=False)

    amounts: dict[str, MoneyFact] = {}
    for box, pattern in LABELS.items():
        labels = [t for t in tokens if _matches(t, pattern)]
        if not labels:
            if box in {"1", "2"}:
                issues.append(Issue(code="missing_box",
                    field=f"box_{box}", message=f"Box {box} needs one clearly identified label. Use one W-2 copy per image."))
            continue
        if len(labels) > 1:
            issues.append(Issue(code="multiple_copies", field=f"box_{box}",
                message=f"Box {box} has multiple labels. Use one W-2 copy per image."))
            continue
        label = labels[0]
        # A merged label containing the next box label is unsafe to partition.
        if sum(_matches(label, p.lstrip("^")) for p in LABELS.values()) > 1:
            issues.append(Issue(code="merged_labels", field=f"box_{box}",
                message="Adjacent box labels merged during OCR. Supply a higher-resolution crop."))
            continue
        region = regions[label]
        content = [t for t in tokens if t is not label and _inside(t, region)]
        candidates = [t for t in content if t in money_values]
        unreadable = [t for t in content if t not in money_values
            and re.sub(r"[^a-z0-9]", "", t.text.lower()) not in LABEL_CONTINUATIONS]
        if unreadable:
            issues.append(Issue(code="invalid_amount", field=f"box_{box}",
                message=f"Box {box} contains unreadable or unexpected content. Verify the image; do not treat it as blank."))
            continue
        if not candidates:
            if box in {"1", "2"}:
                issues.append(Issue(code="missing_amount",
                    field=f"box_{box}", message=f"Box {box} has no unique readable amount. Blank does not mean zero."))
            continue
        if len(candidates) > 1:
            issues.append(Issue(code="ambiguous_amount", field=f"box_{box}",
                message=f"Box {box} has multiple amounts. Verify the image before continuing."))
            continue
        candidate = candidates[0]
        if min(label.confidence, candidate.confidence) < min_confidence:
            issues.append(Issue(code="low_confidence", field=f"box_{box}",
                message=f"Box {box} is below the OCR confidence threshold. Ask for verification."))
            continue
        amounts[box] = MoneyFact(value=money_values[candidate],
            source=source(box, [label, candidate]))

    return ExtractionResult(document_id=document_id, sha256=sha256,
        status="needs_review" if issues else "extracted",
        record=W2Record(tax_year=year, employee_ssn=employee_ssn,
            employer_ein=ein, amounts=amounts), issues=tuple(issues))


def extract_w2(path: str | Path, document_id: str, *, engine: OCREngine | None = None,
               min_confidence: float = .90) -> ExtractionResult:
    """Read real image bytes; never consult expected JSON or a fixture filename."""
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1.")
    try:
        raw, image = load_image(path)
    except (OSError, ValueError):
        # Fixed messages avoid echoing a path or document content into a trace.
        return ExtractionResult(document_id=document_id, status="rejected",
            issues=(Issue(code="invalid_image", message="Use an accessible single PNG, JPEG, or WEBP image under the size limits."),))
    digest = hashlib.sha256(raw).hexdigest()
    reader = RapidOCREngine() if engine is None else engine
    tokens = reader.read(image)
    return transcribe_tokens(tokens, document_id=document_id, sha256=digest,
        image_size=image.size, engine=reader.name, min_confidence=min_confidence)
