"""Test actual graph orchestration with explicit test-only worker providers."""
from copy import deepcopy
from threading import Barrier
import pytest
from langgraph.types import Command
from src.agents.audit import input_fingerprint
from src.integration.contracts import ProviderResult, Providers
from tests.audit.fixtures import clean_state
from tests.integration.fixtures import extracted, intake_data, rules_data

from src.integration.graph import build_graph
from src.integration.state import new_case


def fake_extract(state):
    doc_id = state["document"]["document_id"]
    sha = "a" * 64 if doc_id == "w2-1" else "b" * 64
    return {"extractions": {doc_id: extracted(doc_id, sha)}}


async def fake_compute(state):
    return {"computation_result": deepcopy(clean_state()["computation_result"])}


async def fake_audit(packet):
    return {"audit_result": dict(status="passed", issues=[], input_fingerprint=input_fingerprint(packet),
                                  review_scope="deterministic_component", draft_only=True)}


def providers(**overrides):
    async def intake(state):
        return ProviderResult("ready", intake_data())
    async def rules(state):
        return ProviderResult("ready", rules_data([d["document_id"] for d in state["documents"]]))
    async def adversarial(state):
        return ProviderResult("ready", {"findings": []})
    values = dict(intake=intake, rules=rules, adversarial=adversarial,
                  extraction=fake_extract, computation=fake_compute, audit=fake_audit, mode="synthetic")
    return Providers(**(values | overrides))


def graph(p=None, **kwargs):
    return build_graph(p, **kwargs)


def config(case_id="graph-test"):
    return {"configurable": {"thread_id": case_id}}


@pytest.mark.asyncio
async def test_default_is_blocked_without_intake_not_a_finished_return():
    result = await graph().ainvoke(new_case("default"), config("default"))
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "provider_not_configured"
    assert not result.get("computation_result")


@pytest.mark.asyncio
async def test_configured_pipeline_reaches_reviewable_state_not_filed_form():
    initial = new_case("clean")
    before = deepcopy(initial)
    result = await graph(providers()).ainvoke(initial, config("clean"))
    assert result["status"] == "ready_for_human_review"
    assert initial == before
    assert result["mode"] == "synthetic"
    assert result["review_attempts"] == 1
    assert "filed" not in result and "filled_form" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["rules", "adversarial"])
async def test_missing_required_provider_cannot_be_bypassed(owner):
    result = await graph(providers(**{owner: None})).ainvoke(new_case("missing"), config("missing"))
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_extraction_workers_really_overlap_and_merge_both_results():
    barrier = Barrier(2)
    def concurrent_extract(state):
        barrier.wait(timeout=5)
        return fake_extract(state)
    async def intake(state):
        data = intake_data()
        data["documents"].append(dict(document_id="w2-2", path="demo/w2_clean.jpg"))
        return ProviderResult("ready", data)
    result = await graph(providers(intake=intake, extraction=concurrent_extract)).ainvoke(new_case("parallel"), config("parallel"))
    assert result["status"] == "ready_for_human_review"
    assert set(result["extractions"]) == {"w2-1", "w2-2"}


@pytest.mark.asyncio
async def test_empty_document_inventory_has_a_real_non_fanout_path():
    async def intake(state):
        return ProviderResult("ready", intake_data(documents=False))
    result = await graph(providers(intake=intake)).ainvoke(new_case("empty"), config("empty"))
    assert result["status"] == "ready_for_human_review"
    assert result["extractions"] == {}


async def human_rules(state):
    response = state.get("human_response", {})
    if response.get("owner") == "rules" and response.get("response", {}).get("resolution") == "verified":
        return ProviderResult("ready", rules_data([d["document_id"] for d in state["documents"]]))
    return ProviderResult("needs_human_review", issue_codes=("source_conflict",))


@pytest.mark.asyncio
async def test_actual_interrupt_and_valid_resume_reinvoke_rules():
    g, c = graph(providers(rules=human_rules)), config("resume")
    paused = await g.ainvoke(new_case("resume"), c)
    assert paused["__interrupt__"]
    assert not paused.get("computation_result")
    payload = paused["__interrupt__"][0].value
    result = await g.ainvoke(Command(resume=dict(action="resolve", owner="rules", revision=payload["revision"],
                                               response={"resolution": "verified"})), c)
    assert result["status"] == "ready_for_human_review"
    assert not result["human_response"]  # Consumed once by Rules, not retained as a reusable approval.


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [True, {"approved": True}, {"action": "resolve", "owner": "rules", "revision": -1, "response": {}}])
async def test_raw_approval_or_wrong_revision_cannot_patch_state(response):
    g, c = graph(providers(rules=human_rules)), config("bad-resume")
    await g.ainvoke(new_case("bad-resume"), c)
    result = await g.ainvoke(Command(resume=response), c)
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "invalid_human_response"
    assert not result.get("computation_result")


@pytest.mark.asyncio
async def test_human_can_stop_without_clearing_rules():
    g, c = graph(providers(rules=human_rules)), config("stop")
    await g.ainvoke(new_case("stop"), c)
    result = await g.ainvoke(Command(resume={"action": "stop"}), c)
    assert result["status"] == "stopped"
    assert not result.get("computation_result")


@pytest.mark.asyncio
async def test_forged_or_stale_audit_fingerprint_prevents_final_readiness():
    async def old_audit(packet):
        output = await fake_audit(packet)
        output["audit_result"]["input_fingerprint"] = "0" * 64
        return output
    result = await graph(providers(audit=old_audit)).ainvoke(new_case("stale"), config("stale"))
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "stale_audit"


@pytest.mark.asyncio
async def test_review_revise_loop_is_explicitly_bounded():
    async def revise(packet):
        return {"audit_result": {"status": "revision_required", "issues": [{"code": "test_error", "route_to": "computation"}]}}
    result = await graph(providers(audit=revise), max_review_attempts=1, no_progress_limit=10).ainvoke(new_case("limit"), config("limit"))
    assert result["status"] == "blocked"
    assert result["review_attempts"] == 1
    assert result["issues"][0]["code"] == "review_limit"


@pytest.mark.asyncio
async def test_no_progress_guard_ignores_changing_call_uuids_and_timestamps():
    count = 0
    async def compute(state):
        nonlocal count
        count += 1
        output = await fake_compute(state)
        output["computation_result"]["tool_calls"][0]["call_id"] = f"new-{count}"
        output["computation_result"]["checked_at"] = f"new-time-{count}"
        return output
    async def revise(packet):
        return {"audit_result": {"status": "revision_required", "issues": [{"code": "same_error", "route_to": "computation"}]}}
    result = await graph(providers(computation=compute, audit=revise), max_review_attempts=20, no_progress_limit=1).ainvoke(new_case("cycle"), config("cycle"))
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "no_progress"
    assert count < 10


@pytest.mark.asyncio
async def test_supervisor_hop_limit_is_not_just_framework_recursion_error():
    result = await graph(providers(), max_hops=2).ainvoke(new_case("hops"), config("hops"))
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "hop_limit"


@pytest.mark.asyncio
async def test_provider_failure_and_unsafe_identifier_are_sanitized():
    async def broken(state):
        raise RuntimeError("secret-123-45-6789")
    result = await graph(providers(intake=broken)).ainvoke(new_case("error"), config("error"))
    assert result["status"] == "blocked"
    assert "secret" not in str(result)
    async def unsafe(state):
        data = intake_data()
        data["facts"]["ssn"] = "123-45-6789"
        return ProviderResult("ready", data)
    result = await graph(providers(intake=unsafe)).ainvoke(new_case("privacy"), config("privacy"))
    assert result["status"] == "blocked" and not result["intake_snapshot"]
    assert "123-45-6789" not in str(result)


@pytest.mark.asyncio
async def test_missing_findings_is_not_an_adversarial_pass():
    async def bogus(state):
        return ProviderResult("ready", {"approved": True})
    result = await graph(providers(adversarial=bogus)).ainvoke(new_case("bogus"), config("bogus"))
    assert result["status"] == "blocked"


@pytest.mark.asyncio
async def test_changed_intake_invalidates_previous_computation_and_review():
    calls = 0
    async def intake(state):
        data = intake_data()
        if state.get("issues"):
            data["amounts"]["2a"][0]["value"] = "1.00"
        return ProviderResult("ready", data)
    async def compute(state):
        nonlocal calls
        calls += 1
        assert not state.get("audit_result")
        return await fake_compute(state)
    async def review(state):
        if state["revision"] == 1:
            return ProviderResult("ready", {"findings": [{"code": "clarify_input", "route_to": "intake"}]})
        return ProviderResult("ready", {"findings": []})
    result = await graph(providers(intake=intake, computation=compute, adversarial=review)).ainvoke(new_case("changed"), config("changed"))
    assert result["status"] == "ready_for_human_review"
    assert result["revision"] == 2 and calls == 2
    assert result["computation_input"]["amounts"]["2a"][0]["value"] == "1.00"


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_id", [False, True])
async def test_corrected_upload_uses_new_id_and_retains_original_history(reuse_id):
    async def intake(state):
        data = intake_data()
        if state.get("issues"):
            data["documents"] = [dict(document_id="w2-1" if reuse_id else "w2-2", path="corrected-w2.jpg")]
        return ProviderResult("ready", data)
    async def review(state):
        if state["revision"] == 1:
            return ProviderResult("ready", {"findings": [{"code": "replace_upload", "route_to": "intake"}]})
        return ProviderResult("ready", {"findings": []})
    result = await graph(providers(intake=intake, adversarial=review)).ainvoke(new_case("replace"), config("replace"))
    if reuse_id:
        assert result["status"] == "blocked"
        assert result["issues"][0]["code"] == "upload_id_reused"
    else:
        assert result["status"] == "ready_for_human_review"
        assert set(result["extractions"]) == {"w2-1", "w2-2"}
        assert [d["document_id"] for d in result["documents"]] == ["w2-2"]
        assert result["extractions"]["w2-1"]["sha256"] == "a" * 64


@pytest.mark.asyncio
async def test_new_intake_revision_cannot_reuse_prior_human_resolution():
    seen = []
    async def intake(state):
        data = intake_data()
        if state["revision"] > 0:
            data["amounts"]["2a"][0]["value"] = "1.00"
        return ProviderResult("ready", data)
    async def rules(state):
        seen.append((state["revision"], bool(state.get("human_response"))))
        return await human_rules(state)
    async def review(state):
        return ProviderResult("ready", {"findings": [{"code": "new_fact", "route_to": "intake"}]})
    g, c = graph(providers(intake=intake, rules=rules, adversarial=review)), config("new-resolution")
    paused = await g.ainvoke(new_case("new-resolution"), c)
    revision = paused["__interrupt__"][0].value["revision"]
    result = await g.ainvoke(Command(resume=dict(action="resolve", owner="rules", revision=revision,
                                               response={"resolution": "verified"})), c)
    assert result["__interrupt__"]
    assert result["__interrupt__"][0].value["revision"] == 2
    assert seen[-1] == (2, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["extraction", "computation", "audit", "adversarial"])
async def test_malformed_worker_output_cannot_poison_checkpoint(owner):
    def extraction(state):
        output = fake_extract(state)
        output["extractions"][state["document"]["document_id"]]["record"]["amounts"]["1"]["value"] = float("nan")
        return output
    async def computation(state):
        output = await fake_compute(state)
        output["computation_result"]["bad_metadata"] = float("nan")
        return output
    async def audit(packet):
        output = await fake_audit(packet)
        output["audit_result"]["bad_metadata"] = float("nan")
        return output
    async def adversarial(state):
        return ProviderResult("ready", {"findings": [{"code": "bad", "route_to": "rules", "value": float("nan")}]})
    bad = dict(extraction=extraction, computation=computation, audit=audit, adversarial=adversarial)
    g, c = graph(providers(**{owner: bad[owner]})), config("malformed")
    result = await g.ainvoke(new_case("malformed"), c)
    assert result["status"] == "blocked"
    assert "nan" not in str(result).lower()
    assert not g.get_state(c).next
    resumed = await g.ainvoke(None, c)
    assert resumed["status"] == "blocked"


@pytest.mark.asyncio
async def test_consumed_human_resolution_cannot_resolve_a_later_rules_issue():
    async def review(state):
        return ProviderResult("ready", {"findings": [{"code": "new_rules_conflict", "route_to": "rules"}]})
    g, c = graph(providers(rules=human_rules, adversarial=review)), config("one-use")
    paused = await g.ainvoke(new_case("one-use"), c)
    revision = paused["__interrupt__"][0].value["revision"]
    result = await g.ainvoke(Command(resume=dict(action="resolve", owner="rules", revision=revision,
                                               response={"resolution": "verified"})), c)
    assert result["__interrupt__"]
    assert result["__interrupt__"][0].value["owner"] == "rules"
    assert not result.get("human_response")


@pytest.mark.asyncio
async def test_distinct_human_clarifications_count_as_progress_at_default_limits():
    answers = []
    async def rules(state):
        answer = state.get("human_response", {}).get("response", {}).get("answer")
        if answer:
            answers.append(answer)
        if answer == "complete":
            return ProviderResult("ready", rules_data())
        return ProviderResult("needs_human_review", issue_codes=("clarify_rules",))
    g, c = graph(providers(rules=rules)), config("clarifications")
    result = await g.ainvoke(new_case("clarifications"), c)
    for answer in ("first-fact", "second-fact", "complete"):
        payload = result["__interrupt__"][0].value
        result = await g.ainvoke(Command(resume=dict(action="resolve", owner="rules", revision=payload["revision"],
                                                   response={"answer": answer})), c)
    assert result["status"] == "ready_for_human_review"
    assert answers == ["first-fact", "second-fact", "complete"]
