from copy import deepcopy
from itertools import permutations
from threading import Barrier

import pytest
from langgraph.types import Command

from examples.hitl_extraction import build_graph as hitl_graph
from examples.parallel_extraction import build_graph
from src.agents.document_extraction import merge_extractions
from src.document_extraction.validation import validate_synthetic_ssn
from tests.test_extraction import ROOT, clean_tokens, parse


class FakeEngine:
    name = "test"

    def read(self, image):
        return clean_tokens()


class MissingEngine(FakeEngine):
    def read(self, image):
        return [t for t in clean_tokens() if t.text != "3,125.50"]


def request(doc_id="test"):
    return {"document_id": doc_id, "path": str(ROOT/"demo/w2_clean.jpg")}


def test_merge_order_and_idempotency():
    parts = [{str(i): parse(clean_tokens()).model_dump(mode="json")} for i in range(3)]
    outputs = []
    for order in permutations(parts):
        merged = {}
        for part in order:
            merged = merge_extractions(merged, part)
        outputs.append(merged)
    assert all(output == outputs[0] for output in outputs)
    assert merge_extractions(outputs[0], outputs[0]) == outputs[0]


def test_merge_retries_only_differing_in_timestamp_are_commutative():
    first = {"a": parse(clean_tokens()).model_dump(mode="json")}
    second = deepcopy(first)
    second["a"]["record"]["amounts"]["1"]["source"]["timestamp"] = "2099-01-01T00:00:00Z"
    assert merge_extractions(first, second) == merge_extractions(second, first)


def test_merge_rejects_conflicting_payload_for_same_upload():
    first = {"a": parse(clean_tokens()).model_dump(mode="json")}
    second = deepcopy(first)
    second["a"]["record"]["amounts"]["1"]["value"] = "99999.00"
    with pytest.raises(ValueError, match="Conflicting extraction"):
        merge_extractions(first, second)


def test_langgraph_really_runs_parallel_workers_and_aggregates():
    barrier = Barrier(2)

    class ConcurrentEngine(FakeEngine):
        def read(self, image):
            barrier.wait(timeout=10)  # Would fail if workers ran sequentially.
            return clean_tokens()

    result = build_graph(ConcurrentEngine).invoke({"documents": [request("a"), request("b")],
        "extractions": {}}, {"max_concurrency": 2})
    assert set(result["extractions"]) == {"a", "b"}
    assert all(r["status"] == "extracted" for r in result["extractions"].values())


def test_empty_parallel_batch_terminates():
    result = build_graph(FakeEngine).invoke({"documents": [], "extractions": {}})
    assert result["extractions"] == {}


def test_interrupt_resume_reextracts_and_retains_original():
    calls = 0

    class ChangingEngine(FakeEngine):
        def read(self, image):
            nonlocal calls
            calls += 1
            return MissingEngine().read(image) if calls == 1 else clean_tokens()

    graph = hitl_graph(ChangingEngine)
    config = {"configurable": {"thread_id": "resolved"}}
    result = graph.invoke({"document": request("original"), "extractions": {}, "attempts": 0}, config)
    assert result["__interrupt__"]
    result = graph.invoke(Command(resume={"replacement_path": request()["path"]}), config)
    assert "__interrupt__" not in result
    assert result["extractions"]["original"]["status"] == "needs_review"
    assert result["extractions"]["W2#replacement-1"]["status"] == "extracted"


def test_unresolved_handoff_loop_stops_after_three_replacements():
    graph = hitl_graph(MissingEngine)
    config = {"configurable": {"thread_id": "bounded"}, "recursion_limit": 20}
    result = graph.invoke({"document": request("original"), "extractions": {}, "attempts": 0}, config)
    for _ in range(3):
        assert result["__interrupt__"]
        result = graph.invoke(Command(resume={"replacement_path": request()["path"]}), config)
    assert "__interrupt__" not in result
    assert result["attempts"] == 3
    assert result["extractions"][result["document"]["document_id"]]["status"] == "needs_review"


def test_human_can_stop_without_inventing_missing_amount():
    graph = hitl_graph(MissingEngine)
    config = {"configurable": {"thread_id": "stop"}}
    result = graph.invoke({"document": request(), "extractions": {}}, config)
    result = graph.invoke(Command(resume={"action": "stop"}), config)
    assert result["stopped"]
    assert result["extractions"]["test"]["status"] == "needs_review"


@pytest.mark.parametrize("text", ["900-12-3456", "999123456", "901 12 3456"])
def test_shared_intake_ssn_validator(text):
    assert validate_synthetic_ssn(text).startswith(("900-", "999-", "901-"))


@pytest.mark.parametrize("text", ["899-12-3456", "123-45-6789", "901-12-345", "abc", ""])
def test_shared_intake_ssn_validator_rejects(text):
    with pytest.raises(ValueError) as error:
        validate_synthetic_ssn(text)
    assert text not in str(error.value) or not text
