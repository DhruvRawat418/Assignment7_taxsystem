"""Document facts describe printed boxes, never 1040-SR line assignments."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(StrictModel):
    document_id: str
    sha256: str
    page: int = 1
    box: str
    # Coordinates refer to the EXIF-corrected image, origin at top-left.
    bbox: tuple[float, float, float, float]
    image_size: tuple[int, int]
    raw_text: str
    confidence: float = Field(ge=0, le=1)
    agent: Literal["document_extraction"] = "document_extraction"
    engine: str
    timestamp: datetime


class MoneyFact(StrictModel):
    value: Decimal = Field(ge=0, allow_inf_nan=False, decimal_places=2)
    origin: Literal["document"] = "document"
    source: Source


class TextFact(StrictModel):
    value: str
    source: Source


class Issue(StrictModel):
    code: str
    field: str | None = None
    message: str  # Never include a rejected SSN or the entire OCR transcript.


class W2Record(StrictModel):
    document_type: Literal["W-2"] = "W-2"
    tax_year: TextFact | None = None
    employee_ssn: TextFact | None = None
    employer_ein: TextFact | None = None
    amounts: dict[str, MoneyFact] = Field(default_factory=dict)


class ExtractionResult(StrictModel):
    document_id: str
    sha256: str | None = None
    status: Literal["extracted", "needs_review", "rejected"]
    record: W2Record | None = None
    issues: tuple[Issue, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "extracted" and self.record is not None
