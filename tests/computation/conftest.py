import json
from pathlib import Path

import pytest


@pytest.fixture
def request_data():
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "demo/computation_clean.json").read_text())
