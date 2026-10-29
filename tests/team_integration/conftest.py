"""Opt-in tests against explicit teammate checkouts, isolated from their working files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("computation team integration")
    for owner in ("rules", "integration", "extraction"):
        group.addoption(f"--{owner}-root", help=f"Explicit local {owner} checkout/snapshot")


@pytest.fixture(scope="session")
def team_workspace(request, tmp_path_factory):
    options = {owner: request.config.getoption(f"--{owner}-root")
               for owner in ("rules", "integration", "extraction")}
    if not any(options.values()):
        pytest.skip("Opt-in: supply --rules-root, --integration-root and --extraction-root")
    if not all(options.values()):
        raise pytest.UsageError("Supply all three teammate checkout paths")
    roots = {owner: Path(path).resolve() for owner, path in options.items()}
    required = {"rules": "src/agents/eligibility.py",
                "integration": "src/integration/graph.py",
                "extraction": "src/document_extraction/models.py"}
    for owner, relative in required.items():
        if not (roots[owner] / relative).is_file():
            raise pytest.UsageError(f"{owner} checkout is missing {relative}")

    workspace = tmp_path_factory.mktemp("computation-team")
    own_root = Path(__file__).resolve().parents[2]
    # The current branch's Computation wins over any older integration copy.
    # No teammate source is vendored or changed in the contributor checkouts.
    for root in (roots["integration"], roots["extraction"], roots["rules"], own_root):
        shutil.copytree(root / "src", workspace / "src", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(own_root / "demo/computation_clean.json", workspace / "computation_clean.json")
    shutil.copy2(Path(__file__).with_name("worker.py"), workspace / "team_probe_worker.py")
    return workspace


@pytest.fixture(scope="session")
def team_probe(team_workspace):
    def run(scenario):
        environment = dict(os.environ, LANGSMITH_TRACING="false")
        completed = subprocess.run(
            [sys.executable, "team_probe_worker.py", scenario], cwd=team_workspace,
            env=environment, capture_output=True, text=True, timeout=90,
        )
        if completed.returncode:
            pytest.fail("Synthetic team probe failed:\n" + completed.stderr[-3000:])
        return json.loads(completed.stdout)
    return run
