"""Hands a finished Intake interview to the team orchestrator.

The interview itself (intake.py) runs in its own LangGraph session, one thread per
case, because it pauses for the taxpayer at every question. The team graph only
sees the result, as the `intake` provider:

    ProviderResult("ready", {"facts": {...}, "amounts": {...}, "documents": [...]})

or `needs_input` while the interview is not finished. Nothing here applies a tax
rule or adds numbers: we copy each answer to the key Eligibility or Computation
expects and say where it came from.
"""
from __future__ import annotations

import hashlib
import sqlite3

from src.agents.computation_contract import INPUT_LINES
from src.agents.intake import SCOPE_FIELDS, pending_hitl
from src.integration.contracts import ProviderResult

FILING_STATUS = {
    "single": "single", "married_filing_jointly": "mfj", "married_filing_separately": "mfs",
    "head_of_household": "hoh", "qualifying_surviving_spouse": "qss",
}
# Intake answer -> key in Eligibility's IntakeFacts.
FACT_KEYS = {
    "taxpayer_birth_date": "taxpayer_date_of_birth", "taxpayer_blind": "taxpayer_blind",
    "spouse_birth_date": "spouse_date_of_birth", "spouse_blind": "spouse_blind",
    "mfs_lived_with_spouse": "mfs_lived_with_spouse", **{f: f for f in SCOPE_FIELDS},
}
# Form box -> 1040-SR line. Federal tax withheld on any 1099 goes to line 25b.
# 1099-R boxes 1 and 2a go to 4a/4b (IRA) or 5a/5b (pension), see _amounts().
BOX_LINES = {
    "ssa1099_box5": "6a", "ssa1099_box6": "25b",
    "int_box1": "2b", "int_box8": "2a", "int_box4": "25b",
    "div_box1a": "3b", "div_box1b": "3a", "div_box4": "25b",
    "r_box4": "25b", "estimated_payments_total": "26",
}
# Lines this system never asks about, because they only exist for out-of-scope
# situations (business income, credits, other taxes...). The scope questions cover them.
SCOPE_ZERO_LINES = ("8", "10", "17", "19", "20", "23", "25c", "32", "ss_adjustments")
SUPPORTED_FORMS = {"W-2", "SSA-1099", "1099-INT", "1099-DIV", "1099-R"}
# Answers we cannot send as "unknown": without them there is no return to compute.
MUST_KNOW = {"filing_status", "taxpayer_birth_date", "taxpayer_blind", "spouse_birth_date", "spouse_blind",
             "mfs_lived_with_spouse", "documents", "w2_files", "has_estimated_payments", *BOX_LINES,
             "r_is_ira", "r_box1", "r_box2a", "r_box2b"}


def _answered(answers: dict, field: str):
    """The value, or None if the question was not asked or the person was unsure."""
    rec = answers.get(field)
    return rec["value"] if rec and rec["status"] == "answered" else None


def _source(field: str, rec: dict, why: str | None = None) -> dict:
    return {"kind": "user_input", "reference": f"intake:{field}", "field": why or field,
            "entered_by": rec["entered_by"][:100], "recorded_at": rec["entered_at"]}


def _amounts(answers: dict) -> dict:
    forms = set(_answered(answers, "documents") or [])
    docs_rec = answers["documents"]
    amounts: dict = {line: [] for line in INPUT_LINES}

    for field, line in BOX_LINES.items():
        if field in answers:
            amounts[line].append({"value": answers[field]["value"], "sources": [_source(field, answers[field])]})
    if "1099-R" in forms:
        ira = _answered(answers, "r_is_ira")
        for field, line in (("r_box1", "4a" if ira else "5a"), ("r_box2a", "4b" if ira else "5b")):
            amounts[line].append({"value": answers[field]["value"], "sources": [_source(field, answers[field])]})

    # A line with no entry is a confirmed zero: the person told us which forms they have
    # (or that they sent no payments), or the line is outside the supported scope.
    for line, entries in amounts.items():
        if entries:
            continue
        if line == "26":
            rec, why = answers["has_estimated_payments"], "no payments sent during the year"
        elif line in SCOPE_ZERO_LINES:
            rec = {**docs_rec, "entered_by": "intake (outside supported scope)"}
            why = f"line {line} not used in the supported scope"
        else:
            rec, why = docs_rec, f"line {line}: no matching form listed"
        amounts[line].append({"value": "0.00", "sources": [_source("documents", rec, why)]})

    if "W-2" in forms:  # Extraction reads boxes 1 and 2 from the images: they own 1z and 25a.
        del amounts["1z"], amounts["25a"]
    return amounts


def _documents(answers: dict) -> list[dict]:
    if "W-2" not in (_answered(answers, "documents") or []):
        return []
    # The id comes from the file name, so the same file always gets the same id
    # and a corrected upload (new file) gets a new one.
    return [{"document_id": "w2-" + hashlib.sha1(path.encode()).hexdigest()[:10], "path": path}
            for path in answers["w2_files"]["value"]]


def _facts(session: dict) -> dict:
    answers = session["answers"]
    facts = {"filing_status": FILING_STATUS[answers["filing_status"]["value"]]}
    for field, key in FACT_KEYS.items():
        value = _answered(answers, field)
        if value is not None:
            facts[key] = value

    # Things the interview noticed. Eligibility decides what they mean.
    reasons = {r["reason"] for r in session.get("hitl_requests", [])}
    notes = session.get("volunteer_notes", [])
    facts["spouse_died_during_tax_year"] = "filing_status_ambiguity" in reasons
    facts["third_party_pressure_observed"] = "possible_financial_exploitation" in reasons
    facts["requested_advice"] = any(n.get("kind") == "advice" for n in notes)

    # Everything a volunteer should read goes in free_text_notes, which Eligibility escalates.
    free_text = [n["note"] for n in notes if n.get("kind") in ("unsure", "third_party")]
    for form in _answered(answers, "documents") or []:
        if form not in SUPPORTED_FORMS:
            free_text.append(f"The taxpayer listed a form this system does not handle: {form}")
    if _answered(answers, "r_box2b"):
        free_text.append("1099-R box 2b (taxable amount not determined) is checked")
    if session.get("dependents"):
        free_text.append(f"The taxpayer listed {len(session['dependents'])} dependent(s); "
                         "dependent credits are not handled")
    facts["free_text_notes"] = free_text[:64]
    return facts


def to_packet(session: dict) -> dict:
    """The `data` of a ready ProviderResult. Dependents' SSNs are deliberately left out."""
    answers = session["answers"]
    return {"facts": _facts(session), "amounts": _amounts(answers), "documents": _documents(answers)}


def not_ready_reason(session: dict | None) -> str | None:
    if not session or "answers" not in session:
        return "intake_not_started"
    if pending_hitl(session):
        return "intake_waiting_for_staff"
    if not session.get("intake_complete"):
        return "intake_not_finished"
    if any(rec["status"] == "unsure" for f, rec in session["answers"].items() if f in MUST_KNOW):
        return "intake_unsure_answer"
    return None


def make_intake_provider(load_session):
    """`load_session(case_id)` returns the interview state for that case, or None."""
    def intake_provider(state: dict) -> ProviderResult:
        session = load_session(state.get("case_id"))
        reason = not_ready_reason(session)
        if reason:
            return ProviderResult("needs_input", issue_codes=(reason,))
        packet = to_packet(session)
        # Another agent sent the case back (e.g. unreadable W-2, missing fact) and the
        # interview has not changed since: the taxpayer has to be asked again.
        if state.get("issues") and packet == state.get("intake_snapshot"):
            return ProviderResult("needs_input", issue_codes=tuple(i["code"] for i in state["issues"])[:128])
        return ProviderResult("ready", packet)
    return intake_provider


def sqlite_sessions(db_path: str):
    """Reads interviews saved by demo/run_intake.py. The session name is the case id."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    saver = SqliteSaver(sqlite3.connect(db_path, check_same_thread=False))

    def load_session(case_id):
        saved = saver.get_tuple({"configurable": {"thread_id": case_id}})
        return saved.checkpoint["channel_values"] if saved else None
    return load_session
