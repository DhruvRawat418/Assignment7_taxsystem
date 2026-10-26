"""Synthetic providers/records only; never claim these are implemented agents."""
from copy import deepcopy
from tests.audit.fixtures import clean_state
from tests.test_extraction import clean_tokens, parse
from src.document_extraction.ocr import Token


def extracted(document_id="w2-1", sha="a" * 64):
    tokens = [Token({"38,750.25": "50,000.00", "3,125.50": "4,000.00"}.get(t.text, t.text), t.confidence, t.bbox)
              for t in clean_tokens()]
    record = parse(tokens).model_dump(mode="json")
    record["document_id"], record["sha256"] = document_id, sha
    for field in record["record"].values():
        if isinstance(field, dict) and "source" in field:
            field["source"].update(document_id=document_id, sha256=sha)
    for field in record["record"]["amounts"].values():
        field["source"].update(document_id=document_id, sha256=sha)
    return record


def intake_data(documents=True):
    request = clean_state()["computation_input"]
    amounts = deepcopy(request["amounts"])
    if documents:
        del amounts["1z"], amounts["25a"]
    return dict(facts={"filing_status": "single"}, amounts=amounts,
                documents=[dict(document_id="w2-1", path="demo/w2_clean.jpg")] if documents else [])


def rules_data(document_ids=("w2-1",)):
    request = clean_state()["computation_input"]
    return dict(profile=deepcopy(request["profile"]), clearance=deepcopy(request["rules"]),
                box_dispositions={key: {"1": {"action": "use", "line": "1z"},
                                        "2": {"action": "use", "line": "25a"}} for key in document_ids})
