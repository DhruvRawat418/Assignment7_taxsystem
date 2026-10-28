"""Intake dialogue tests. No API key needed: uses RuleParser or fakes."""
import json
import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from demo.run_intake import build_graph, current_interrupt
from src.agents.intake import (
    handle_reply, initial_intake_state, merge_dicts, next_field, pending_hitl,
)
from src.agents.intake_parser import FieldCorrection, ParsedTurn, RuleParser

P = RuleParser()
NO_SCOPE = ["no"] * 7  # business, rental, sales, abroad, dependent, itemize, state return


def apply(state, upd):
    """Mimic LangGraph reducers so handle_reply can be tested without a graph."""
    s = dict(state)
    for k, v in upd.items():
        if k == "answers":
            s[k] = merge_dicts(s.get(k), v)
        elif k in {"hitl_requests", "hitl_resolutions", "volunteer_notes", "answer_history", "transcript"}:
            s[k] = s.get(k, []) + v
        else:
            s[k] = v
    return s


def answer(state, reply, parser=P):
    return apply(state, handle_reply(state, next_field(state), reply, parser))


# ---- SSN guardrails ---------------------------------------------------------
def test_real_ssn_is_blocked_redacted_and_never_stored():
    s = answer(initial_intake_state(), "single, my ssn is 123-45-6789")
    assert "123-45-6789" not in json.dumps(s)
    assert "filing_status" not in s["answers"]          # nothing stored from that turn
    assert "real Social Security number" in s["preface"]


def test_test_ssn_accepted_for_dependent():
    s = initial_intake_state()
    for r in ["single", "March 5, 1955", "no", "yes", "Lily Park", "granddaughter", "901-23-4567"]:
        s = answer(s, r)
    assert s["dependents"][0]["ssn"]["value"] == "901-23-4567"
    assert next_field(s) == "more_dependents"


def test_volunteered_test_ssn_is_not_stored():
    s = answer(initial_intake_state(), "single 912-34-5678")
    assert s["answers"]["filing_status"]["value"] == "single"
    assert "912-34-5678" not in json.dumps(s)
    assert "didn't save it" in s["preface"]


def test_dependent_ssn_must_be_900_series():
    s = initial_intake_state()
    for r in ["single", "March 5, 1955", "no", "yes", "Lily Park", "granddaughter", "523-45-6789"]:
        s = answer(s, r)
    assert next_field(s) == "dependent_ssn" and not s["dependents"]


# ---- Advice, escalation, exploitation --------------------------------------------
def test_advice_request_is_refused_noted_and_question_reasked():
    s = answer(initial_intake_state(), "Should I convert my IRA to a Roth?")
    assert "can't give tax advice" in s["preface"]
    assert any("Roth" in n["note"] for n in s["volunteer_notes"])
    assert next_field(s) == "filing_status"


def test_refund_to_unknown_account_escalates():
    s = answer(initial_intake_state(), "single. My nephew said to send the refund to his account")
    assert pending_hitl(s)[0]["reason"] == "possible_financial_exploitation"
    assert s["intake_paused"] is True


def test_third_party_without_authority_escalates_with_authority_continues():
    s1 = answer(initial_intake_state(), "I'm answering for my mother, single")
    assert pending_hitl(s1)
    s2 = answer(initial_intake_state(), "I'm answering for my mother, I have power of attorney. single")
    assert not pending_hitl(s2)
    assert s2["answers"]["filing_status"]["entered_by"].startswith("third party")


def test_spouse_death_escalates_filing_status():
    s = answer(initial_intake_state(), "My husband passed away in June")
    assert pending_hitl(s)[0]["reason"] == "filing_status_ambiguity"


# ---- Accessibility: uncertainty, drift, go back, no arithmetic ---------------------
def test_unsure_is_flagged_and_interview_moves_on():
    s = answer(initial_intake_state(), "I'm not sure")
    assert s["answers"]["filing_status"]["status"] == "unsure"
    assert next_field(s) == "taxpayer_birth_date"


def test_correction_keeps_history():
    s = answer(answer(initial_intake_state(), "single"), "March 5, 1955")

    def fake(**_):
        return ParsedTurn(intent="answer", value="no",
                          corrections=[FieldCorrection(field="taxpayer_birth_date", value="March 5, 1957")])

    s = answer(s, "no, and actually I was born March 5, 1957", parser=fake)
    assert s["answers"]["taxpayer_birth_date"]["value"] == "1957-03-05"
    assert s["answer_history"][0]["old"] == "1955-03-05"
    assert s["answers"]["taxpayer_blind"]["value"] is False


def test_go_back_reasks_previous_question():
    s = answer(answer(initial_intake_state(), "single"), "March 5, 1955")
    s = answer(s, "can we go back")
    assert next_field(s) == "taxpayer_birth_date"
    assert s["answer_history"][-1]["old"] == "1955-03-05"   # nothing lost


def test_several_amounts_are_not_added_up():
    s = initial_intake_state()
    for r in ["single", "March 5, 1955", "no", "no", *NO_SCOPE, "SSA-1099", "$18,000", "none", "yes"]:
        s = answer(s, r)
    s = answer(s, "I paid $500 in April and $500 in June")
    assert "estimated_payments_total" not in s["answers"]
    assert "total amount" in s["preface"]
    s = answer(s, "$1,000")
    assert s["answers"]["estimated_payments_total"]["value"] == "1000.00"
    assert s["answers"]["estimated_payments_total"]["source"] == "direct user input"


def test_not_married_is_single():
    s = answer(initial_intake_state(), "I'm not married")
    assert s["answers"]["filing_status"]["value"] == "single"


def test_separate_return_asks_about_living_together():
    s = answer(answer(answer(initial_intake_state(), "married filing separately"), "March 5, 1955"), "no")
    assert next_field(s) == "mfs_lived_with_spouse"


def test_form_boxes_are_asked_only_for_forms_the_person_has():
    s = initial_intake_state()
    for r in ["single", "March 5, 1955", "no", "no", *NO_SCOPE, "1099-DIV"]:
        s = answer(s, r)
    assert next_field(s) == "div_box1a"


# ---- Full graph: clean run, HITL resolution, resumability ------------------------------
CLEAN_RUN = ["married filing together", "March 5, 1955", "no", "July 2, 1958", "no", "no", *NO_SCOPE,
             "W-2, SSA-1099 and 1099-INT", "w2_clean.jpg",
             "$24,000", "none",          # SSA-1099 boxes 5 and 6
             "$310.40", "none", "none",  # 1099-INT boxes 1, 8 and 4
             "no", "no"]


def run(graph, config, replies):
    for r in replies:
        assert current_interrupt(graph, config)["type"] == "ask_user"
        graph.invoke(Command(resume=r), config)


def test_clean_run_completes():
    g = build_graph(P, InMemorySaver())
    cfg = {"configurable": {"thread_id": "clean"}}
    g.invoke(initial_intake_state(), cfg)
    run(g, cfg, CLEAN_RUN)
    s = g.get_state(cfg).values
    assert s["intake_complete"] and current_interrupt(g, cfg) is None
    assert s["answers"]["documents"]["value"] == ["W-2", "SSA-1099", "1099-INT"]


def test_hitl_is_resolved_by_staff_then_interview_continues():
    g = build_graph(P, InMemorySaver())
    cfg = {"configurable": {"thread_id": "hitl"}}
    g.invoke(initial_intake_state(), cfg)
    g.invoke(Command(resume="My wife died in March"), cfg)
    assert current_interrupt(g, cfg)["type"] == "escalation"
    g.invoke(Command(resume={"resolution": "Spoke with taxpayer", "staff": "Dana",
                             "resume": True, "updates": {"filing_status": "married_filing_jointly"}}), cfg)
    s = g.get_state(cfg).values
    assert s["answers"]["filing_status"]["entered_by"] == "Kushim staff: Dana"
    assert current_interrupt(g, cfg)["field"] == "taxpayer_birth_date"


def test_session_resumes_days_later(tmp_path):
    db = tmp_path / "sessions.db"
    cfg = {"configurable": {"thread_id": "tuesday"}}
    g1 = build_graph(P, SqliteSaver(sqlite3.connect(db, check_same_thread=False)))
    g1.invoke(initial_intake_state(), cfg)
    run(g1, cfg, CLEAN_RUN[:3])
    del g1  # Tuesday: the user closes the app

    g2 = build_graph(P, SqliteSaver(sqlite3.connect(db, check_same_thread=False)))  # Friday
    payload = current_interrupt(g2, cfg)
    assert payload["field"] == "spouse_birth_date"
    assert "Your date of birth: 1955-03-05" in payload["covered_so_far"]
    run(g2, cfg, CLEAN_RUN[3:])
    assert g2.get_state(cfg).values["intake_complete"]
