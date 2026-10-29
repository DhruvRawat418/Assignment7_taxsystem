"""Boundary owned by Eligibility & Rules; does not prescribe the team's global state.

Two directions are defined here.

Upstream: `IntakeFacts` is the subset of `intake_snapshot["facts"]` this agent
reads. Intake owns the dialogue; this agent owns what the answers mean. The
four line 12d checkbox answers are required rather than defaulted, because an
unknown answer must not silently become False.

Downstream: `RulesOutput` is the `rules_output` packet the Orchestrator stores
and `prepare_packet` validates. Its `profile` and `clearance` are revalidated
against Computation's own `Profile` and `RulesClearance`, so a drift between
the two contracts fails here rather than inside the computation node.
"""
from __future__ import annotations

from datetime import date
from src.agents.dependent_contract import DependentDetails
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from src.agents.computation_contract import FilingStatus, Profile, RulesClearance

# Born before this date is 65 or older for tax year 2025.
SR_BIRTHDATE_CUTOFF = date(1961, 1, 2)

# Scope questions Intake asks. Absent means not reported; each is a plain
# yes/no the taxpayer can answer without reading the brief.
SCOPE_FLAGS = (
    "wants_to_itemize",
    "has_self_employment_income",
    "has_rental_income",
    "has_capital_gains",
    "has_digital_assets",
    "has_foreign_income_or_accounts",
    "is_amended_or_prior_year",
    "needs_state_return",
    "separate_spouse_itemizes",
    "requested_advice",
    "third_party_pressure_observed",
    "taxpayer_can_be_claimed_as_dependent",
    "taxpayer_dual_status_alien",
    "spouse_died_during_tax_year",
    "taxpayer_died_during_tax_year",
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntakeFacts(ContractModel):
    """What this agent reads from `intake_snapshot["facts"]`.

    Extra keys are ignored by `from_snapshot` rather than rejected, so Intake
    can collect facts other agents need without breaking this boundary.
    """

    dependents: list[DependentDetails] = Field(default_factory=list)
    filing_status: FilingStatus
    taxpayer_date_of_birth: date
    taxpayer_blind: StrictBool
    spouse_date_of_birth: date | None = None
    spouse_blind: StrictBool | None = None
    mfs_lived_with_spouse: StrictBool | None = None

    wants_to_itemize: StrictBool = False
    has_self_employment_income: StrictBool = False
    has_rental_income: StrictBool = False
    has_capital_gains: StrictBool = False
    has_digital_assets: StrictBool = False
    has_foreign_income_or_accounts: StrictBool = False
    is_amended_or_prior_year: StrictBool = False
    needs_state_return: StrictBool = False
    separate_spouse_itemizes: StrictBool = False
    requested_advice: StrictBool = False
    third_party_pressure_observed: StrictBool = False
    taxpayer_can_be_claimed_as_dependent: StrictBool = False
    taxpayer_dual_status_alien: StrictBool = False
    spouse_died_during_tax_year: StrictBool = False
    taxpayer_died_during_tax_year: StrictBool = False

    # Anything the taxpayer said that did not fit a structured question. The
    # orchestrator's intake validator fixes the snapshot's top-level keys, so
    # free text travels inside facts rather than beside them.
    free_text_notes: list[str] = Field(default_factory=list, max_length=64)

    @classmethod
    def required_keys(cls):
        return ("filing_status", "taxpayer_date_of_birth", "taxpayer_blind")

    @model_validator(mode="after")
    def spouse_details_present(self) -> IntakeFacts:
        if self.filing_status == "mfj":
            if self.spouse_date_of_birth is None or self.spouse_blind is None:
                raise ValueError("A joint return needs spouse age and blindness")
        if self.filing_status == "mfs" and self.mfs_lived_with_spouse is None:
            raise ValueError("A separate return needs mfs_lived_with_spouse")
        return self

    def is_65_or_older(self, role: Literal["taxpayer", "spouse"]) -> bool:
        birth = self.taxpayer_date_of_birth if role == "taxpayer" else self.spouse_date_of_birth
        return birth is not None and birth < SR_BIRTHDATE_CUTOFF


class UseBox(ContractModel):
    """A W-2 box that carries an amount to a Form 1040-SR line."""

    action: Literal["use"] = "use"
    line: Literal["1z", "25a"]


class NotUsedBox(ContractModel):
    """A W-2 box deliberately excluded, with the reason and authority.

    The integration adapter requires a non-empty reason and at least one
    citation. An excluded box is never silently dropped and never assumed 0.
    """

    action: Literal["not_used"] = "not_used"
    reason: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)


class RulesOutput(ContractModel):
    """The `rules_output` packet, exactly the three keys the adapter accepts."""

    profile: Profile
    clearance: RulesClearance
    box_dispositions: dict[str, dict[str, UseBox | NotUsedBox]]

    @model_validator(mode="after")
    def cleared_output_is_complete(self) -> RulesOutput:
        if self.clearance.approved and self.clearance.blocking_conditions:
            raise ValueError("An approved clearance cannot carry blocking conditions")
        if not self.clearance.approved and not self.clearance.blocking_conditions:
            raise ValueError("A withheld clearance must name its blocking conditions")
        return self

    def as_packet(self) -> dict:
        """Render for `ProviderResult.data`, which must be plain JSON types."""
        return self.model_dump(mode="json")


def profile_from_facts(facts: IntakeFacts, *, mfs_spouse_allowance_approved: bool) -> Profile:
    """Build Computation's Profile. Age comes from the date of birth, never a
    self-reported flag, so the two cannot disagree."""
    spouse_applicable = facts.filing_status in ("mfj", "mfs")
    return Profile(
        filing_status=facts.filing_status,
        taxpayer_65_or_older=facts.is_65_or_older("taxpayer"),
        taxpayer_blind=facts.taxpayer_blind,
        spouse_65_or_older=spouse_applicable and facts.is_65_or_older("spouse"),
        spouse_blind=bool(spouse_applicable and facts.spouse_blind),
        mfs_lived_with_spouse=facts.mfs_lived_with_spouse,
        mfs_spouse_allowance_approved=(
            mfs_spouse_allowance_approved if facts.filing_status == "mfs" else False
        ),
    )
