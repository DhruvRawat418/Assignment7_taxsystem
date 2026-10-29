"""Behavioral checks for Xinrui's allocation policy in the real team graph.

    Business providers below are test doubles; these are routing tests.
"""
from copy import deepcopy
from threading import Barrier

import pytest
from langgraph.types import Command

from src.integration.contracts import ProviderResult
from src.integration.state import context_fingerprint, new_case
from src.integration.task_division import plan_extraction, task_board
from tests.integration.fixtures import extracted, intake_data
from tests.integration.test_graph import config, fake_extract, graph, providers


def board_by_id(state):
    return {task["task_id"]: task for task in state["task_plan"]["tasks"]}


def test_active_inventory_ignores_history_and_distinguishes_rework_from_new_work():
    documents = [{"document_id": key, "path": key + ".jpg"} for key in ("good", "bad", "new")]
    history = {"good": extracted("good"), "bad": {"status": "needs_review", "issues": [{"code": "missing_box"}]},
               "obsolete": {"status": "rejected", "issues": [{"code": "unsafe_ssn"}]}}
    before = deepcopy((documents, history))
    plan = plan_extraction(documents, history)
    assert [d["document_id"] for d in plan.pending] == ["new"]
    assert plan.completed == ("good",) and plan.needs_input == ("bad",)
    assert not plan.ready_for_rules
    assert (documents, history) == before
    assert plan_extraction(documents[:1], history).ready_for_rules
    assert plan_extraction([], history).ready_for_rules


def test_success_status_with_open_issue_still_requires_intake():
    result = extracted()
    result["issues"] = [{"code": "unresolved_conflict"}]
    plan = plan_extraction([{"document_id": "w2-1", "path": "a.jpg"}], {"w2-1": result})
    assert not plan.ready_for_rules and plan.needs_input == ("w2-1",)


def test_task_board_is_private_and_only_the_selected_stage_is_ready():
    state = new_case("board")
    data = intake_data()
    state.update(intake_snapshot=data, documents=data["documents"], next_stage="extract", revision=1)
    before = deepcopy(state)
    board = task_board(state)
    by_id = {t["task_id"]: t for t in board["tasks"]}
    assert by_id["extract:w2-1"]["status"] == "ready"
    assert by_id["rules"]["status"] == "waiting"
    assert by_id["compute"]["depends_on"] == ["rules"]
    assert "demo/w2_clean.jpg" not in str(board) and "50000" not in str(board)
    assert state == before


def test_stale_compute_and_audit_are_not_done_in_a_new_revision():
    state = new_case("stale-board")
    state.update(computation_result={"status": "completed"}, audit_result={"status": "passed"})
    state["computed_for"] = state["audit_for"] = context_fingerprint(state)
    assert next(t for t in task_board(state)["tasks"] if t["task_id"] == "audit")["status"] == "done"
    state["intake_snapshot"] = {"facts": {"changed": True}}
    by_id = {t["task_id"]: t for t in task_board(state)["tasks"]}
    assert by_id["compute"]["status"] == by_id["audit"]["status"] == "waiting"


def test_human_task_is_not_ready_until_supervisor_completion_checks_pass():
    state = new_case("final-gate")
    state["next_stage"] = "complete"
    final_task = next(t for t in task_board(state)["tasks"] if t["task_id"] == "final_review")
    assert final_task["status"] == "waiting"


@pytest.mark.asyncio
async def test_only_new_tasks_run_in_parallel_and_rules_waits_for_all_results():
    barrier, calls = Barrier(2), []
    async def intake(state):
        data = intake_data()
        data["documents"] += [{"document_id": key, "path": key + ".jpg"} for key in ("new-a", "new-b")]
        return ProviderResult("ready", data)

    def extract(state):
        calls.append(state["document"]["document_id"])
        barrier.wait(timeout=5)  # Serial execution cannot satisfy this barrier.
        return fake_extract(state)

    real_rules = providers().rules
    async def rules(state):
        assert set(state["extractions"]) == {"w2-1", "new-a", "new-b"}
        return await real_rules(state)

    initial = new_case("allocation-parallel")
    initial["extractions"] = {"w2-1": extracted()}
    result = await graph(providers(intake=intake, extraction=extract, rules=rules)).ainvoke(initial, config("allocation-parallel"))
    assert result["status"] == "ready_for_human_review"
    assert sorted(calls) == ["new-a", "new-b"]
    board = board_by_id(result)
    assert board["aggregate"]["depends_on"] == ["extract:w2-1", "extract:new-a", "extract:new-b"]
    assert all(board[key]["status"] == "done" for key in ("aggregate", "rules", "compute", "audit", "adversarial"))
    assert board["final_review"]["status"] == "ready"
    assert result["task_plan"]["case_status"] == result["status"]


@pytest.mark.asyncio
async def test_interrupt_replacement_reuses_good_upload_and_keeps_bad_upload_history():
    calls = []
    async def intake(state):
        data = intake_data()
        response = state["human_response"]
        if response:
            assert response["owner"] == "intake"
            assert response["response"] == {"replacement_received": True}
            data["documents"].append({"document_id": "fixed", "path": "fixed.jpg"})
        elif state["issues"]:
            return ProviderResult("needs_human_review", issue_codes=("clearer_document_required",))
        else:
            data["documents"].append({"document_id": "bad", "path": "bad.jpg"})
        return ProviderResult("ready", data)

    def extract(state):
        key = state["document"]["document_id"]
        calls.append(key)
        if key == "bad":
            return {"extractions": {key: dict(document_id=key, status="needs_review", record=None,
                    issues=[dict(code="missing_amount", message="A clearer image is needed.")])}}
        return fake_extract(state)

    g, c = graph(providers(intake=intake, extraction=extract)), config("allocation-resume")
    paused = await g.ainvoke(new_case("allocation-resume"), c)
    assert paused["__interrupt__"] and not paused["computation_result"]
    board = board_by_id(paused)
    assert board["extract:bad"]["request_owner"] == "intake"
    assert board["clarification"]["return_to"] == "intake"
    revision = paused["__interrupt__"][0].value["revision"]
    final = await g.ainvoke(Command(resume={"action": "resolve", "owner": "intake", "revision": revision,
                            "response": {"replacement_received": True}}), c)
    assert final["status"] == "ready_for_human_review" and final["revision"] == 2
    assert sorted(calls) == ["bad", "fixed", "w2-1"]
    assert set(final["extractions"]) == {"w2-1", "bad", "fixed"}
    board = board_by_id(final)
    assert "extract:bad" not in board and board["extract:fixed"]["status"] == "done"
    sources = [source["reference"] for amount in final["computation_input"]["amounts"]["1z"] for source in amount["sources"]]
    assert set(sources) == {"w2-1", "fixed"}


@pytest.mark.asyncio
async def test_same_failed_upload_is_not_retried_and_no_progress_stop_is_visible():
    calls = []
    def extract(state):
        calls.append(state["document"]["document_id"])
        return {"extractions": {"w2-1": dict(document_id="w2-1", status="rejected", record=None,
                issues=[dict(code="invalid_image", message="Replace this upload.")])}}
    final = await graph(providers(extraction=extract), no_progress_limit=1).ainvoke(new_case("no-repeat"), config("no-repeat"))
    assert calls == ["w2-1"]
    assert final["status"] == "blocked" and final["issues"][0]["code"] == "no_progress"
    assert final["task_plan"]["case_status"] == "blocked"
    assert final["task_plan"]["issue_codes"] == ["no_progress"]
    assert not any(t["status"] == "ready" for t in final["task_plan"]["tasks"])


@pytest.mark.asyncio
async def test_missing_provider_block_is_visible_in_board():
    result = await graph().ainvoke(new_case("missing-board"), config("missing-board"))
    assert result["status"] == result["task_plan"]["case_status"] == "blocked"
    assert result["task_plan"]["issue_codes"] == ["provider_not_configured"]
    assert not result["computation_result"]
