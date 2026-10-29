"""Intake -> team contract. These tests use the teammates' real code, not copies:
the orchestrator's intake validator and adapter, Computation's request model, and
Eligibility if its branch is merged. No API key, no OCR."""
import asyncio
import json

import pytest

from src.agents.computation_contract import INPUT_LINES, ComputationRequest
from src.agents.intake import initial_intake_state, next_field
from src.agents.intake_contract import make_intake_provider, not_ready_reason, to_packet
from src.integration.adapters import prepare_packet, validate_intake
from tests.integration.fixtures import extracted, rules_data
from tests.intake.test_agent import NO_SCOPE, answer

SINGLE_W2_SSA = ["single", "March 5, 1955", "no", "no", *NO_SCOPE, "W-2 and SSA-1099", "w2_clean.jpg",
                 "$24,000", "none", "no", "no"]


def interview(replies):
    s = initial_intake_state()
    for r in replies:
        s = answer(s, r)
    if next_field(s) is None:
        s["intake_complete"] = True
    return s


def provider_for(session):
    return make_intake_provider(lambda case_id: session)


def test_finished_interview_passes_the_orchestrator_validator():
    packet = to_packet(interview(SINGLE_W2_SSA))
    assert validate_intake(packet) == packet
    assert packet["facts"]["filing_status"] == "single"
    assert packet["facts"]["taxpayer_date_of_birth"] == "1955-03-05"
    assert packet["documents"][0]["path"] == "w2_clean.jpg"


def test_amounts_cover_every_line_except_the_w2_lines():
    amounts = to_packet(interview(SINGLE_W2_SSA))["amounts"]
    assert set(amounts) == set(INPUT_LINES) - {"1z", "25a"}
    assert amounts["6a"][0]["value"] == "24000.00"
    assert amounts["6a"][0]["sources"][0]["entered_by"] == "taxpayer"
    assert amounts["2b"][0]["value"] == "0.00"  # no 1099-INT listed: a confirmed zero, with a source


def test_packet_reaches_computation_through_the_real_adapter():
    """Same check Jijuan does for Rules: the adapter must build a valid computation request."""
    session = interview(SINGLE_W2_SSA)
    packet = to_packet(session)
    document_id = packet["documents"][0]["document_id"]
    rules = rules_data(document_ids=(document_id,))
    built = prepare_packet(packet, rules, {document_id: extracted(document_id)})
    request = ComputationRequest.model_validate(built["computation_input"])
    assert str(request.amounts["1z"][0].value) == "50000.00"  # from the W-2 image, not from Intake
    assert str(request.amounts["6a"][0].value) == "24000.00"


def test_no_w2_means_intake_supplies_wages_as_zero():
    replies = ["single", "March 5, 1955", "no", "no", *NO_SCOPE, "SSA-1099", "$24,000", "none", "no", "no"]
    packet = to_packet(interview(replies))
    assert packet["documents"] == []
    assert packet["amounts"]["1z"][0]["value"] == "0.00"
    prepare_packet(packet, rules_data(document_ids=()), {})


def test_1099r_goes_to_ira_or_pension_lines():
    base = ["single", "March 5, 1955", "no", "no", *NO_SCOPE, "1099-R"]
    ira = to_packet(interview([*base, "yes", "$10,000", "$10,000", "no", "$1,000", "no", "no"]))["amounts"]
    pension = to_packet(interview([*base, "no", "$8,000", "$6,000", "no", "none", "no", "no"]))["amounts"]
    assert ira["4a"][0]["value"] == "10000.00" and ira["5a"][0]["value"] == "0.00"
    assert pension["5b"][0]["value"] == "6000.00" and pension["4b"][0]["value"] == "0.00"
    assert ira["25b"][0]["value"] == "1000.00"


def test_synthetic_dependent_details_reach_handoff():
    replies = ["single", "March 5, 1955", "no", "yes", "Lily", "Park", "granddaughter", "901-23-4567", "no",
               *NO_SCOPE, "SSA-1099", "$24,000", "none", "no", "no"]
    packet = to_packet(interview(replies))
    assert packet["facts"]["dependents"][0]["ssn"] == "901-23-4567"
    assert packet["facts"]["dependents"][0]["last_name"] == "Park"
    assert not packet["facts"]["free_text_notes"]


def test_guardrail_signals_become_eligibility_facts():
    s = interview(["Should I convert my IRA to a Roth?", *SINGLE_W2_SSA])
    assert to_packet(s)["facts"]["requested_advice"] is True


def test_provider_waits_until_the_interview_is_done():
    half = interview(SINGLE_W2_SSA[:3])
    result = provider_for(half)({"case_id": "c1", "issues": []})
    assert result.status == "needs_input" and result.issue_codes == ("intake_not_finished",)
    assert not_ready_reason(interview(["I'm not sure", *SINGLE_W2_SSA[1:]])) == "intake_unsure_answer"


def test_provider_does_not_resend_the_same_answers_when_sent_back():
    session = interview(SINGLE_W2_SSA)
    provider = provider_for(session)
    first = provider({"case_id": "c1", "issues": []})
    assert first.status == "ready"
    again = provider({"case_id": "c1", "intake_snapshot": first.data,
                      "issues": [{"code": "document_requires_attention", "owner": "intake"}]})
    assert again.status == "needs_input" and again.issue_codes == ("document_requires_attention",)


def test_team_graph_runs_intake_then_rules():
    """End to end in the real orchestrator. Extraction is the bundled synthetic fixture;
    Rules is Jijuan's agent when her branch is merged."""
    eligibility = pytest.importorskip("src.agents.eligibility")
    from src.integration.contracts import Providers
    from src.integration.graph import build_graph
    from src.integration.state import new_case

    packet = to_packet(interview(SINGLE_W2_SSA))
    document_id = packet["documents"][0]["document_id"]

    def extraction(state):
        return {"extractions": {document_id: extracted(document_id)}}

    def rules(state):
        # Eligibility adds "line_12d_boxes" for the dashboard, but prepare_packet accepts
        # exactly three keys, so the real pairing fails with invalid_mapping. Reported to
        # the team; dropped here so this test checks Intake, not that mismatch.
        result = eligibility.eligibility(state)
        result.data.pop("line_12d_boxes", None)
        return result

    graph = build_graph(Providers(intake=provider_for(interview(SINGLE_W2_SSA)),
                                  rules=rules, extraction=extraction))
    state = asyncio.run(graph.ainvoke(new_case("intake-e2e"), {"configurable": {"thread_id": "intake-e2e"}}))
    stages = [e["stage"] for e in state["events"]]
    assert stages[:4] == ["intake", "extract", "rules", "compute"]
    # No adversarial reviewer exists yet, so the honest end state is "blocked" at that step.
    assert state["issues"][0]["owner"] == "adversarial"
