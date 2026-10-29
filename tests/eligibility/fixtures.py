"""Hand-built synthetic case for Eligibility & Rules; no live taxpayer data.

Social Security numbers here are 900-series test values, which is the only
range the project accepts.
"""
from copy import deepcopy

SHA = "b" * 64


def source(document_id, box):
    return dict(document_id=document_id, sha256=SHA, page=1, box=box, bbox=[0, 0, 10, 10],
                image_size=[100, 100], raw_text="synthetic", confidence=1.0,
                agent="document_extraction", engine="test-only",
                timestamp="2026-10-24T00:00:00Z")


def money(document_id, box, value):
    return dict(value=value, origin="document", source=source(document_id, box))


def extraction(document_id="w2-1", boxes=None):
    boxes = {"1": "50000.00", "2": "4000.00"} if boxes is None else boxes
    return dict(document_id=document_id, sha256=SHA, status="extracted", issues=[],
                record=dict(document_type="W-2",
                            tax_year=dict(value="2025", source=source(document_id, "tax_year")),
                            amounts={box: money(document_id, box, value)
                                     for box, value in boxes.items()}))


# Computation requires every input line to be present; absence and a
# confirmed zero are different. Intake owns these, so the fixture supplies
# them as sourced zeros. With a W-2 attached, 1z and 25a come from the
# document instead and Intake must not also claim them.
INPUT_LINES = ("1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a",
               "8", "10", "17", "19", "20", "23", "25a", "25b", "25c", "26", "32",
               "ss_adjustments")


def intake_amounts(from_documents=True):
    owned = set(INPUT_LINES) - ({"1z", "25a"} if from_documents else set())
    return {line: [dict(value="0.00", sources=[dict(
        kind="user_input", reference="synthetic-intake", field="confirmed " + line,
        entered_by="demo-user", recorded_at="2026-10-24T00:00:00Z")])] for line in sorted(owned)}


def facts(**overrides):
    base = dict(filing_status="single", taxpayer_date_of_birth="1952-04-09",
                taxpayer_blind=False)
    base.update(overrides)
    return base


def clean_state(**fact_overrides):
    """A single filer aged 65 or older with one clean W-2."""
    return dict(
        case_id="case-1", mode="live", status="running", next_stage="rules",
        intake_snapshot=dict(facts=facts(**fact_overrides), amounts=intake_amounts(),
                             documents=[dict(document_id="w2-1", path="/tmp/w2-1.jpg")]),
        documents=[dict(document_id="w2-1", path="/tmp/w2-1.jpg")],
        extractions={"w2-1": extraction()},
        rules_output={}, issues=[], events=[],
    )


def state_without_documents(**fact_overrides):
    state = clean_state(**fact_overrides)
    state["intake_snapshot"]["documents"] = []
    state["intake_snapshot"]["amounts"] = intake_amounts(from_documents=False)
    state["documents"] = []
    state["extractions"] = {}
    return state


def joint_state(**fact_overrides):
    overrides = dict(filing_status="mfj", spouse_date_of_birth="1955-01-03", spouse_blind=False)
    overrides.update(fact_overrides)
    return clean_state(**overrides)


def with_boxes(boxes):
    state = clean_state()
    state["extractions"]["w2-1"] = extraction(boxes=boxes)
    return deepcopy(state)
