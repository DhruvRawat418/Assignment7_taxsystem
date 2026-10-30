"""Probes that check whether each registered guardrail actually fires.

A probe does not assert; it reports. Every probe returns a `ProbeResult` and
never raises, because this harness has to run against a partial system: on a
branch where Computation is absent, "P1 cannot be checked here" is a true and
useful answer, while an ImportError is neither.

Three outcomes:

    PASS    the enforcement point exists and fired on a hostile input
    FAIL    the enforcement point exists and did not fire — a real defect
    ABSENT  the component is not in this checkout, so nothing was checked

ABSENT is not a pass. The conformance report counts it separately so that
coverage cannot be inflated by running the harness somewhere the agents are
missing.

Probes deliberately exercise behaviour rather than inspecting source text. A
probe that greps for a function name proves nothing about whether the guardrail
works; one that feeds in a rejected SSN and checks what comes back does.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSENT = "absent"


@dataclass(frozen=True)
class ProbeResult:
    outcome: Outcome
    detail: str

    @property
    def ok(self) -> bool:
        return self.outcome is not Outcome.FAIL


def _absent(what: str) -> ProbeResult:
    return ProbeResult(Outcome.ABSENT, f"{what} is not present in this checkout")


def _passed(detail: str) -> ProbeResult:
    return ProbeResult(Outcome.PASS, detail)


def _failed(detail: str) -> ProbeResult:
    return ProbeResult(Outcome.FAIL, detail)


# --- Fixtures the probes feed in. Kept local so the harness has no test dep. --

SHA = "c" * 64


def _source(document_id: str, box: str) -> dict:
    return dict(document_id=document_id, sha256=SHA, page=1, box=box,
                bbox=[0, 0, 10, 10], image_size=[100, 100], raw_text="synthetic",
                confidence=1.0, agent="document_extraction", engine="probe",
                timestamp="2026-10-28T00:00:00Z")


def _extraction(document_id: str = "w2-1", boxes: dict | None = None) -> dict:
    boxes = {"1": "50000.00", "2": "4000.00"} if boxes is None else boxes
    return dict(document_id=document_id, sha256=SHA, status="extracted", issues=[],
                record=dict(document_type="W-2",
                            tax_year=dict(value="2025",
                                          source=_source(document_id, "tax_year")),
                            amounts={box: dict(value=value, origin="document",
                                               source=_source(document_id, box))
                                     for box, value in boxes.items()}))


INPUT_LINES = ("1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a",
               "8", "10", "17", "19", "20", "23", "25a", "25b", "25c", "26", "32",
               "ss_adjustments")


def _intake_amounts(from_documents: bool = True) -> dict:
    owned = set(INPUT_LINES) - ({"1z", "25a"} if from_documents else set())
    return {line: [dict(value="0.00", sources=[dict(
        kind="user_input", reference="probe", field="confirmed " + line,
        entered_by="guardrail-probe", recorded_at="2026-10-28T00:00:00Z")])]
        for line in sorted(owned)}


def case_state(**facts) -> dict:
    """A clean, in-scope case. Probes mutate one thing and expect a block."""
    base = dict(filing_status="single", taxpayer_date_of_birth="1952-04-09",
                taxpayer_blind=False)
    base.update(facts)
    return dict(
        case_id="guardrail-probe", mode="live", status="running", next_stage="rules",
        intake_snapshot=dict(facts=base, amounts=_intake_amounts(),
                             documents=[dict(document_id="w2-1", path="/tmp/w2-1.jpg")]),
        documents=[dict(document_id="w2-1", path="/tmp/w2-1.jpg")],
        extractions={"w2-1": _extraction()},
        rules_output={}, issues=[], events=[],
    )


def _eligibility():
    try:
        from src.agents.eligibility import eligibility
        return eligibility
    except Exception:
        return None


def _blocks(result, expected_code: str | None = None) -> bool:
    if result is None or result.status != "needs_human_review":
        return False
    return expected_code is None or expected_code in result.issue_codes


# --- Prohibitions -----------------------------------------------------------


def probe_draft_only() -> ProbeResult:
    """P1: a computation result cannot claim to be anything but a draft."""
    try:
        from pydantic import ValidationError
        from src.agents.computation_contract import ComputationResult
    except Exception:
        return _absent("Computation contract")
    try:
        ComputationResult.model_validate(dict(status="completed", draft_only=False))
    except ValidationError:
        return _passed("ComputationResult rejects draft_only=False")
    except Exception as error:  # unexpected, but still not a silent pass
        return _failed(f"unexpected error validating a non-draft result: {error!r}")
    return _failed("ComputationResult accepted draft_only=False")


def probe_sourced_amounts() -> ProbeResult:
    """P3: an amount with no source cannot be constructed."""
    try:
        from pydantic import ValidationError
        from src.agents.computation_contract import SourcedAmount
    except Exception:
        return _absent("Computation contract")
    try:
        SourcedAmount.model_validate(dict(value="100.00", sources=[]))
    except ValidationError:
        return _passed("SourcedAmount rejects an empty source list")
    except Exception as error:
        return _failed(f"unexpected error validating an unsourced amount: {error!r}")
    return _failed("SourcedAmount accepted an amount with no sources")


def probe_citation_integrity() -> ProbeResult:
    """P6: an authority outside the corpus cannot be cited."""
    try:
        from src.agents.eligibility_rules import UnknownRuleError, cite
    except Exception:
        return _absent("Eligibility reference corpus")
    try:
        cite("NOT-A-REAL-RULE-01")
    except UnknownRuleError:
        pass
    except Exception as error:
        return _failed(f"cite() raised an unexpected error: {error!r}")
    else:
        return _failed("cite() accepted an id that is not in the corpus")
    try:
        cite()
    except UnknownRuleError:
        return _passed("cite() rejects both unknown ids and empty citations")
    except Exception as error:
        return _failed(f"cite() raised an unexpected error on no arguments: {error!r}")
    return _failed("cite() allowed a determination with no citation at all")


def probe_scope_escalation() -> ProbeResult:
    """P5 / E1: an out-of-scope item stops the case."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    result = eligibility(case_state(has_rental_income=True))
    if _blocks(result, "rental_income_out_of_scope"):
        return _passed("rental income blocks with rental_income_out_of_scope")
    return _failed(f"rental income did not block; status={getattr(result, 'status', None)}")


def probe_advice_escalation() -> ProbeResult:
    """P2 / E4: a request for advice stops the case."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    result = eligibility(case_state(requested_advice=True))
    if _blocks(result, "tax_advice_requested"):
        return _passed("an advice request blocks with tax_advice_requested")
    return _failed("an advice request did not block")


def probe_escalation_surface() -> ProbeResult:
    """P4: a blocking result names its conditions and their authority."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    result = eligibility(case_state(has_rental_income=True, requested_advice=True))
    if not _blocks(result):
        return _failed("two out-of-scope signals did not produce a block")
    conditions = result.data.get("blocking_conditions") or []
    citations = result.data.get("citations") or []
    if len(conditions) >= 2 and citations:
        return _passed(f"{len(conditions)} conditions reported with {len(citations)} citations")
    return _failed("a blocking result carried no conditions or no citations")


# --- Identifiers ------------------------------------------------------------

REAL_LOOKING_SSN = "123-45-6789"
SYNTHETIC_SSN = "901-23-4567"


def probe_ssn_range() -> ProbeResult:
    """I1: only 900-999 area numbers are accepted."""
    try:
        from src.document_extraction.validation import validate_synthetic_ssn
    except Exception:
        return _absent("SSN validation helper")
    try:
        validate_synthetic_ssn(REAL_LOOKING_SSN)
    except ValueError:
        pass
    except Exception as error:
        return _failed(f"validator raised an unexpected error: {error!r}")
    else:
        return _failed("validator accepted an SSN outside the 900-999 range")
    try:
        validate_synthetic_ssn(SYNTHETIC_SSN)
    except Exception as error:
        return _failed(f"validator rejected a valid synthetic SSN: {error!r}")
    return _passed("rejects a real-looking SSN, accepts a 900-series one")


def probe_ssn_not_echoed() -> ProbeResult:
    """I2: the rejected value never appears in the error text."""
    try:
        from src.document_extraction.validation import validate_synthetic_ssn
    except Exception:
        return _absent("SSN validation helper")
    try:
        validate_synthetic_ssn(REAL_LOOKING_SSN)
    except ValueError as error:
        text = str(error)
        digits = REAL_LOOKING_SSN.replace("-", "")
        if REAL_LOOKING_SSN in text or digits in text:
            return _failed("the rejected identifier appears in the error message")
        return _passed("the rejected identifier does not appear in the error message")
    except Exception as error:
        return _failed(f"validator raised an unexpected error: {error!r}")
    return _failed("validator did not reject a real-looking SSN at all")


# --- Escalation conditions --------------------------------------------------


def probe_document_conflict() -> ProbeResult:
    """E2: a document that is not clear of issues stops the case."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    state = case_state()
    state["extractions"]["w2-1"]["issues"] = [
        dict(code="low_confidence", field="1", message="unclear")]
    if _blocks(eligibility(state), "document_requires_attention"):
        return _passed("a document carrying issues blocks the case")
    return _failed("a document carrying issues did not block")


def probe_1099r_rule() -> ProbeResult:
    """E3: a checked box survives Intake and blocks through the Rules fallback.

    This does not claim a dedicated 1099-R OCR/disposition implementation.
    """
    try:
        from src.agents.eligibility_rules import RULES
        from src.agents.intake import initial_intake_state, provenance
        from src.agents.intake_contract import _facts
    except Exception:
        return _absent("Intake contract or Eligibility reference corpus")
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    if "SCOPE-08" not in RULES:
        return _failed("no corpus rule covers a 1099-R with box 2b checked")
    session = initial_intake_state()
    session['answers'] = {
        'filing_status': provenance('single', 'Synthetic guardrail probe', 'guardrail-probe'),
        'documents': provenance(['1099-R'], 'Synthetic guardrail probe', 'guardrail-probe'),
        'r_box2b': provenance(True, 'Synthetic guardrail probe', 'guardrail-probe'),
    }
    facts = _facts(session)
    if not any('1099-R box 2b' in note for note in facts.get('free_text_notes', [])):
        return _failed("Intake dropped the checked 1099-R box 2b signal")
    if _blocks(eligibility(case_state(**facts)), 'unclassified_free_text'):
        return _passed("Intake retains box 2b; Rules blocks via unclassified_free_text fallback, not a dedicated disposition")
    return _failed("a checked 1099-R box 2b passed the integrated Intake/Rules boundary")


def probe_filing_status_ambiguity() -> ProbeResult:
    """E5: bereavement stops the case before a status is chosen."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    result = eligibility(case_state(filing_status="mfj",
                                    spouse_date_of_birth="1955-01-03",
                                    spouse_blind=False,
                                    spouse_died_during_tax_year=True))
    if not _blocks(result, "filing_status_ambiguous"):
        return _failed("a spouse who died during the tax year did not block")
    if "filing_status.validated" in str(result.data):
        return _failed("a filing status was validated despite the ambiguity")
    return _passed("blocks without choosing a filing status")


def probe_exploitation() -> ProbeResult:
    """E6: a pressure signal stops the case and is phrased as an observation."""
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    result = eligibility(case_state(third_party_pressure_observed=True))
    if not _blocks(result, "possible_exploitation"):
        return _failed("a third-party pressure signal did not block")
    conditions = " ".join(result.data.get("blocking_conditions") or [])
    verdicts = ("fraud", "abuse", "scam", "criminal", "guilty")
    if any(word in conditions.lower() for word in verdicts):
        return _failed("the finding reads as a verdict rather than an observation")
    return _passed("blocks with an observation, not a verdict")


# --- Orchestration safety ---------------------------------------------------


def probe_loop_guard() -> ProbeResult:
    """O1: the graph exposes bounded hops, review attempts and progress."""
    try:
        import inspect
        from src.integration.graph import build_graph
    except Exception:
        return _absent("Integration graph")
    parameters = inspect.signature(build_graph).parameters
    required = ("max_hops", "max_review_attempts", "no_progress_limit")
    missing = [name for name in required if name not in parameters]
    if missing:
        return _failed(f"graph has no {', '.join(missing)}")
    try:
        build_graph(max_hops=0)
    except ValueError:
        return _passed("hop, review and progress limits exist and are validated")
    except Exception as error:
        return _failed(f"unexpected error validating limits: {error!r}")
    return _failed("graph accepted a zero hop limit")


def probe_clearance_required() -> ProbeResult:
    """O2: an uncleared packet cannot reach Computation."""
    try:
        from src.integration.adapters import prepare_packet
        from src.integration.contracts import IntegrationError
    except Exception:
        return _absent("Integration adapters")
    eligibility = _eligibility()
    if eligibility is None:
        return _absent("Eligibility & Rules")
    state = case_state()
    data = eligibility(state).data
    if "clearance" not in data:
        return _failed("a clean case did not produce a clearance to test")
    data = dict(data)
    data["clearance"] = dict(approved=False, citations=["SCOPE-04"],
                             blocking_conditions=["withheld for the probe"])
    try:
        prepare_packet(state["intake_snapshot"],
                       {k: data[k] for k in ("profile", "clearance", "box_dispositions")},
                       state["extractions"])
    except IntegrationError as error:
        if error.code == "rules_not_cleared":
            return _passed("prepare_packet refuses an uncleared packet")
        return _failed(f"refused for the wrong reason: {error.code}")
    except Exception as error:
        return _failed(f"unexpected error: {error!r}")
    return _failed("prepare_packet accepted a packet Rules had not cleared")


PROBES: dict[str, Callable[[], ProbeResult]] = {
    "probe_draft_only": probe_draft_only,
    "probe_sourced_amounts": probe_sourced_amounts,
    "probe_citation_integrity": probe_citation_integrity,
    "probe_scope_escalation": probe_scope_escalation,
    "probe_advice_escalation": probe_advice_escalation,
    "probe_escalation_surface": probe_escalation_surface,
    "probe_ssn_range": probe_ssn_range,
    "probe_ssn_not_echoed": probe_ssn_not_echoed,
    "probe_document_conflict": probe_document_conflict,
    "probe_1099r_rule": probe_1099r_rule,
    "probe_filing_status_ambiguity": probe_filing_status_ambiguity,
    "probe_exploitation": probe_exploitation,
    "probe_loop_guard": probe_loop_guard,
    "probe_clearance_required": probe_clearance_required,
}


def run(probe_name: str) -> ProbeResult:
    probe = PROBES.get(probe_name)
    if probe is None:
        return _failed(f"{probe_name!r} is registered but not implemented")
    try:
        return probe()
    except Exception as error:  # a probe must never take the harness down
        return _failed(f"probe raised: {error!r}")
