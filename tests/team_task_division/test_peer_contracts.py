"""Optional cross-checkout probe. Never imports or edits peers in place."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.ocr
def test_real_team_handoff_and_known_contract_blocker(tmp_path):
    names = ("SILVERFILE_TEAM_INTAKE", "SILVERFILE_TEAM_RULES", "SILVERFILE_TEAM_COMPUTATION")
    paths = [os.environ.get(name) for name in names]
    if not any(paths):
        pytest.skip("Set the three SILVERFILE_TEAM_* checkout paths to run the real peer probe")
    if not all(paths):
        pytest.fail("All three teammate checkout paths are required")
    intake_root, rules_root, computation_root = map(Path, paths)
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "demo").mkdir()
    shutil.copy2(root / "demo/w2_clean.jpg", tmp_path / "demo/w2_clean.jpg")
    # Bring in each owner's actual files only, without overwriting our supervisor.
    groups = ((intake_root, "src/agents/intake*.py"), (rules_root, "src/agents/eligibility*.py"),
              (computation_root, "src/agents/computation*.py"), (computation_root, "src/tools/*.py"))
    for checkout, pattern in groups:
        files = list(checkout.glob(pattern))
        assert files, f"Missing {pattern} in {checkout}"
        for file in files:
            shutil.copy2(file, tmp_path / file.relative_to(checkout))
    shutil.copy2(Path(__file__).with_name("worker.py"), tmp_path / "probe.py")
    run = subprocess.run([sys.executable, "probe.py"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    raw, smoke = report["raw_contract"], report["projected_smoke"]
    assert raw["status"] == "blocked" and raw["issues"] == [{"code": "invalid_mapping", "owner": "rules"}]
    assert raw["tool_calls"] == 0
    assert smoke["status"] == "ready_for_human_review" and smoke["audit_status"] == "passed"
    assert smoke["tool_calls"] == 40
    assert smoke["stages"] == ["intake", "extract", "rules", "compute", "audit", "adversarial", "complete"]
    assert report["test_only_adversarial"] and not report["full_system_verified"]
    # Retain a machine-readable report when -s is requested.
    print(json.dumps(report, sort_keys=True))
