"""Structured findings from the adversarial reviewer."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        pattern=r"^[a-z][a-z_]{0,63}$",
        description="Short problem identifier, such as conflicting_income.",
    )

    route_to: Literal[
        "intake",
        "document_extraction",
        "rules",
        "computation",
        "human_review",
    ]

    explanation: str = Field(
        min_length=1,
        max_length=1000,
        description="What is wrong and why it needs attention.",
    )

    evidence: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Specific fields or source references supporting the finding.",
    )


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ReviewFinding] = Field(
        max_length=20,
        description="Supported problems found during review; empty if none found.",
    )