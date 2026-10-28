"""Turns one free-text reply into a structured ParsedTurn.

Two interchangeable parsers:
- LLMParser: the real one (LangChain structured output). Sees only the REDACTED reply,
  the current question and a short summary - never the whole transcript (context strategy).
- RuleParser: offline fallback for tests and for running without an API key.
"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, Field


class FieldCorrection(BaseModel):
    field: str = Field(description="Name of an EARLIER field the person is correcting, e.g. 'taxpayer_birth_date'.")
    value: str = Field(description="The corrected value exactly as the person stated it.")


class ParsedTurn(BaseModel):
    intent: Literal["answer", "unsure", "advice_request", "go_back", "off_topic"] = Field(
        description="answer = replies to the current question; unsure = says they don't know; "
        "advice_request = asks what they SHOULD do to pay less / optimise / deduct; "
        "go_back = wants to return to the previous question; off_topic = anything else."
    )
    value: Optional[str] = Field(
        None, description="The answer to the CURRENT question in the person's words, lightly cleaned. "
        "Never add up, convert or compute anything."
    )
    corrections: list[FieldCorrection] = Field(default_factory=list)
    advice_question: Optional[str] = Field(None, description="The advice question, rephrased neutrally, if any.")
    third_party_answering: bool = Field(False, description="Someone other than the taxpayer seems to be answering.")
    stated_authority: Optional[str] = Field(None, description="e.g. 'power of attorney' if the third party states one.")
    refund_account_concern: bool = Field(False, description="Refund going to an account the taxpayer can't describe or that isn't theirs.")
    spouse_death_mentioned: bool = Field(False, description="The person mentions their spouse died.")


class Parser(Protocol):
    def __call__(self, *, field: str, question: str, reply: str, known: str) -> ParsedTurn: ...


SYSTEM_PROMPT = """You read ONE reply from an older adult who is answering questions for a tax-form draft.
Your only job is to classify the reply and copy out the answer. Rules:
- Do not give advice. Do not do arithmetic. Do not interpret tax rules.
- If they give several amounts, copy them as said; never add them up.
- "[TEST-SSN]" and "[SSN-REDACTED]" are placeholders; leave them as they are.
- Questions like "should I...", "would I pay less if...", "can I deduct..." are advice_request.
- If they correct an earlier answer ("actually I was born in 1957"), put it in corrections.
- Flag third_party_answering, refund_account_concern and spouse_death_mentioned only on clear signals."""


class LLMParser:
    def __init__(self, model: str | None = None):
        from langchain.chat_models import init_chat_model  # imported lazily: tests don't need it

        model = model or os.environ["SILVERFILE_MODEL"]  # e.g. "openai:gpt-4o-mini"
        self.llm = init_chat_model(model, temperature=0).with_structured_output(ParsedTurn)

    def __call__(self, *, field: str, question: str, reply: str, known: str) -> ParsedTurn:
        user_msg = (
            f"Current field: {field}\nQuestion asked: {question}\n"
            f"Already covered (summary): {known or 'nothing yet'}\n\nReply: {reply}"
        )
        return self.llm.invoke([("system", SYSTEM_PROMPT), ("human", user_msg)])


class RuleParser:
    """Keyword-only parser. Good enough for tests and offline demos; flags are handled by
    intake_guards.detect_flags in both modes."""

    def __call__(self, *, field: str, question: str, reply: str, known: str) -> ParsedTurn:
        t = reply.strip().lower()
        if re.search(r"\b(go back|previous question|back up|change my last)\b", t):
            return ParsedTurn(intent="go_back")
        if re.search(r"\b(not sure|don'?t know|no idea|unsure|can'?t remember)\b", t):
            return ParsedTurn(intent="unsure")
        return ParsedTurn(intent="answer", value=reply.strip())
