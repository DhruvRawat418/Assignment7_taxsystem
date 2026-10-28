"""Standalone Eligibility & Rules provider; no arithmetic and no taxpayer dialogue.

Use `eligibility(state)` as the `rules` provider, or `make_eligibility_node()`
to bind an optional LLM. The agent reads `intake_snapshot` and `extractions`
and returns a `ProviderResult`. It never computes a dollar amount, never speaks
to the taxpayer, never mutates state and never decides the next node: a scope
problem returns `needs_human_review` and a missing fact returns `needs_input`,
and the Orchestrator routes from there.

Rule evaluation is deterministic. "Must cite" is only meaningful if a citation
is verifiable, so every clearance citation and box disposition is built through
`cite()`, which raises on an id that is not in the corpus; a fabricated
authority cannot be constructed. A model is used in exactly one place,
`scope_sentinel`, where free text has to be classified: its output is
constrained to corpus ids, anything unverifiable escalates, and it decides
nothing on its own.
"""
from copy import deepcopy

from pydantic import ValidationError

from src.agents.eligibility_contract import (
    IntakeFacts, NotUsedBox, RulesOutput, SCOPE_FLAGS, UseBox, profile_from_facts,
)
from src.agents.eligibility_rules import (
    W2_LINE_BOXES, W2_NOT_USED, cite, corpus_for_prompt, describe, get_rule, validate_rule_ids,
)
from src.agents.computation_contract import RulesClearance
from src.document_extraction.models import ExtractionResult
from src.integration.contracts import ProviderResult

# Clearance for an ordinary cleared return. Each id is the authority for a
# decision Computation will rely on and Audit will check.
BASE_CITATIONS = (
    "SR-ELIG-01", "FS-01", "SD-01", "SD-02", "SD-03", "SD-04", "ESD-01", "ESD-03", "ESD-04",
    "SSA-01", "SCOPE-01",
)

# Issue codes must match the Orchestrator's [a-z][a-z_]{0,63} pattern.
SCOPE_ISSUES = (
    ("wants_to_itemize", "itemized_deductions_out_of_scope",
     "The taxpayer wants to itemise deductions", ("SD-05", "SCOPE-02")),
    ("has_self_employment_income", "self_employment_income_out_of_scope",
     "Self-employment or business income was reported", ("SCOPE-03",)),
    ("has_rental_income", "rental_income_out_of_scope",
     "Rental income was reported", ("SCOPE-04",)),
    ("has_capital_gains", "capital_gains_out_of_scope",
     "Capital gains requiring Schedule D were reported", ("SCOPE-05",)),
    ("has_digital_assets", "digital_assets_out_of_scope",
     "Digital assets were reported", ("SCOPE-05",)),
    ("has_foreign_income_or_accounts", "foreign_income_out_of_scope",
     "Foreign income or foreign accounts were reported", ("SCOPE-06",)),
    ("is_amended_or_prior_year", "amended_or_prior_year_out_of_scope",
     "This is an amended or prior-year return", ("SCOPE-07",)),
    ("needs_state_return", "state_return_out_of_scope",
     "A state return was requested", ("SCOPE-07",)),
    ("requested_advice", "tax_advice_requested",
     "The taxpayer asked a question that calls for tax advice", ("ADVICE-01",)),
    ("third_party_pressure_observed", "possible_exploitation",
     "A possible indication of third-party pressure was observed", ("HITL-02",)),
)


class Blocker:
    """One reason clearance is withheld, with the authority for withholding it."""

    __slots__ = ("code", "detail", "citations")

    def __init__(self, code, detail, *rule_ids):
        self.code, self.detail, self.citations = code, detail, cite(*rule_ids)

    def condition(self):
        return f"{self.code}: {self.detail} [{', '.join(self.citations)}]"


def read_facts(state):
    """Parse the facts this agent needs. Returns (facts, missing_keys, invalid)."""
    snapshot = state.get("intake_snapshot") or {}
    raw = snapshot.get("facts") if isinstance(snapshot, dict) else None
    if not isinstance(raw, dict):
        return None, ["filing_status"], None
    known = set(IntakeFacts.model_fields)
    missing = [key for key in IntakeFacts.required_keys() if raw.get(key) is None]
    if missing:
        return None, missing, None
    try:
        return IntakeFacts.model_validate({k: v for k, v in raw.items() if k in known}), [], None
    except ValidationError as error:
        return None, [], error


# --- Rule checks. Each is pure and returns a list of Blocker. ---------------


def check_filing_status(facts):
    if facts.spouse_died_during_tax_year or facts.taxpayer_died_during_tax_year:
        return [Blocker("filing_status_ambiguous",
                        "A spouse died during the tax year, so married filing jointly, "
                        "qualifying surviving spouse and single may each be correct",
                        "FS-02")]
    return []


def check_sr_eligibility(facts):
    eligible = facts.is_65_or_older("taxpayer") or (
        facts.filing_status == "mfj" and facts.is_65_or_older("spouse"))
    if eligible:
        return []
    return [Blocker("not_eligible_for_1040sr",
                    "Nobody on this return was born before 2 January 1961",
                    "SR-ELIG-01", "SR-ELIG-02")]


def check_deduction_chart(facts):
    blockers = []
    if facts.taxpayer_can_be_claimed_as_dependent:
        blockers.append(Blocker("claimed_as_dependent",
                                "The taxpayer can be claimed as a dependent", "SD-04"))
    if facts.taxpayer_dual_status_alien:
        blockers.append(Blocker("dual_status_alien",
                                "The taxpayer was a dual-status alien", "SD-04"))
    if facts.filing_status == "mfs" and facts.separate_spouse_itemizes:
        blockers.append(Blocker("separate_spouse_itemizes",
                                "A separately-filing spouse itemises", "SD-04"))
    return blockers


def check_separate_return_spouse_boxes(facts):
    """Spouse boxes on a separate return are flagged, never assumed either way.

    Computation's Profile carries `mfs_spouse_allowance_approved` precisely so
    this agent can decline to approve it. Whether the boxes may be counted
    depends on facts outside the stated scope, so a human decides.
    """
    if facts.filing_status != "mfs":
        return []
    if not (facts.is_65_or_older("spouse") or facts.spouse_blind):
        return []
    return [Blocker("separate_return_spouse_boxes",
                    "Spouse age or blindness was reported on a separate return and counting "
                    "those boxes needs explicit approval",
                    "SD-06", "HITL-03")]


def check_intake_scope(facts):
    return [Blocker(code, detail, *rules)
            for flag, code, detail, rules in SCOPE_ISSUES if getattr(facts, flag)]


def line_12d_boxes(facts):
    """The boxes this return checks, for the report and the dashboard.

    The count is informational here: Computation derives the deduction from the
    four Profile booleans, so this must never become a second source of truth.
    """
    spouse_applicable = facts.filing_status in ("mfj", "mfs")
    boxes = []
    if facts.is_65_or_older("taxpayer"):
        boxes.append("taxpayer_65_or_older")
    if facts.taxpayer_blind:
        boxes.append("taxpayer_blind")
    if spouse_applicable and facts.is_65_or_older("spouse"):
        boxes.append("spouse_65_or_older")
    if spouse_applicable and facts.spouse_blind:
        boxes.append("spouse_blind")
    return boxes


def disposition_for_box(box):
    """Return the decision for one W-2 box, or None if nobody has classified it."""
    if box in W2_LINE_BOXES:
        return UseBox(line=W2_LINE_BOXES[box])
    rule_id = W2_NOT_USED.get(box)
    if rule_id is None:
        return None
    rule = get_rule(rule_id)
    return NotUsedBox(reason=rule.text, citations=cite(rule_id))


def build_box_dispositions(state):
    """Decide every extracted box for every active document.

    The adapter requires the disposition keys to equal the extracted boxes
    exactly, so an unrecognised box blocks rather than being dropped: a box
    nobody has classified might be taxable, and guessing is the failure that
    matters here.
    """
    documents = state.get("documents") or []
    extractions = state.get("extractions") or {}
    dispositions, blockers = {}, []

    for request in documents:
        document_id = request.get("document_id") if isinstance(request, dict) else None
        if not document_id:
            blockers.append(Blocker("invalid_document_request",
                                    "A document request carried no document id", "SCOPE-01"))
            continue
        raw = extractions.get(document_id)
        if raw is None:
            blockers.append(Blocker("extraction_missing",
                                    f"No extraction was supplied for {document_id}", "SCOPE-01"))
            continue
        try:
            extraction = ExtractionResult.model_validate(raw)
        except ValidationError:
            blockers.append(Blocker("extraction_unreadable",
                                    f"The extraction for {document_id} did not validate",
                                    "SCOPE-01"))
            continue
        if extraction.status != "extracted" or extraction.issues or extraction.record is None:
            blockers.append(Blocker("document_requires_attention",
                                    f"The extraction for {document_id} is not clear of issues",
                                    "SCOPE-01"))
            continue

        decisions, unknown = {}, []
        for box in extraction.record.amounts:
            decision = disposition_for_box(box)
            if decision is None:
                unknown.append(box)
            else:
                decisions[box] = decision
        if unknown:
            blockers.append(Blocker(
                "unrecognized_document_box",
                f"{document_id} carries box(es) {', '.join(sorted(unknown))}, which this scope "
                "does not classify", "SCOPE-01", "HITL-03"))
            continue
        for required in ("1", "2"):
            if required not in decisions:
                blockers.append(Blocker(
                    "incomplete_w2", f"{document_id} is missing box {required}",
                    "W2-BOX-01" if required == "1" else "W2-BOX-02"))
        dispositions[document_id] = decisions

    return dispositions, blockers


# --- The one place a model is used. ----------------------------------------

SENTINEL_SYSTEM = """You classify free-text notes from a tax intake conversation against a \
fixed list of out-of-scope rules.

Rules:
{corpus}

You do not interpret tax law, give advice, or decide anything about the return. You only report \
which listed rule a note may implicate.

Return a rule_id only from the list above. If a note is ambiguous, or you are not confident, set \
uncertain to true rather than guessing. Flagging for a human is a correct answer."""


def scope_sentinel(notes, llm=None):
    """Classify free-text notes. Unverifiable output escalates, never decides."""
    notes = [n for n in notes if isinstance(n, str) and n.strip()]
    if not notes:
        return []
    if llm is None:
        return [Blocker("unclassified_free_text",
                        "Free-text notes were captured but no classifier is configured",
                        "HITL-03")]

    from pydantic import BaseModel

    class ScopeSignal(BaseModel):
        rule_id: str
        note: str
        confidence: str

    class ScopeAssessment(BaseModel):
        signals: list[ScopeSignal] = []
        uncertain: bool = False

    try:
        result = llm.with_structured_output(ScopeAssessment).invoke([
            {"role": "system",
             "content": SENTINEL_SYSTEM.format(corpus=corpus_for_prompt("SCOPE-"))},
            {"role": "user", "content": "\n".join(f"- {note}" for note in notes)},
        ])
    except Exception:
        return [Blocker("scope_classifier_failed",
                        "Free-text notes could not be classified", "HITL-03")]

    known, unknown = validate_rule_ids([signal.rule_id for signal in result.signals])
    blockers = [Blocker("free_text_out_of_scope", signal.note.strip()[:200], signal.rule_id)
                for signal in result.signals
                if signal.rule_id in known and signal.confidence == "high"]
    if unknown or result.uncertain:
        blockers.append(Blocker("unclassified_free_text",
                                "Free-text notes could not be classified with confidence",
                                "HITL-03"))
    return blockers


# --- The provider. ----------------------------------------------------------


def eligibility(state, llm=None):
    """Return a ProviderResult for the `rules` stage.

    `ready` carries the full packet. `needs_input` sends the case back to
    Intake for a fact this agent cannot supply. `needs_human_review` carries
    the blocking conditions. Nothing here chooses the next node.
    """
    if not isinstance(state, dict):
        return ProviderResult(status="failed", issue_codes=("invalid_state",))

    facts, missing, invalid = read_facts(state)
    if missing:
        return ProviderResult(status="needs_input", issue_codes=("missing_intake_fact",),
                              data={"missing_facts": sorted(missing)})
    if invalid is not None or facts is None:
        return ProviderResult(status="needs_input", issue_codes=("invalid_intake_fact",),
                              data={"detail": "Intake facts did not validate"})

    blockers = []
    for check in (check_filing_status, check_sr_eligibility, check_deduction_chart,
                  check_separate_return_spouse_boxes, check_intake_scope):
        blockers.extend(check(facts))
    dispositions, document_blockers = build_box_dispositions(state)
    blockers.extend(document_blockers)
    blockers.extend(scope_sentinel(facts.free_text_notes, llm=llm))

    if blockers:
        return ProviderResult(
            status="needs_human_review",
            issue_codes=tuple(dict.fromkeys(blocker.code for blocker in blockers))[:128],
            data={"blocking_conditions": [blocker.condition() for blocker in blockers],
                  "citations": sorted({c for blocker in blockers for c in blocker.citations})},
        )

    try:
        output = RulesOutput(
            profile=profile_from_facts(facts, mfs_spouse_allowance_approved=False),
            clearance=RulesClearance(approved=True, citations=list(cite(*BASE_CITATIONS)),
                                     blocking_conditions=[]),
            box_dispositions=dispositions,
        )
    except ValidationError:
        return ProviderResult(status="failed", issue_codes=("rules_output_invalid",))

    packet = output.as_packet()
    packet["line_12d_boxes"] = line_12d_boxes(facts)
    return ProviderResult(status="ready", data=packet)


def make_eligibility_node(llm=None):
    """Bind an optional classifier. Without one, free text escalates."""
    def node(state):
        return eligibility(state, llm=llm)
    return node


def explain(rule_id):
    """Rule text for the dashboard, so a citation renders as something readable."""
    return deepcopy(describe(rule_id))
