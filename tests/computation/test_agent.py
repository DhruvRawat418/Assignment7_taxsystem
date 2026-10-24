from copy import deepcopy
from decimal import Decimal
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from src.agents.computation import compute, computation_node, computation_tools


class NoTools:
    async def call(self, name, arguments):
        raise AssertionError("No computation should run before clearance and valid inputs")


class BrokenTools:
    async def call(self, name, arguments):
        raise RuntimeError("Simulated unavailable tool")


def change(data, line, value):
    data["amounts"][line][0]["value"] = value


@pytest.mark.asyncio
async def test_real_mcp_clean_return_provenance_and_multiple_documents(request_data):
    async with computation_tools() as client:
        result = await compute(request_data, client)
        assert result.status == "completed", result.issues
        expected = {"9": "50000.00", "11a": "50000.00", "12e": "17750.00",
                    "13b": "6000.00", "14": "23750.00", "15": "26250.00",
                    "16": "2911.50", "24": "2911.50", "25d": "4000.00",
                    "33": "4000.00", "34": "1088.50", "37": "0.00"}
        for line, value in expected.items():
            assert result.lines[line].value == Decimal(value)
        calls = {call.call_id: call for call in result.tool_calls}
        audit_values = {**result.lines, **result.intermediates}
        assert set(result.intermediates) == {"ss_adjustments", "income_before_ss"}
        for line, amount in audit_values.items():
            assert amount.tool_call_id in calls
            assert amount.value == Decimal(calls[amount.tool_call_id].result["value"])
            assert calls[amount.tool_call_id].output_key == line
            assert all(dependency in audit_values for dependency in amount.depends_on)
            assert amount.rule_references
        assert result.lines["34"].sources  # transitive evidence reaches the final balance
        names = [call.tool for call in result.tool_calls]
        assert names.index("social_security_taxable") < names.index("senior_deduction") < names.index("income_tax")
        extra = deepcopy(request_data["amounts"]["1z"][0])
        extra["value"] = "1000.00"
        extra["sources"][0]["reference"] = "synthetic-w2-2"
        request_data["amounts"]["1z"].append(extra)
        result = await compute(request_data, client)
        assert result.lines["1z"].value == Decimal("51000.00")
        assert len(result.lines["1z"].sources) == 2


@pytest.mark.asyncio
async def test_real_mcp_social_security_dependency_and_payment_lines(request_data):
    change(request_data, "1z", "30000.00")
    change(request_data, "6a", "20000.00")
    change(request_data, "17", "100.00")
    change(request_data, "19", "200.00")
    change(request_data, "20", "300.00")
    change(request_data, "23", "50.00")
    change(request_data, "25b", "10.00")
    change(request_data, "25c", "20.00")
    change(request_data, "26", "30.00")
    change(request_data, "32", "40.00")
    async with computation_tools() as client:
        result = await compute(request_data, client)
    assert result.status == "completed"
    assert result.lines["6b"].value == Decimal("9600")
    assert result.lines["9"].value == Decimal("39600")
    assert result.lines["16"].value == Decimal("1663.50")
    assert result.lines["24"].value == Decimal("1313.50")
    assert result.lines["33"].value == Decimal("4100")
    assert result.lines["34"].value == Decimal("2786.50")


@pytest.mark.asyncio
async def test_real_mcp_negative_agi_and_credit_floor(request_data):
    change(request_data, "1z", "100.00")
    change(request_data, "10", "200.00")
    change(request_data, "19", "1000.00")
    async with computation_tools() as client:
        result = await compute(request_data, client)
    assert result.status == "completed"
    assert result.lines["11a"].value == Decimal("-100.00")
    for line in ("15", "16", "22", "24", "37"):
        assert result.lines[line].value == 0


@pytest.mark.parametrize("mutation", [
    lambda d: d["amounts"].pop("2a"),
    lambda d: d["amounts"].__setitem__("2a", []),
    lambda d: d["amounts"]["1z"][0].__setitem__("sources", []),
    lambda d: change(d, "1z", 0.1),
    lambda d: change(d, "1z", "NaN"),
    lambda d: change(d, "1z", "-1"),
    lambda d: d.__setitem__("tax_year", 2024),
    lambda d: d["profile"].__setitem__("filing_status", "unknown"),
    lambda d: d["profile"].__setitem__("taxpayer_65_or_older", "false"),
    lambda d: d["rules"].__setitem__("citations", [""]),
    lambda d: d["rules"].__setitem__("citations", ["   "]),
    lambda d: d["amounts"]["2a"][0]["sources"][0].pop("recorded_at"),
    lambda d: d["amounts"]["2a"][0]["sources"][0].__setitem__("recorded_at", "2026-10-24T00:00:00"),
])
@pytest.mark.asyncio
async def test_invalid_contract_does_not_compute(request_data, mutation):
    mutation(request_data)
    result = await compute(request_data, NoTools())
    assert result.status == "invalid_input"
    assert not result.lines and not result.tool_calls


@pytest.mark.asyncio
async def test_upstream_escalations_are_respected(request_data):
    for condition in ("1099_r_taxable_amount_not_determined", "tax_advice_request",
                      "unresolved_document_conflict", "out_of_scope", "financial_exploitation"):
        data = deepcopy(request_data)
        data["rules"]["blocking_conditions"] = [condition]
        result = await compute(data, NoTools())
        assert result.status == "needs_human_review"
        assert not result.lines and not result.tool_calls
    request_data["rules"]["approved"] = False
    assert (await compute(request_data, NoTools())).status == "needs_human_review"


@pytest.mark.asyncio
async def test_conflicting_amounts_and_tool_failure_never_emit_partial_returns(request_data):
    change(request_data, "3a", "1.00")  # qualified exceeds total ordinary dividends
    async with computation_tools() as client:
        result = await compute(request_data, client)
    assert result.status == "needs_human_review"
    assert not result.lines
    assert result.issues[0].code == "inconsistent_inputs"
    failed = await compute(request_data, BrokenTools())
    assert failed.status == "tool_error" and not failed.lines


@pytest.mark.asyncio
async def test_actual_langgraph_integration_and_reexecution_replaces_stale_result(request_data):
    class State(TypedDict, total=False):
        computation_input: dict
        computation_result: dict
        intake_marker: str

    builder = StateGraph(State)
    builder.add_node("computation", computation_node)
    builder.add_edge(START, "computation")
    builder.add_edge("computation", END)
    graph = builder.compile()
    original = deepcopy(request_data)
    output = await graph.ainvoke({"computation_input": request_data, "intake_marker": "preserve"})
    assert output["computation_result"]["status"] == "completed"
    assert output["intake_marker"] == "preserve" and request_data == original
    output["computation_input"]["rules"]["approved"] = False
    updated = await graph.ainvoke(output)
    assert updated["computation_result"]["status"] == "needs_human_review"
    assert updated["computation_result"]["lines"] == {}
    assert updated["computation_result"]["intermediates"] == {}
    assert set(await computation_node({})) == {"computation_result"}


@pytest.mark.asyncio
async def test_real_mcp_joint_spouse_eligibility_and_amount_owed(request_data):
    request_data["profile"] = {"filing_status": "mfj", "taxpayer_65_or_older": False,
                               "spouse_65_or_older": True, "taxpayer_blind": False,
                               "spouse_blind": False}
    change(request_data, "25a", "0.00")
    async with computation_tools() as client:
        result = await compute(request_data, client)
    assert result.status == "completed"
    assert result.lines["12e"].value == Decimal("33100")
    assert result.lines["13b"].value == Decimal("6000")
    assert result.lines["16"].value == Decimal("1090")
    assert result.lines["34"].value == 0
    assert result.lines["37"].value == Decimal("1090")


@pytest.mark.asyncio
async def test_malformed_tool_result_is_not_a_tax_return(request_data):
    class InvalidTools:
        async def call(self, name, arguments):
            return {"value": "NaN", "rule_references": ["test"]}

    result = await compute(request_data, InvalidTools())
    assert result.status == "tool_error" and not result.lines


@pytest.mark.parametrize("field", ["taxpayer_blind", "spouse_65_or_older", "spouse_blind"])
@pytest.mark.asyncio
async def test_missing_checkbox_answer_never_becomes_false(request_data, field):
    request_data["profile"]["filing_status"] = "mfj"
    del request_data["profile"][field]
    result = await compute(request_data, NoTools())
    assert result.status == "invalid_input"
    assert not result.lines and not result.intermediates and not result.tool_calls


@pytest.mark.parametrize("line,conflicting", [("1z", False), ("1z", True), ("2a", False)])
@pytest.mark.asyncio
async def test_repeated_document_or_direct_input_is_not_counted_twice(request_data, line, conflicting):
    repeat = deepcopy(request_data["amounts"][line][0])
    if conflicting:
        repeat["value"] = "1.00"
    request_data["amounts"][line].append(repeat)
    result = await compute(request_data, NoTools())
    assert result.status == "needs_human_review"
    assert any(issue.code == "duplicate_input_source" for issue in result.issues)
    assert not result.lines and not result.intermediates and not result.tool_calls
