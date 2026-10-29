"""Test reviewer → orchestrator → human-review interruption."""

import pytest

from langgraph.types import Command

from src.agents.adversarial import make_adversarial_provider
from src.integration.graph import build_graph
from src.integration.state import new_case
from tests.integration.test_graph import providers


async def fake_model(messages):
    """Predictable response for testing routing only."""
    return {
        "findings": [{
            "code": "scope_conflict",
            "route_to": "human_review",
            "explanation": "Synthetic scope conflict requiring human review.",
            "evidence": ["rules_output.clearance"],
        }]
    }


@pytest.mark.asyncio
async def test_reviewer_finding_pauses_graph():
    reviewer = make_adversarial_provider(fake_model)

    # Existing helpers replace other agents with test-only workers.
    graph = build_graph(providers(adversarial=reviewer))

    config = {
        "configurable": {
            "thread_id": "test-adversarial-handoff"
        }
    }

    result = await graph.ainvoke(
        new_case("test-adversarial-handoff"),
        config,
    )

    # Verify an actual LangGraph interrupt, not just a status label.
    assert result.get("__interrupt__"), "Graph did not pause"

    payload = result["__interrupt__"][0].value
    assert "scope_conflict" in payload["issue_codes"]

    stages = [event["stage"] for event in result["events"]]
    assert stages[-2:] == ["adversarial", "human"]
    assert "complete" not in stages

    # The existing graph assigns scope-related human findings to Rules.
    assert payload["owner"] == "rules"

    # Verify that the paused case accepts a stop decision.
    stopped = await graph.ainvoke(
        Command(resume={"action": "stop"}),
        config,
    )

    assert stopped["status"] == "stopped"
    assert not stopped.get("__interrupt__")
    assert "complete" not in [
        event["stage"] for event in stopped["events"]
    ]

@pytest.mark.asyncio
async def test_human_resolution_resumes_workflow():
    import json

    from src.integration.contracts import ProviderResult
    from tests.integration.fixtures import rules_data

    marker = "TEST_ONLY_RECORD_CONFIRMED"

    async def test_rules(state):
        data = rules_data([
            document["document_id"]
            for document in state["documents"]
        ])

        resolution = state.get("human_response", {})

        # Simulate Rules validating the specific human response.
        if (
            resolution.get("owner") == "rules"
            and resolution.get("response", {}).get("resolution")
            == "verified_synthetic_record"
        ):
            data["clearance"]["citations"].append(marker)

        return ProviderResult("ready", data)

    async def test_model(messages):
        packet = json.loads(messages[-1]["content"])
        citations = packet["rules_output"]["clearance"]["citations"]

        # Only the updated evidence clears this test finding.
        if marker in citations:
            return {"findings": []}

        return {
            "findings": [{
                "code": "record_confirmation_required",
                "route_to": "human_review",
                "explanation": "Synthetic record needs confirmation.",
                "evidence": ["rules_output.clearance"],
            }]
        }

    graph = build_graph(providers(
        rules=test_rules,
        adversarial=make_adversarial_provider(test_model),
    ))

    config = {
        "configurable": {"thread_id": "test-review-resume"}
    }

    paused = await graph.ainvoke(
        new_case("test-review-resume"),
        config,
    )

    assert paused.get("__interrupt__")
    payload = paused["__interrupt__"][0].value

    resumed = await graph.ainvoke(
        Command(resume={
            "action": "resolve",
            "owner": payload["owner"],
            "revision": payload["revision"],
            "response": {
                "resolution": "verified_synthetic_record"
            },
        }),
        config,
    )

    assert not resumed.get("__interrupt__")
    assert resumed["status"] == "ready_for_human_review"

    stages = [event["stage"] for event in resumed["events"]]

    # Updated evidence must go through calculation and review again.
    assert stages.count("rules") == 2
    assert stages.count("compute") == 2
    assert stages.count("audit") == 2
    assert stages.count("adversarial") == 2
    assert stages[-1] == "complete"