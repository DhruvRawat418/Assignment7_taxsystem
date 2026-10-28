"""Offline export tests. Synthetic providers test rendering, not tax correctness."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader
from pdf_export import build_pdf, validate_export_state, verify_pdf, field_name, PREFIX
from src.integration.graph import build_graph
from src.integration.state import new_case
from tests.integration.test_graph import providers

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "assets" / "f1040s--2025.pdf"


@pytest.fixture
def reviewed():
    async def run():
        graph = build_graph(providers())
        return await graph.ainvoke(new_case("pdf-test"), {"configurable": {"thread_id": "pdf-test"}})
    return asyncio.run(run())


def test_export_places_values_on_form_and_preserves_evidence(reviewed):
    before = deepcopy(reviewed)
    pdf, evidence, notes = build_pdf(reviewed, TEMPLATE)
    reader = PdfReader(BytesIO(pdf))
    fields = reader.get_fields()
    assert len(reader.pages) == 4
    # Independent expected positions for the synthetic fixture.
    expected = {
        "Page1[0].f1_57[0]": "50000.00",  # wages, 1z
        "Page2[0].f2_20[0]": "17750.00",  # standard deduction, 12e
        "Page2[0].f2_22[0]": "6000.00",   # senior deduction, 13b
        "Page2[0].f2_34[0]": "2911.50",   # total tax, 24
        "Page3[0].f3_01[0]": "4000.00",   # withholding, 25a
        "Page3[0].f3_14[0]": "1088.50",   # overpayment, 34
        "Page3[0].f3_19[0]": "0.00",      # amount owed, 37
        "Page1[0].Single_ReadOrder[0].c1_8[0]": "/1",
        "Page2[0].Line12d_ReadOrder[0].c2_17[0]": "/1",
        "Page2[0].Line12d_ReadOrder[0].c2_18[0]": "/Off",
    }
    verify_pdf(pdf, {PREFIX + key: value for key, value in expected.items()})
    assert "/XFA" not in reader.trailer["/Root"]["/AcroForm"]
    assert all("SILVERFILE DRAFT" in page.extract_text() for page in reader.pages)
    assert reader.attachments["audit-record.json"][0] == evidence
    audit_record = json.loads(evidence)
    assert audit_record["computation"]["lines"]["1z"]["value"] == "50000.00"
    assert fields[PREFIX + "Page1[0].f1_57[0]"].get("/TU")
    # No invented identity, bank account, or requested refund amount.
    for page, number in ((1, 14), (1, 16), (3, 15)):
        assert not fields[field_name(fields, page, number)].get("/V")
    assert notes and reviewed == before


@pytest.mark.parametrize("status", ["running", "stopped", "blocked", "paused_for_human_review"])
def test_unreviewed_case_cannot_export(reviewed, status):
    reviewed["status"] = status
    with pytest.raises(ValueError, match="reviewed draft"):
        build_pdf(reviewed, TEMPLATE)


def test_changed_intake_invalidates_export(reviewed):
    reviewed["intake_snapshot"]["facts"]["taxpayer_blind"] = True
    with pytest.raises(ValueError, match="stale"):
        build_pdf(reviewed, TEMPLATE)


def test_changed_amount_invalidates_export(reviewed):
    reviewed["computation_result"]["lines"]["1z"]["value"] = "999.00"
    with pytest.raises(ValueError, match="reviews"):
        validate_export_state(reviewed)


def test_adversarial_finding_prevents_export(reviewed):
    reviewed["adversarial_result"] = {"findings": [{"code": "unresolved_issue"}]}
    with pytest.raises(ValueError, match="reviews"):
        build_pdf(reviewed, TEMPLATE)


def test_unexpected_template_rejected(reviewed, tmp_path):
    wrong = tmp_path / "wrong.pdf"
    wrong.write_bytes(b"not the verified template")
    with pytest.raises(ValueError, match="template"):
        build_pdf(reviewed, wrong)


def test_dashboard_generates_download_and_blocks_stopped_case(tmp_path):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from streamlit.testing.v1 import AppTest
    import shutil
    database = tmp_path / "workflow_sessions.db"
    (tmp_path / "assets").mkdir()
    shutil.copyfile(TEMPLATE, tmp_path / "assets" / TEMPLATE.name)

    async def seed():
        async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
            graph = build_graph(providers(), checkpointer=saver)
            config = {"configurable": {"thread_id": "pdf-ui"}}
            await graph.ainvoke(new_case("pdf-ui"), config)
    asyncio.run(seed())
    script = ("from pathlib import Path\nimport runpy\n"
              "runpy.run_path(" + repr(str(ROOT / "dashboard.py")) + ")[\"main\"](Path(" + repr(str(database)) + "))")
    app = AppTest.from_string(script).run(timeout=30)
    next(b for b in app.button if b.label == "Generate draft 1040-SR").click().run(timeout=30)
    assert not app.exception and not app.error
    assert any("Draft generated" in message.value for message in app.success)
    assert len(app.get("download_button")) == 2

    async def stop():
        async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
            graph = build_graph(providers(), checkpointer=saver)
            await graph.aupdate_state({"configurable": {"thread_id": "pdf-ui"}}, {"status": "stopped"})
    asyncio.run(stop())
    app.run()
    assert not app.exception
    assert not any(b.label == "Generate draft 1040-SR" for b in app.button)
    assert len(app.get("download_button")) == 0
