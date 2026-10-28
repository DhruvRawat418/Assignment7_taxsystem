"""Entrypoint tests run the real CLI and local MCP server, not a CLI double."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    result = subprocess.run([sys.executable, "run.py", *args], cwd=ROOT,
                            text=True, capture_output=True, timeout=90)
    assert result.stdout.strip(), result.stderr
    return result, json.loads(result.stdout)


def test_default_cli_blocks_and_does_not_print_taxpayer_state():
    result, data = run()
    assert result.returncode == 2
    assert data["status"] == "blocked"
    assert data["issues"] == [{"code": "provider_not_configured", "owner": "intake"}]
    assert data["filed"] is False
    assert "intake_snapshot" not in data


def test_readiness_is_configuration_not_a_claim_all_components_work():
    result, data = run("--readiness")
    assert result.returncode == 0
    assert data["providers"]["rules"] == "not_configured"
    assert data["providers"]["adversarial_review"] == "not_configured"
    assert data["providers"]["dashboard"] == "not_implemented"
    assert data["production_ready"] is False


@pytest.mark.parametrize("flag", ["--synthetic-demo", "--synthetic-hitl-demo"])
def test_labelled_demo_really_uses_mcp_and_audit_without_claiming_real_agents(flag):
    result, data = run(flag, "--task-plan")
    assert result.returncode == 0, data
    assert data["status"] == "ready_for_human_review"
    assert data["mode"] == "synthetic"
    assert data["llm_called"] is False and data["ocr_used"] is False
    assert set(data["test_only_providers"]) == {"intake", "rules", "extraction", "adversarial_review"}
    assert data["computation_tool_calls"] == 40
    assert data["audit_status"] == "passed"
    assert data["audit_checks"] > 0
    assert data["filed"] is False
    assert data["human_interrupt_resumed"] is (flag == "--synthetic-hitl-demo")
    assert data["production_ready"] is False
    assert "refund" not in data and "filled_form" not in data
    assert data["task_plan"]["case_status"] == "ready_for_human_review"
    assert data["task_plan"]["tasks"][-1]["task_id"] == "final_review"
    assert "demo/w2_clean.jpg" not in json.dumps(data["task_plan"])


def test_invalid_case_id_has_a_sanitized_error_not_a_traceback():
    result, data = run("--case-id", "invalid case")
    assert result.returncode == 2
    assert data["issues"][0]["code"] == "invalid_case_id"
    assert "Traceback" not in result.stderr
