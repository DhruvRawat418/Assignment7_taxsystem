"""LangGraph-compatible worker and a conflict-detecting parallel reducer.

The supervisor supplies one `document` per Send task and owns all routing/HITL.
This worker never talks to the taxpayer or writes return lines.
"""
from __future__ import annotations

import json
from threading import local
from typing import Annotated, Callable, TypedDict

from src.document_extraction import extract_w2
from src.document_extraction.models import ExtractionResult, Issue
from src.document_extraction.ocr import OCREngine, RapidOCREngine


class DocumentRequest(TypedDict):
    document_id: str  # Unique per upload, including corrected uploads.
    path: str


def _without_timestamps(value):
    if isinstance(value, dict):
        return {k: _without_timestamps(v) for k, v in value.items() if k != "timestamp"}
    if isinstance(value, list):
        return [_without_timestamps(v) for v in value]
    return value


def merge_extractions(left: dict, right: dict) -> dict:
    """Order-independent, idempotent merge; a collision is never overwritten.

    Retried identical facts retain the earliest extraction timestamp. Corrected
    uploads must use a new document_id and retain their predecessor for audit.
    """
    merged = dict(left)
    for document_id, result in right.items():
        if document_id in merged:
            if _without_timestamps(merged[document_id]) != _without_timestamps(result):
                raise ValueError(f"Conflicting extraction for document_id {document_id!r}; use a new upload ID.")
            merged[document_id] = min(merged[document_id], result,
                key=lambda r: json.dumps(r, sort_keys=True))
        else:
            merged[document_id] = result
    return dict(sorted(merged.items()))


class ExtractionState(TypedDict, total=False):
    documents: list[DocumentRequest]
    document: DocumentRequest  # Worker-local Send payload; not a shared write.
    extractions: Annotated[dict[str, dict], merge_extractions]


def make_extraction_node(engine_factory: Callable[[], OCREngine] = RapidOCREngine):
    engines = local()

    def document_extraction_node(state: ExtractionState) -> dict:
        request = state["document"]
        if not hasattr(engines, "reader"):
            try:
                engines.reader = engine_factory()
            except Exception:
                result = ExtractionResult(document_id=request["document_id"], status="needs_review",
                    issues=(Issue(code="ocr_failed", message="The local OCR engine could not start. Request technical or human review."),))
                return {"extractions": {request["document_id"]: result.model_dump(mode="json")}}
        result = extract_w2(request["path"], request["document_id"], engine=engines.reader)
        return {"extractions": {request["document_id"]: result.model_dump(mode="json")}}

    return document_extraction_node
