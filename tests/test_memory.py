"""Agent memory: durable state, resumability, recap, footprint and privacy of what is stored.

No API key needed. The interview uses the real CaseService and SQLite stores;
the workflow uses the team's test-only providers and a fake reviewer.
"""
from datetime import timedelta
import time

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from src import memory
from src.agents.adversarial import make_adversarial_provider
from src.integration.case_service import CaseService
from src.integration.graph import build_graph
from src.integration.state import new_case
from tests.integration.test_adversarial_handoff import fake_model
from tests.integration.test_graph import providers


def start_interview(root, case_id="maria", answers=("single", "March 5, 1955")):
    service = CaseService(root)
    view = service.create(case_id)
    for reply in answers:
        view = service.answer(case_id, view["token"], reply)
    return service, view


# ---- 1. Resume recap (spec 4.3: "resumed on Friday ... with a summary") ---------------
def test_recap_after_three_days_summarises_and_points_to_the_same_question(tmp_path):
    _, view = start_interview(tmp_path)
    last = memory.resume_recap(tmp_path, "maria")["last_activity_at"]
    friday = memory._parse(last) + timedelta(days=3, hours=2)

    recap = memory.resume_recap(tmp_path, "maria", now=friday)

    assert recap["found"] and recap["idle_for"] == "3 days"
    assert recap["answers_saved"] == 2
    assert "Your date of birth: 1955-03-05" in recap["covered_so_far"]
    assert recap["next_step"] == view["pending"]["question"]  # exactly where we stopped
    assert recap["message"].startswith("Welcome back. We last worked on this 3 days ago.")


def test_recap_for_unknown_case_is_not_found(tmp_path):
    start_interview(tmp_path)
    assert memory.resume_recap(tmp_path, "nobody")["found"] is False


def test_reading_memory_never_writes_a_checkpoint(tmp_path):
    _, view = start_interview(tmp_path)
    before = (tmp_path / memory.INTAKE_DB).read_bytes()
    memory.resume_recap(tmp_path, "maria")
    memory.case_timeline(tmp_path, "maria")
    memory.memory_footprint(tmp_path, "maria")
    memory.audit_persisted_memory(tmp_path)
    assert (tmp_path / memory.INTAKE_DB).read_bytes() == before
    assert CaseService(tmp_path).view("maria")["token"] == view["token"]


# ---- 2. Timeline grouped into working sessions ----------------------------------------
def test_timeline_splits_sessions_and_reports_the_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "SESSION_GAP", timedelta(milliseconds=500))
    service, view = start_interview(tmp_path, answers=("single",))
    time.sleep(1.1)  # "Tuesday" -> "Friday", compressed
    service.answer("maria", view["token"], "March 5, 1955")

    timeline = memory.case_timeline(tmp_path, "maria")

    assert len(timeline["sessions"]) == 2
    assert "resumed_after" in timeline["sessions"][1]
    whats = [e["what"] for e in timeline["events"]]
    assert whats[0] == "interview started"
    assert "waiting for answer: taxpayer_birth_date" in whats
    assert [e["at"] for e in timeline["events"]] == sorted(e["at"] for e in timeline["events"])


# ---- 3. Footprint ------------------------------------------------------------------
def test_footprint_counts_checkpoints_and_latest_state(tmp_path):
    start_interview(tmp_path)
    report = memory.memory_footprint(tmp_path, "maria")["interview"]
    assert report["checkpoints"] >= 3
    assert report["stored_bytes"] > report["latest_state_bytes"] > 0
    assert "answers" in report["largest_keys"]


# ---- 4. Nothing sensitive in durable memory -------------------------------------------
def test_blocked_real_ssn_never_reaches_any_stored_checkpoint(tmp_path):
    service, view = start_interview(tmp_path, answers=())
    service.answer("maria", view["token"], "single, my SSN is 123-45-6789")
    result = memory.audit_persisted_memory(tmp_path)
    assert result["clean"] and result["records_scanned"] > 0


def test_audit_detects_an_ssn_written_around_the_guardrails(tmp_path):
    """Negative control: prove the scanner works by bypassing Intake on purpose."""
    start_interview(tmp_path)
    from demo.run_intake import build_graph as build_interview
    from src.agents.intake_parser import RuleParser
    with SqliteSaver.from_conn_string(str(tmp_path / memory.INTAKE_DB)) as saver:
        graph = build_interview(RuleParser(), saver)
        graph.update_state({"configurable": {"thread_id": "maria"}},
                           {"preface": "leaked 123-45-6789 and test 901-23-4567"}, as_node="intake")
    result = memory.audit_persisted_memory(tmp_path)
    assert not result["clean"]
    assert {f["kind"] for f in result["findings"]} == {"real_looking_ssn"}


def test_test_ssns_and_hash_digests_are_not_false_positives(tmp_path):
    assert not memory._SSN_is_real(b"901-23-4567") and memory._SSN_is_real(b"123-45-6789")
    assert not memory._SSN_is_real(b"a3f9123456789bcd")  # digits inside a hex digest


# ---- 5. Workflow memory survives a restart at the human-review interrupt ---------------
@pytest.mark.asyncio
async def test_paused_workflow_survives_restart_and_resumes(tmp_path):
    db = str(tmp_path / memory.WORKFLOW_DB)
    config = {"configurable": {"thread_id": "restart"}}
    reviewer = make_adversarial_provider(fake_model)  # always raises a human-review finding

    async with AsyncSqliteSaver.from_conn_string(db) as saver:
        paused = await build_graph(providers(adversarial=reviewer), checkpointer=saver).ainvoke(
            new_case("restart"), config)
        assert paused.get("__interrupt__")
    # Process ends here: nothing kept in RAM.

    recap = memory.resume_recap(tmp_path, "restart")
    assert recap["workflow"]["status"] == "paused_for_human_review"
    assert recap["workflow"]["pending_reviews"] == 1

    async with AsyncSqliteSaver.from_conn_string(db) as saver:  # new process, same file
        graph = build_graph(providers(adversarial=reviewer), checkpointer=saver)
        restored = await graph.aget_state(config)
        assert restored.values["events"] == paused["events"]   # nothing lost
        stopped = await graph.ainvoke(Command(resume={"action": "stop"}), config)
        assert stopped["status"] == "stopped"
