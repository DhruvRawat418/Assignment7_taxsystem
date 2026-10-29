"""SilverFile - Intake agent.

The only agent that talks to the taxpayer. It asks one plain-language question at a
time, records each answer with provenance, and raises flags for a human. It never
does arithmetic and never interprets tax rules (that is Eligibility / Computation).

The interview runs in its own LangGraph session (see demo/run_intake.py). The team
orchestrator never runs the dialogue: it calls the provider in intake_contract.py,
which reads the finished interview and returns {"facts", "amounts", "documents"}.

Each call to the node asks exactly ONE question via LangGraph `interrupt`, so the
LLM parse (after the interrupt) runs once per answer, and the checkpointer can
resume a session days later at the exact question it stopped on.
"""
from __future__ import annotations

import operator
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional, TypedDict

from langgraph.types import interrupt

from src.agents.intake_guards import (
    TAX_YEAR, detect_flags, mask_ssn, parse_amount, parse_date, parse_documents,
    parse_files, parse_filing_status, parse_yes_no, scan_ssns,
)
from src.agents.intake_parser import Parser

# --------------------------------------------------------------------------
# State owned by Intake (merge these keys into the team's SilverFileState)
# --------------------------------------------------------------------------


DELETE = "__delete__"  # put {field: DELETE} in an update to remove a key (used by "go back")


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    merged = {**(left or {}), **(right or {})}
    return {k: v for k, v in merged.items() if v != DELETE}


class IntakeState(TypedDict, total=False):
    answers: Annotated[dict, merge_dicts]          # field -> answer record (with provenance)
    dependents: list                                # finished dependent records
    dep_draft: Optional[dict]                       # dependent being collected; None = between dependents
    dependents_done: bool
    answered_order: list                            # for "go back"
    respondent: str                                 # "taxpayer" or "third party (...)"
    intake_complete: bool
    intake_paused: bool                             # True while waiting for a human
    preface: str                                    # what to say before the next question
    hitl_requests: Annotated[list, operator.add]    # blocking escalations (orchestrator -> interrupt)
    hitl_resolutions: Annotated[list, operator.add]
    volunteer_notes: Annotated[list, operator.add]  # non-blocking notes for the volunteer preparer
    answer_history: Annotated[list, operator.add]   # every change, so nothing is ever lost
    transcript: Annotated[list, operator.add]       # redacted; for audit, not fed to the LLM


def initial_intake_state() -> IntakeState:
    return {
        "answers": {}, "dependents": [], "dep_draft": {}, "dependents_done": False,
        "answered_order": [], "respondent": "taxpayer", "intake_complete": False,
        "intake_paused": False, "preface": "",
    }


# --------------------------------------------------------------------------
# Questions: one clause each, plain language
# --------------------------------------------------------------------------
QUESTIONS = {
    "filing_status": (
        f"How will you file for {TAX_YEAR}? You can say: single, married filing together, "
        "married filing separately, head of household, or surviving spouse. It's fine to say you're not sure."
    ),
    "taxpayer_birth_date": "What is your date of birth?",
    "taxpayer_blind": "Are you legally blind?",
    "spouse_birth_date": "What is your spouse's date of birth?",
    "spouse_blind": "Is your spouse legally blind?",
    "mfs_lived_with_spouse": f"Did you live with your spouse at any time in {TAX_YEAR}?",
    "has_dependents": "Is there anyone you support who you want to list on your return, like a child or grandchild?",
    "dependent_first_name": "What is this person's first name and middle initial, if any?",
    "dependent_last_name": "What is this person's last name?",
    "dependent_relationship": "How is this person related to you?",
    "dependent_ssn": "What is this person's Social Security number? In this practice system it must start with 9.",
    "more_dependents": "Is there anyone else you want to list?",
    # Scope questions. Eligibility decides what an answer means; we just ask.
    "has_self_employment_income": f"Did you earn money from your own business or freelance work in {TAX_YEAR}?",
    "has_rental_income": f"Did you rent out a house, apartment or room in {TAX_YEAR}?",
    "has_capital_gains": f"Did you sell any stocks, real estate or cryptocurrency in {TAX_YEAR}?",
    "has_foreign_income_or_accounts": "Did you have any income or bank accounts outside the United States?",
    "taxpayer_can_be_claimed_as_dependent": "Could someone else claim you as a dependent on their tax return?",
    "wants_to_itemize": "Do you want to list your expenses, like medical bills or donations, instead of the standard deduction?",
    "needs_state_return": "Do you also want help with a state tax return?",
    "documents": (
        f"Which tax forms did you get for {TAX_YEAR}? For example: W-2, SSA-1099, 1099-R, 1099-INT, or 1099-DIV."
    ),
    "w2_files": "Please type the file name of each W-2 photo or scan. If there are several, separate them with commas.",
    "has_estimated_payments": f"Did you send the IRS any payments during {TAX_YEAR}, before filing?",
    "estimated_payments_total": "What was the total amount of those payments?",
    "has_direct_schedule_amounts": "Do you have any other dollar amounts to enter from your completed tax schedules or payment records?",
}

# Transcribe already-known amounts; Intake never determines deductions or credits.
DIRECT_AMOUNT_LINES = {
    "schedule1_income": "8", "schedule1_adjustments": "10",
    "schedule2_line3": "17", "direct_dependent_credits": "19",
    "schedule3_line8": "20", "schedule2_line21": "23",
    "other_withholding": "25c", "schedule3_line15": "32", "ss_adjustments": "ss_adjustments",
}
DIRECT_AMOUNT_QUESTIONS = {
    "schedule1_income": "What is the amount on your completed Schedule 1, line 10?",
    "schedule1_adjustments": "What is the amount on your completed Schedule 1, line 26?",
    "schedule2_line3": "What is the amount on your completed Schedule 2, line 3?",
    "direct_dependent_credits": "What child or other-dependent credit amount has your preparer supplied for Form 1040-SR, line 19?",
    "schedule3_line8": "What is the amount on your completed Schedule 3, line 8?",
    "schedule2_line21": "What is the amount on your completed Schedule 2, line 21?",
    "other_withholding": "What other federal tax withholding amount belongs on Form 1040-SR, line 25c?",
    "schedule3_line15": "What is the amount on your completed Schedule 3, line 15?",
    "ss_adjustments": "What adjustment amount has your preparer supplied for the Social Security benefits worksheet?",
}
for _field, _question in DIRECT_AMOUNT_QUESTIONS.items():
    QUESTIONS[_field] = _question + " Say none if there is no amount, or not sure if you need help."

# Questions about the boxes of each form, asked only if the person has that form.
# W-2 amounts are not asked: Document Extraction reads them from the image.
FORM_QUESTIONS = {
    "SSA-1099": [
        ("ssa1099_box5", "On your SSA-1099, what is the amount in box 5, net benefits?", "SSA-1099 box 5"),
        ("ssa1099_box6", "On your SSA-1099, what is in box 6, federal tax withheld? Say none if it's blank.",
         "SSA-1099 box 6"),
    ],
    "1099-INT": [
        ("int_box1", "On your 1099-INT, what is the amount in box 1, interest income?", "1099-INT box 1"),
        ("int_box8", "On your 1099-INT, what is in box 8, tax-exempt interest? Say none if it's blank.",
         "1099-INT box 8"),
        ("int_box4", "On your 1099-INT, what is in box 4, federal tax withheld? Say none if it's blank.",
         "1099-INT box 4"),
    ],
    "1099-DIV": [
        ("div_box1a", "On your 1099-DIV, what is the amount in box 1a, total ordinary dividends?", "1099-DIV box 1a"),
        ("div_box1b", "On your 1099-DIV, what is in box 1b, qualified dividends? Say none if it's blank.",
         "1099-DIV box 1b"),
        ("div_box4", "On your 1099-DIV, what is in box 4, federal tax withheld? Say none if it's blank.",
         "1099-DIV box 4"),
    ],
    "1099-R": [
        ("r_is_ira", "Is your 1099-R for an IRA?", "1099-R is for an IRA"),
        ("r_box1", "On your 1099-R, what is the amount in box 1, gross distribution?", "1099-R box 1"),
        ("r_box2a", "On your 1099-R, what is the amount in box 2a, taxable amount?", "1099-R box 2a"),
        ("r_box2b", "On your 1099-R, is the box \"taxable amount not determined\" checked?", "1099-R box 2b checked"),
        ("r_box4", "On your 1099-R, what is in box 4, federal tax withheld? Say none if it's blank.",
         "1099-R box 4"),
    ],
}
FORM_QUESTIONS_NOTE = " If you have more than one of these forms, tell me the total."

LABELS = {
    "filing_status": "Filing status", "taxpayer_birth_date": "Your date of birth",
    "taxpayer_blind": "You are legally blind", "spouse_birth_date": "Spouse's date of birth",
    "spouse_blind": "Spouse is legally blind", "mfs_lived_with_spouse": "Lived with your spouse",
    "has_dependents": "People to list",
    "has_self_employment_income": "Business or freelance income", "has_rental_income": "Rental income",
    "has_capital_gains": "Sold stocks, real estate or crypto",
    "has_foreign_income_or_accounts": "Income or accounts abroad",
    "taxpayer_can_be_claimed_as_dependent": "Someone can claim you as a dependent",
    "wants_to_itemize": "Wants to itemize", "needs_state_return": "Wants a state return",
    "documents": "Tax forms", "w2_files": "W-2 files", "has_estimated_payments": "Payments sent during the year",
    "estimated_payments_total": "Total of those payments",
    "has_direct_schedule_amounts": "Other schedule or payment amounts to enter",
    **{field: question.rstrip("?") for field, question in DIRECT_AMOUNT_QUESTIONS.items()},
}
EXTRA_SCOPE_QUESTIONS = {
    "has_digital_assets": "During 2025, did you receive, sell, exchange, or otherwise dispose of digital assets, such as cryptocurrency?",
    "is_amended_or_prior_year": "Are you amending a return or preparing a return for a year other than 2025?",
    "taxpayer_dual_status_alien": "Were you a dual-status alien for U.S. tax purposes in 2025? You can say you are not sure.",
    "separate_spouse_itemizes": "If you are married filing separately, does your spouse itemize deductions? Answer no if this does not apply.",
}
QUESTIONS.update(EXTRA_SCOPE_QUESTIONS)
LABELS.update({key: question for key, question in EXTRA_SCOPE_QUESTIONS.items()})
SCOPE_FIELDS = ["has_self_employment_income", "has_rental_income", "has_capital_gains",
                "has_foreign_income_or_accounts", "taxpayer_can_be_claimed_as_dependent",
                "wants_to_itemize", "needs_state_return", *EXTRA_SCOPE_QUESTIONS]
for _form, _items in FORM_QUESTIONS.items():
    for _field, _question, _label in _items:
        QUESTIONS[_field] = _question if _field in ("r_is_ira", "r_box2b") else _question + FORM_QUESTIONS_NOTE
        LABELS[_field] = _label

RETRY_HINTS = {
    "filing_status": "Sorry, I didn't catch that. Which of these fits best: single, married filing together, "
                     "married filing separately, head of household, or surviving spouse?",
    "date": "Sorry, I didn't catch the date. Could you say it like this: March 5, 1956?",
    "yes_no": "Sorry, I didn't catch that. Could you answer yes or no?",
    "amount": "Sorry, I didn't catch the amount. Could you tell me the number in dollars?",
    "amount_multiple": "Thank you. Could you tell me the total amount, as one number?",
    "documents": "Sorry, I didn't catch that. Which forms do you have? For example W-2 or SSA-1099.",
    "files": "Sorry, I didn't catch the file name. Could you type it, like w2_2025.jpg?",
    "ssn": "That number doesn't look right. It should have 9 digits and start with 9.",
    "text": "Sorry, I didn't catch that. Could you say it again?",
}

FIELD_KIND = {
    "filing_status": "filing_status", "taxpayer_birth_date": "date", "spouse_birth_date": "date",
    "taxpayer_blind": "yes_no", "spouse_blind": "yes_no", "has_dependents": "yes_no",
    "more_dependents": "yes_no", "has_estimated_payments": "yes_no",
    "estimated_payments_total": "amount", "documents": "documents",
    "dependent_first_name": "text", "dependent_last_name": "text", "dependent_relationship": "text", "dependent_ssn": "ssn",
    "mfs_lived_with_spouse": "yes_no", "w2_files": "files",
    "has_direct_schedule_amounts": "yes_no",
    **{field: "amount" for field in DIRECT_AMOUNT_LINES},
    **{f: "yes_no" for f in SCOPE_FIELDS},
    **{f: ("yes_no" if f in ("r_is_ira", "r_box2b") else "amount")
       for items in FORM_QUESTIONS.values() for f, _, _ in items},
}
TOP_LEVEL_FIELDS = [f for f in QUESTIONS if not f.startswith("dependent_") and f != "more_dependents"]
JOINT_STATUSES = {"married_filing_jointly"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def provenance(value: Any, raw: str, entered_by: str, status: str = "answered") -> dict:
    """Every value the taxpayer gives is stored as 'direct user input' with time and author (spec 4.2)."""
    return {"value": value, "status": status, "source": "direct user input",
            "entered_at": now_iso(), "entered_by": entered_by, "raw_reply": raw}


def note(text: str, field: str | None = None, kind: str = "info") -> dict:
    """kind is one of: info, advice, unsure, third_party, ssn_blocked."""
    return {"id": uuid.uuid4().hex[:8], "field": field, "kind": kind, "note": text, "at": now_iso(),
            "raised_by": "intake"}


def hitl(reason: str, detail: str, field: str | None) -> dict:
    return {"id": uuid.uuid4().hex[:8], "reason": reason, "detail": detail, "field": field,
            "blocking": True, "raised_by": "intake", "at": now_iso()}


def pending_hitl(state: dict) -> list[dict]:
    done = {r["id"] for r in state.get("hitl_resolutions", [])}
    return [r for r in state.get("hitl_requests", []) if r["id"] not in done]


# --------------------------------------------------------------------------
# Which question comes next (deterministic, no LLM)
# --------------------------------------------------------------------------
def _val(answers: dict, field: str) -> Any:
    rec = answers.get(field)
    return rec["value"] if rec else None


def next_field(state: dict) -> str | None:
    a = state.get("answers", {})
    for f in ["filing_status", "taxpayer_birth_date", "taxpayer_blind"]:
        if f not in a:
            return f
    if _val(a, "filing_status") in JOINT_STATUSES:
        for f in ["spouse_birth_date", "spouse_blind"]:
            if f not in a:
                return f
    if _val(a, "filing_status") == "married_filing_separately" and "mfs_lived_with_spouse" not in a:
        return "mfs_lived_with_spouse"
    if "has_dependents" not in a:
        return "has_dependents"
    if _val(a, "has_dependents") is True and not state.get("dependents_done"):
        draft = state.get("dep_draft")
        if draft is None:
            return "more_dependents"
        for k in ["first_name", "last_name", "relationship", "ssn"]:
            if k not in draft:
                return f"dependent_{k}"
    for f in SCOPE_FIELDS + ["documents"]:
        if f not in a:
            return f
    forms = _val(a, "documents") or []
    if "W-2" in forms and "w2_files" not in a:
        return "w2_files"
    for form, items in FORM_QUESTIONS.items():
        if form in forms:
            for f, _, _ in items:
                if f not in a:
                    return f
    if "has_estimated_payments" not in a:
        return "has_estimated_payments"
    if _val(a, "has_estimated_payments") is True and "estimated_payments_total" not in a:
        return "estimated_payments_total"
    if "has_direct_schedule_amounts" not in a:
        return "has_direct_schedule_amounts"
    if _val(a, "has_direct_schedule_amounts") is True:
        for field in DIRECT_AMOUNT_LINES:
            if field not in a:
                return field
    return None


def summarize(state: dict) -> str:
    """Plain-language recap, used when a session resumes days later. Never shows a full SSN."""
    a = state.get("answers", {})
    lines = []
    for f in TOP_LEVEL_FIELDS:
        if f in a and f in LABELS:
            rec = a[f]
            v = rec["value"]
            if rec["status"] == "unsure":
                v = "not sure yet (flagged for a volunteer)"
            elif isinstance(v, bool):
                v = "yes" if v else "no"
            elif isinstance(v, list):
                v = ", ".join(v) or "none"
            elif f == "filing_status":
                v = str(v).replace("_", " ")
            elif f == "estimated_payments_total":
                v = f"${v}"
            lines.append(f"- {LABELS[f]}: {v}")
    for d in state.get("dependents", []):
        ssn = mask_ssn(d["ssn"]["value"]) if d.get("ssn", {}).get("value") else "not given"
        lines.append(f"- Listed person: {d.get('first_name', d.get('name', {})).get('value', '')} {d.get('last_name', {}).get('value', '')} ({d['relationship']['value']}), SSN {ssn}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Handling one reply (pure function: easy to unit test without a graph)
# --------------------------------------------------------------------------
def _validate(field: str, value: str, scan) -> tuple[Any, str | None]:
    """Return (normalised_value, None) or (None, retry_hint_key)."""
    kind = FIELD_KIND[field]
    if kind == "filing_status":
        v = parse_filing_status(value)
        return (v, None) if v else (None, "filing_status")
    if kind == "date":
        v = parse_date(value)
        return (v, None) if v else (None, "date")
    if kind == "yes_no":
        v = parse_yes_no(value)
        return (v, None) if v is not None else (None, "yes_no")
    if kind == "amount":
        if field in DIRECT_AMOUNT_LINES:
            text = value.strip()
            negative = field == "schedule1_income" and text.startswith("-")
            if negative:
                text = text[1:].strip()
            if not (re.fullmatch(r"\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", text)
                    or (not negative and text.lower() in {"none", "nothing", "zero", "no"})):
                return None, "amount"
            parsed = parse_amount(text)
            return (("-" if negative else "") + parsed.value, None) if parsed.value is not None else (None, "amount")
        p = parse_amount(value)
        if p.multiple_amounts:
            return None, "amount_multiple"
        return (p.value, None) if p.value is not None else (None, "amount")
    if kind == "documents":
        v = parse_documents(value)
        return (v, None) if v is not None else (None, "documents")
    if kind == "files":
        v = parse_files(value)
        return (v, None) if v else (None, "files")
    if kind == "ssn":
        return (scan.test_ssns[0], None) if len(scan.test_ssns) == 1 else (None, "ssn")
    v = value.strip()
    return (v, None) if v else (None, "text")


def _store(state: dict, field: str, value: Any, raw: str, who: str, status: str = "answered") -> dict:
    """Write one answer and return the state update. Corrections keep the old value in history."""
    upd: dict = {}
    rec = provenance(value, raw, who, status)
    if field.startswith("dependent_"):
        key = field.removeprefix("dependent_")
        draft = {**(state.get("dep_draft") or {}), key: rec}
        if key == "ssn":  # dependent complete
            upd["dependents"] = [*state.get("dependents", []), draft]
            upd["dep_draft"] = None
        else:
            upd["dep_draft"] = draft
    elif field == "more_dependents":
        if value is True:
            upd["dep_draft"] = {}
        else:
            upd["dependents_done"] = True
    else:
        old = state.get("answers", {}).get(field)
        if old and old["value"] != value:
            upd["answer_history"] = [{"field": field, "old": old["value"], "new": value, "at": rec["entered_at"]}]
        upd["answers"] = {field: rec}
    upd["answered_order"] = [*state.get("answered_order", []), field]
    return upd


def _go_back(state: dict) -> dict:
    order = list(state.get("answered_order", []))
    if not order:
        return {"preface": "We're at the first question already."}
    last = order.pop()
    upd: dict = {"answered_order": order, "preface": "No problem, let's go back."}
    if last in TOP_LEVEL_FIELDS:
        old = state["answers"][last]
        upd["answer_history"] = [{"field": last, "old": old["value"], "new": None, "at": now_iso(), "note": "went back"}]
        upd["answers"] = {last: DELETE}
    elif last.startswith("dependent_"):
        key = last.removeprefix("dependent_")
        if state.get("dep_draft") is None:  # reopen the dependent we just finished
            deps = list(state.get("dependents", []))
            draft = deps.pop() if deps else {}
            upd["dependents"] = deps
        else:
            draft = dict(state["dep_draft"])
        draft.pop(key, None)
        upd["dep_draft"] = draft
    elif last == "more_dependents":
        upd["dep_draft"] = None
        upd["dependents_done"] = False
    return upd


def handle_reply(state: dict, field: str, reply: str, parser: Parser) -> dict:
    question = QUESTIONS[field]
    who = state.get("respondent", "taxpayer")

    # 1. SSN guard runs first, before anything is stored or sent to an LLM.
    scan = scan_ssns(reply)
    text = scan.redacted_text
    upd: dict = {"transcript": [{"field": field, "question": question, "reply": text, "at": now_iso()}],
                 "preface": ""}
    if scan.real_ssn_found:
        upd["preface"] = ("For your safety, please don't type a real Social Security number here. "
                          "I did not save it. This practice system only accepts test numbers that start with 9.")
        upd["volunteer_notes"] = [note("A real-looking SSN was typed and blocked. It was not stored.", field, "ssn_blocked")]
        return upd

    # 2. Flags: deterministic backstop OR the LLM. Either one is enough.
    flags = detect_flags(text)
    parsed = parser(field=field, question=question, reply=text, known=summarize(state))
    third_party = flags.third_party or parsed.third_party_answering
    authority = flags.stated_authority or parsed.stated_authority
    refund_concern = flags.refund_concern or parsed.refund_account_concern
    spouse_death = flags.spouse_death or parsed.spouse_death_mentioned
    advice = flags.advice or parsed.intent == "advice_request"

    # 3. Possible financial exploitation: notice and stop. We do not judge.
    if refund_concern or (third_party and not authority):
        reason = "refund routed to an account the taxpayer may not control" if refund_concern \
            else "someone other than the taxpayer is answering, with no stated authority"
        upd["hitl_requests"] = [hitl("possible_financial_exploitation", reason, field)]
        upd["intake_paused"] = True
        upd["preface"] = ("Thank you for telling me. I'd like one of our team members to go over this with you, "
                          "so I'm pausing here. Nothing you told me is lost.")
        return upd
    if third_party and authority and who == "taxpayer":
        who = f"third party (stated authority: {authority})"
        upd["respondent"] = who
        upd["volunteer_notes"] = [note(f"Answers given by a third party who stated: {authority}. Verify.", field, "third_party")]

    # 4. Spouse death: filing status is ambiguous (MFJ vs QSS vs Single). A human decides.
    if spouse_death:
        upd["hitl_requests"] = [hitl("filing_status_ambiguity", "taxpayer mentioned their spouse died", field)]
        upd["intake_paused"] = True
        upd["preface"] = ("I'm sorry for your loss. Your filing status needs a person to look at it with you, "
                          "so I've asked a team member to help. Nothing you told me is lost.")
        return upd

    # 5. Advice request: explain scope, note the question, ask the same question again.
    if advice:
        q = parsed.advice_question or text
        upd["volunteer_notes"] = [*upd.get("volunteer_notes", []), note(f"Taxpayer asked: {q}", field, "advice")]
        upd["preface"] = ("That's a good question, but I can't give tax advice. I've written it down so a "
                          "volunteer preparer can talk it through with you. Let's carry on.")
        return upd

    # 6. Go back / unsure.
    if parsed.intent == "go_back":
        return {**upd, **_go_back(state)}
    if parsed.intent == "unsure" and field.startswith("dependent_"):
        upd["hitl_requests"] = [hitl("dependent_details_uncertain", "Dependent details need confirmation before transcription.", field)]
        upd["intake_paused"] = True
        upd["preface"] = "A volunteer needs to confirm this detail with you before we continue."
        return upd
    if parsed.intent == "unsure":
        upd.update(_store(state, field, None, text, who, status="unsure"))
        upd["volunteer_notes"] = [*upd.get("volunteer_notes", []), note(f"Not sure about: {question}", field, "unsure")]
        upd["preface"] = "That's okay. I've flagged this for a volunteer to check with you. Let's keep going."
        return upd

    # 7. Corrections to earlier answers (tolerance of drift): keep history, never lose data.
    for c in parsed.corrections:
        if c.field in TOP_LEVEL_FIELDS and c.field in state.get("answers", {}):
            value, err = _validate(c.field, c.value, scan)
            if err is None:
                fix = _store(state, c.field, value, text, who)
                upd["answers"] = merge_dicts(upd.get("answers"), fix["answers"])
                upd["answer_history"] = [*upd.get("answer_history", []), *fix.get("answer_history", [])]
                upd["preface"] = f"Thanks, I've updated: {LABELS.get(c.field, c.field).lower()}. "

    if parsed.intent == "off_topic" and not parsed.value:
        upd["preface"] += "Let's come back to this question."
        return upd

    # 8. The answer to the current question.
    value, err = _validate(field, parsed.value or text, scan)
    if err:
        upd["preface"] += RETRY_HINTS[err]
        return upd
    if scan.test_ssns and field != "dependent_ssn":
        upd["preface"] += "You don't need to give me a Social Security number for this, so I didn't save it. "
    stored = _store(state, field, value, text, who)
    if "answers" in upd and "answers" in stored:
        stored["answers"] = merge_dicts(upd["answers"], stored["answers"])
    if "answer_history" in upd and "answer_history" in stored:
        stored["answer_history"] = [*upd["answer_history"], *stored["answer_history"]]
    upd.update(stored)
    return upd


# --------------------------------------------------------------------------
# The LangGraph node
# --------------------------------------------------------------------------
def make_intake_node(parser: Parser):
    def intake_node(state: dict) -> dict:
        field = next_field(state)
        if field is None:
            return {"intake_complete": True,
                    "preface": "Thank you. That's everything I need from you for now."}
        # Everything above this line must stay deterministic: LangGraph re-runs the node on resume.
        reply = interrupt({
            "type": "ask_user",
            "field": field,
            "message": state.get("preface", ""),
            "question": QUESTIONS[field],
            "covered_so_far": summarize(state),
        })
        if field == 'w2_files' and isinstance(reply,dict) and set(reply)=={'uploaded_w2_paths'}:
            paths=reply['uploaded_w2_paths']
            if (not isinstance(paths,list) or not 1<=len(paths)<=10
                    or any(not isinstance(p,str) or not p or len(p)>1000 for p in paths)):
                raise ValueError('Invalid uploaded document references')
            # The browser service validates image bytes and generates these paths.
            # Filesystem references are not free-text taxpayer answers or SSNs.
            return _store(state,field,paths,'Browser W-2 upload',state.get('respondent','taxpayer'))
        return handle_reply(state, field, str(reply), parser)

    return intake_node
