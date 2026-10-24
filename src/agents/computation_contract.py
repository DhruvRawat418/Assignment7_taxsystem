"""Boundary owned by Computation; does not prescribe the team's global state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, model_validator


def parse_money(value: object) -> Decimal:
    # JSON decimal strings are intentional: never accept binary floating-point money.
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Use a decimal string or integer for money")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid decimal amount") from None
    if not amount.is_finite() or abs(amount) >= Decimal("1000000000000"):
        raise ValueError("Amount must be finite and below one trillion dollars")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Money may have at most two decimal places")
    return amount


Money = Annotated[Decimal, BeforeValidator(parse_money)]
FilingStatus = Literal["single", "mfj", "mfs", "hoh", "qss"]

# Each key must be present. Absence and a user-confirmed zero are different.
# Values are lists so multiple W-2s/1099s are summed by an MCP tool, not Extraction.
INPUT_LINES = (
    "1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a",
    "8", "10", "17", "19", "20", "23", "25a", "25b", "25c", "26", "32",
    "ss_adjustments",
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(ContractModel):
    kind: Literal["document", "user_input"]
    reference: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=200)
    entered_by: str | None = Field(default=None, min_length=1, max_length=100)
    recorded_at: datetime | None = None

    @model_validator(mode="after")
    def require_input_audit(self) -> Source:
        if self.kind == "user_input":
            if self.entered_by is None or self.recorded_at is None:
                raise ValueError("Direct input needs entered_by and recorded_at")
            if self.recorded_at.utcoffset() is None:
                raise ValueError("recorded_at must include a timezone")
        return self


class SourcedAmount(ContractModel):
    value: Money
    sources: list[Source] = Field(min_length=1)


class Profile(ContractModel):
    filing_status: FilingStatus
    taxpayer_65_or_older: StrictBool
    # All four checkbox answers are explicit. Unknown must not become False.
    # Use False for spouse fields only when Rules confirms they are inapplicable.
    taxpayer_blind: StrictBool
    spouse_65_or_older: StrictBool
    spouse_blind: StrictBool
    # Required for MFS because Social Security taxation changes with this answer.
    mfs_lived_with_spouse: StrictBool | None = None
    # Rules must explicitly approve counting spouse boxes on an MFS return.
    mfs_spouse_allowance_approved: StrictBool = False

    @model_validator(mode="after")
    def coherent_profile(self) -> Profile:
        if self.filing_status == "mfs" and self.mfs_lived_with_spouse is None:
            raise ValueError("MFS requires mfs_lived_with_spouse")
        if self.filing_status not in ("mfj", "mfs"):
            if self.spouse_65_or_older or self.spouse_blind:
                raise ValueError("Spouse boxes require MFJ or MFS")
        if self.filing_status != "mfs" and self.mfs_spouse_allowance_approved:
            raise ValueError("MFS spouse approval is only applicable to MFS")
        return self


class RulesClearance(ContractModel):
    """Supplied by Eligibility & Rules, never invented by Computation."""

    approved: StrictBool
    citations: list[Annotated[str, Field(min_length=1, pattern=r"\S")]] = Field(min_length=1)
    blocking_conditions: list[str] = Field(default_factory=list)


class ComputationRequest(ContractModel):
    tax_year: Literal[2025]
    profile: Profile
    rules: RulesClearance
    amounts: dict[str, list[SourcedAmount]]

    @model_validator(mode="after")
    def complete_inputs(self) -> ComputationRequest:
        if set(self.amounts) != set(INPUT_LINES):
            missing = sorted(set(INPUT_LINES) - set(self.amounts))
            extra = sorted(set(self.amounts) - set(INPUT_LINES))
            raise ValueError(f"Input line mismatch; missing={missing}; extra={extra}")
        for line, entries in self.amounts.items():
            if not entries:
                raise ValueError(f"Line {line} needs an amount, including sourced zero")
            if line != "8" and any(item.value < 0 for item in entries):
                raise ValueError(f"Line {line} cannot be negative")
        return self


class ToolCall(ContractModel):
    call_id: str
    output_key: str
    tool: str
    arguments: dict
    result: dict


class ComputedLine(ContractModel):
    value: Money
    tool_call_id: str
    depends_on: list[str]
    sources: list[Source]
    rule_references: list[str]


class Issue(ContractModel):
    code: str
    message: str


class ComputationResult(ContractModel):
    status: Literal["completed", "needs_human_review", "invalid_input", "tool_error"]
    tax_year: Literal[2025] = 2025
    lines: dict[str, ComputedLine] = Field(default_factory=dict)
    # Audit-only working values, never fields to render on the tax form.
    intermediates: dict[str, ComputedLine] = Field(default_factory=dict)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    # All successful results are drafts for Review, never filing instructions.
    draft_only: Literal[True] = True
