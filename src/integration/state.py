"""Proposed case state and semantic progress checks; no taxpayer dialogue."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re
from typing import Annotated, TypedDict
from src.agents.document_extraction import merge_extractions
from src.integration.contracts import IntegrationError


class CaseState(TypedDict, total=False):
    task_plan: dict
    case_id: str
    mode: str
    status: str
    next_stage: str
    revision: int
    intake_snapshot: dict
    documents: list
    document_registry: dict
    extractions: Annotated[dict, merge_extractions]
    rules_output: dict
    computation_input: dict
    computation_result: dict
    computed_for: str
    audit_result: dict
    audit_for: str
    adversarial_result: dict
    projection_notes: list
    pending_owner: str
    human_response: dict
    human_resolution_fingerprint: str
    issues: list
    hops: int
    review_attempts: int
    seen_progress: dict
    events: list


def digest(value):
    def encode(value):
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError("Non-JSON state")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, default=encode).encode()).hexdigest()


def active_extractions(state):
    ids = {d["document_id"] for d in state.get("documents", [])}
    return {key: deepcopy(value) for key, value in state.get("extractions", {}).items() if key in ids}


def context_fingerprint(state):
    return digest({"intake": state.get("intake_snapshot"), "rules": state.get("rules_output"),
                   "extractions": active_extractions(state)})


def semantic_digest(value):
    volatile = {"timestamp", "recorded_at", "checked_at", "call_id", "tool_call_id", "input_fingerprint"}
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in volatile}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return digest(strip(value))


def progress_fingerprint(state):
    return semantic_digest({key: state.get(key) for key in (
        "next_stage", "pending_owner", "intake_snapshot", "rules_output", "computation_result",
        "audit_result", "adversarial_result", "issues", "human_resolution_fingerprint")} |
        {"active": active_extractions(state)})


def invalidate():
    return dict(computation_input={}, computation_result={}, computed_for="", audit_result={},
                audit_for="", adversarial_result={}, projection_notes=[])


def new_case(case_id):
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case_id):
        raise IntegrationError("invalid_case_id", "orchestrator")
    return dict(case_id=case_id, mode="live", status="running", next_stage="intake", revision=0,
                intake_snapshot={}, documents=[], document_registry={}, extractions={}, rules_output={},
                pending_owner="", human_response={}, human_resolution_fingerprint="", issues=[], hops=0, review_attempts=0,
                seen_progress={}, events=[], **invalidate())
