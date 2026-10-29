"""Published Rules -> mapping -> this branch's real Computation/MCP -> Audit."""
import pytest


@pytest.mark.parametrize("scenario,deduction,senior,wage_sources", [
    ("single", "17750.00", "6000.00", 1),
    ("joint_one_senior", "33100.00", "6000.00", 1),
    ("joint_both_senior", "34700.00", "12000.00", 1),
    ("multiple_w2", "17750.00", "6000.00", 2),
    ("extra_boxes", "17750.00", "6000.00", 1),
])
def test_rules_computation_and_audit(team_probe, scenario, deduction, senior, wage_sources):
    result = team_probe(scenario)
    assert result["rules_status"] == "ready"
    assert result["computation_status"] == "completed"
    assert result["audit_status"] == "passed"
    assert result["verified_lines"] == 40
    assert result["lines"]["1z"] == "50000.00"
    assert result["lines"]["25a"] == "4000.00"
    assert result["lines"]["12e"] == deduction
    assert result["lines"]["13b"] == senior
    assert result["wage_sources"] == wage_sources
    assert result["input_unchanged"]
    if scenario == "extra_boxes":
        assert result["projection_notes"][0]["excluded_boxes"] == ["3", "4"]


@pytest.mark.parametrize("scenario,expected", [
    ("rules_blocked", "needs_human_review"),
    ("missing_spouse", "needs_input"),
])
def test_uncleared_rules_never_reach_computation(team_probe, scenario, expected):
    result = team_probe(scenario)
    assert result["rules_status"] == expected
    assert result["computation_calls"] == 0
    assert not result.get("lines")


def test_missing_amount_never_becomes_zero(team_probe):
    result = team_probe("missing_amount")
    assert result["rules_status"] == "ready"
    assert result["mapping_error"]
    assert result["computation_calls"] == 0
    assert not result.get("lines")


def test_audit_rejects_consistently_tampered_record(team_probe):
    result = team_probe("tampered")
    assert result["computation_status"] == "completed"
    assert result["audit_status"] == "revision_required"
    assert "recomputed_value_mismatch" in result["audit_issue_codes"]


def test_projected_rules_in_actual_supervisor_graph(team_probe):
    result = team_probe("graph")
    assert result["status"] == "ready_for_human_review"
    assert result["audit_status"] == "passed"
    assert result["computation_calls"] == 1
    assert result["projection"] == "test_only_three_key_rules_packet"


def test_published_rules_packet_directly_matches_adapter(team_probe):
    result = team_probe("raw_contract")
    if (result["rules_status"] == "ready"
            and result["unexpected_keys"] == ["line_12d_boxes"]
            and result["missing_keys"] == []
            and result["projected_mapping_error"] is None
            and result["mapping_error"] == "invalid_mapping"):
        pytest.xfail("Published Rules adds line_12d_boxes; integration accepts exactly three keys. "
                     "Rules/Orchestrator owners must agree on metadata handling.")
    assert result["rules_status"] == "ready"
    assert result["mapping_error"] is None
