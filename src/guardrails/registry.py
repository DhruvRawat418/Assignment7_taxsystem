"""Machine-readable register of SilverFile's guardrails; no enforcement here.

This module is the single list of what the system promises not to do. Each
entry names the assignment section it comes from, the component(s) that enforce
it, the probe that checks it, and the owner responsible.

Keeping the register as data rather than prose has one purpose: the test suite
can assert properties *about the register itself* — that every guardrail has an
enforcement point, that every one has a probe, that no id is duplicated. A
prose checklist cannot be checked that way, and a guardrail nobody checks is a
guardrail nobody has.

Status is recorded honestly. ENFORCED means a probe confirms it fires today;
PARTIAL means some enforcement points exist and others do not; OPEN means the
guardrail is specified but not yet implemented anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    ENFORCED = "enforced"
    PARTIAL = "partial"
    OPEN = "open"


class Kind(str, Enum):
    PROHIBITION = "prohibition"   # assignment section 2
    ESCALATION = "escalation"     # assignment section 4.4
    IDENTIFIER = "identifier"     # assignment section 3.2
    ORCHESTRATION = "orchestration"  # assignment section 4.1


@dataclass(frozen=True)
class Guardrail:
    id: str
    kind: Kind
    statement: str
    source: str
    # Dotted module paths that enforce this. More than one is defence in depth.
    enforcement_points: tuple[str, ...]
    probe: str
    owner: str
    status: Status
    note: str = ""
    tests: tuple[str, ...] = field(default_factory=tuple)


_GUARDRAILS: tuple[Guardrail, ...] = (
    # ---- Standing prohibitions, assignment section 2 --------------------
    Guardrail(
        "P1", Kind.PROHIBITION,
        "Never file anything. The output is a draft plus an audit record.",
        "Assignment 2",
        ("src.agents.computation_contract.ComputationResult",
         "src.agents.audit_checks"),
        "probe_draft_only", "computation", Status.ENFORCED,
        "The type cannot express a non-draft result, and Audit rejects one anyway.",
        ("tests/guardrails/test_conformance.py::test_draft_only",),
    ),
    Guardrail(
        "P2", Kind.PROHIBITION,
        "Never give tax advice, planning or optimisation.",
        "Assignment 2, 4.4(4)",
        ("src.agents.eligibility",),
        "probe_advice_escalation", "eligibility", Status.PARTIAL,
        "Rules escalates a flagged request. Detecting advice-seeking phrasing in "
        "free conversation is handled by Intake backstops, but this harness does not test every phrasing.",
        ("tests/guardrails/test_conformance.py::test_advice_escalates",),
    ),
    Guardrail(
        "P3", Kind.PROHIBITION,
        "Never assert a dollar amount the system cannot source.",
        "Assignment 2, 4.2",
        ("src.agents.computation_contract.SourcedAmount",
         "src.agents.computation_contract.ComputedLine",
         "src.agents.audit_recipe"),
        "probe_sourced_amounts", "computation", Status.ENFORCED,
        "Audit rebuilds expected tool arguments from inputs rather than trusting "
        "the arguments the computation recorded.",
        ("tests/guardrails/test_conformance.py::test_amounts_require_sources",),
    ),
    Guardrail(
        "P4", Kind.PROHIBITION,
        "Always route to a human in the escalation conditions of 4.4.",
        "Assignment 2, 4.4",
        ("src.agents.eligibility", "src.integration.graph"),
        "probe_escalation_surface", "eligibility", Status.PARTIAL,
        "See the E-series guardrails for per-condition status.",
        ("tests/guardrails/test_conformance.py::test_escalation_surface",),
    ),
    Guardrail(
        "P5", Kind.PROHIBITION,
        "Handle only the in-scope return profile of 3.3; anything else escalates.",
        "Assignment 2, 3.3",
        ("src.agents.eligibility",),
        "probe_scope_escalation", "eligibility", Status.ENFORCED,
        "Enforced over intake facts and over every extracted document box. An "
        "unclassified box blocks rather than being dropped.",
        ("tests/guardrails/test_conformance.py::test_out_of_scope_escalates",),
    ),
    Guardrail(
        "P6", Kind.PROHIBITION,
        "Never let a determination cite an authority outside the reference corpus.",
        "Assignment 4, Eligibility & Rules constraint",
        ("src.agents.eligibility_rules",),
        "probe_citation_integrity", "eligibility", Status.ENFORCED,
        "cite() raises on an unknown id, so a determination carrying an invented "
        "authority cannot be constructed.",
        ("tests/guardrails/test_conformance.py::test_citation_integrity",),
    ),
    # ---- Identifiers, assignment section 3.2 ----------------------------
    Guardrail(
        "I1", Kind.IDENTIFIER,
        "Accept only synthetic Social Security numbers in the 900-999 range.",
        "Assignment 3.2",
        ("src.document_extraction.validation.validate_synthetic_ssn",
         "src.integration.adapters._privacy_check"),
        "probe_ssn_range", "guardrails", Status.ENFORCED,
        "Enforced at entry and again on every worker payload before checkpointing.",
        ("tests/guardrails/test_conformance.py::test_ssn_range",),
    ),
    Guardrail(
        "I2", Kind.IDENTIFIER,
        "Never echo a rejected identifier into an error, log or issue message.",
        "Assignment 3.2, 4.3",
        ("src.document_extraction.validation.validate_synthetic_ssn",),
        "probe_ssn_not_echoed", "guardrails", Status.ENFORCED,
        "Exception text reaches logs and the dashboard, so the rejected value "
        "must not appear in it.",
        ("tests/guardrails/test_conformance.py::test_rejected_ssn_not_echoed",),
    ),
    # ---- Escalation conditions, assignment section 4.4 ------------------
    Guardrail(
        "E1", Kind.ESCALATION,
        "Any out-of-scope item from 3.3 escalates to a human.",
        "Assignment 4.4(1)",
        ("src.agents.eligibility",),
        "probe_scope_escalation", "eligibility", Status.ENFORCED,
        tests=("tests/guardrails/test_redteam.py",),
    ),
    Guardrail(
        "E2", Kind.ESCALATION,
        "Any unresolved conflict between a user statement and a document escalates.",
        "Assignment 4.4(2)",
        ("src.agents.eligibility", "src.agents.audit_checks"),
        "probe_document_conflict", "eligibility", Status.PARTIAL,
        "Document-internal contradictions are caught. Comparing a user statement "
        "against a document value needs Intake's facts alongside the extraction.",
    ),
    Guardrail(
        "E3", Kind.ESCALATION,
        "Any 1099-R with box 2b 'taxable amount not determined' escalates.",
        "Assignment 4.4(3), 3.3",
        ("src.agents.intake_contract", "src.agents.eligibility_rules", "src.agents.eligibility"),
        "probe_1099r_rule", "eligibility", Status.PARTIAL,
        "Intake transcribes 1099-R box 2b and Rules blocks via the generic "
        "unclassified_free_text fallback. Dedicated box-2b disposition and "
        "1099-R image extraction are not implemented.",
    ),
    Guardrail(
        "E4", Kind.ESCALATION,
        "A request for tax advice, planning or optimisation escalates.",
        "Assignment 4.4(4)",
        ("src.agents.eligibility",),
        "probe_advice_escalation", "eligibility", Status.PARTIAL,
        "Intake has advice backstops; the corpus does not verify raw-language recognition end to end.",
    ),
    Guardrail(
        "E5", Kind.ESCALATION,
        "Filing-status ambiguity escalates, above all a spouse who died in the year.",
        "Assignment 4.4(5)",
        ("src.agents.eligibility",),
        "probe_filing_status_ambiguity", "eligibility", Status.ENFORCED,
        "Short-circuits before a status is chosen: the ambiguity is the answer.",
    ),
    Guardrail(
        "E6", Kind.ESCALATION,
        "Any indication of financial exploitation or third-party pressure escalates.",
        "Assignment 4.4(6)",
        ("src.agents.eligibility",),
        "probe_exploitation", "eligibility", Status.PARTIAL,
        "Rules surfaces a flag. Observing pressure during conversation belongs to "
        "Intake backstops; this corpus tests the downstream flag only. The system notices and stops; it never "
        "adjudicates.",
    ),
    # ---- Orchestration safety, assignment section 4.1 -------------------
    Guardrail(
        "O1", Kind.ORCHESTRATION,
        "A pathological handoff cycle is detected and broken.",
        "Assignment 4.1",
        ("src.integration.graph",),
        "probe_loop_guard", "orchestrator", Status.ENFORCED,
        "Hop limit, review-attempt limit and a no-progress fingerprint that "
        "ignores changing call ids and timestamps.",
        ("tests/integration/test_graph.py",),
    ),
    Guardrail(
        "O2", Kind.ORCHESTRATION,
        "Computation never runs on a packet Rules has not cleared.",
        "Assignment 4, Computation constraint",
        ("src.integration.adapters.prepare_packet",),
        "probe_clearance_required", "orchestrator", Status.ENFORCED,
        "prepare_packet raises rules_not_cleared rather than proceeding.",
    ),
)

REGISTRY: dict[str, Guardrail] = {g.id: g for g in _GUARDRAILS}


def all_guardrails() -> tuple[Guardrail, ...]:
    return _GUARDRAILS


def by_kind(kind: Kind) -> tuple[Guardrail, ...]:
    return tuple(g for g in _GUARDRAILS if g.kind is kind)


def by_owner(owner: str) -> tuple[Guardrail, ...]:
    return tuple(g for g in _GUARDRAILS if g.owner == owner)


def get(guardrail_id: str) -> Guardrail:
    try:
        return REGISTRY[guardrail_id]
    except KeyError:
        raise KeyError(f"{guardrail_id!r} is not a registered guardrail") from None


def open_gaps() -> tuple[Guardrail, ...]:
    """Guardrails that are specified but not fully enforced."""
    return tuple(g for g in _GUARDRAILS if g.status is not Status.ENFORCED)
