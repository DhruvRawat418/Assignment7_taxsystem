"""Standalone deterministic Review/Audit node, not a final tax approval agent.

Use make_audit_node(trusted_tool_client) at integration. The default audit_node
fails closed because it has no configured MCP connection. No global graph,
LLM, tax arithmetic, filesystem access, network request or state mutation here.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Protocol

from src.agents.audit_checks import check_state
from src.agents.audit_contract import SPECS, issue, money, references
from src.agents.audit_recipe import arguments_equal, expected_arguments

PACKET_KEYS = ("computation_input", "computation_result", "extractions", "audit_source_bindings")


class ToolClient(Protocol):
    async def call(self, name: str, arguments: dict) -> dict: ...


def _decimal_json(value):
    if isinstance(value, Decimal):
        return str(money(value))
    raise TypeError("Non-JSON value")


def input_fingerprint(state):
    """Identify this exact audit packet, not a signature of authenticity.

    Compare against the current packet before using an old pass. An upstream
    version/invalidation policy is still required for asynchronous integration.
    """
    if not isinstance(state, dict):
        raise ValueError("Invalid packet")
    packet = {key: state.get(key) for key in PACKET_KEYS}
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, default=_decimal_json).encode()
    if len(encoded) > 2_000_000:
        raise ValueError("Audit packet exceeds two MB")
    return hashlib.sha256(encoded).hexdigest()


def _result(problems, fingerprint, verified=(), rechecks=()):
    if any(p["route_to"] == "human_review" for p in problems):
        status = "needs_human_review"
    elif any(p["unavailable"] for p in problems):
        status = "verification_unavailable"
    elif problems:
        status = "revision_required"
    else:
        status = "passed"
    return dict(status=status, review_scope="deterministic_component", draft_only=True,
                input_fingerprint=fingerprint, checked_at=datetime.now(timezone.utc).isoformat(),
                issues=list(problems)[:128], issues_truncated=len(problems) > 128,
                verified_lines=list(verified), rechecks=list(rechecks))


async def _recheck(packet, client, tool_timeout):
    request, result = packet["computation_input"], packet["computation_result"]
    lines = {**result["lines"], **result["intermediates"]}
    calls = {call["call_id"]: call for call in result["tool_calls"]}
    values, verified, problems, rechecks = {}, [], [], []
    for key, tool, dependencies in SPECS:
        arguments = expected_arguments(request, key, tool, dependencies, values)
        recorded = calls[lines[key]["tool_call_id"]]
        same_arguments = arguments_equal(recorded["arguments"], arguments)
        if not same_arguments:
            problems.append(issue("tool_arguments_mismatch", key))
        # Only locally specified tool names and independently reconstructed
        # arguments are executable. Give the client a copy to avoid mutation.
        response = await asyncio.wait_for(client.call(tool, deepcopy(arguments)), timeout=tool_timeout)
        if not isinstance(response, dict):
            raise ValueError("Tool returned a non-object")
        value = money(response.get("value"))
        references(response.get("rule_references"))
        values[key] = str(value)
        same_value = value == money(lines[key]["value"])
        if not same_value:
            problems.append(issue("recomputed_value_mismatch", key))
        same_refs = set(response["rule_references"]).issubset(lines[key]["rule_references"])
        if not same_refs:
            problems.append(issue("rule_reference_mismatch", key))
        rechecks.append(dict(line=key, tool=tool, arguments=arguments, value=str(value),
                             rule_references=response["rule_references"]))
        if same_arguments and same_value and same_refs:
            verified.append(key)
    return problems, verified, rechecks


async def audit(state: dict, client: ToolClient | None = None, *, tool_timeout=5.0, total_timeout=60.0) -> dict:
    """Check a snapshot, fail closed on missing evidence/tools, preserve cancellation."""
    try:
        fingerprint = input_fingerprint(state)
        packet = deepcopy({key: state.get(key) for key in PACKET_KEYS})
    except (ValueError, TypeError, RecursionError, OverflowError):
        return _result([issue("invalid_contract", route_to="orchestrator")], None)
    problems = check_state(packet)
    if problems:
        return _result(problems, fingerprint)
    if client is None:
        return _result([issue("mcp_unavailable", route_to="orchestrator", unavailable=True)], fingerprint)
    try:
        if (type(tool_timeout) not in (int, float) or type(total_timeout) not in (int, float)
                or not 0 < tool_timeout <= 60 or not 0 < total_timeout <= 300):
            raise ValueError("Invalid timeout configuration")
        problems, verified, rechecks = await asyncio.wait_for(
            _recheck(packet, client, tool_timeout), timeout=total_timeout)
    except asyncio.CancelledError:
        raise
    except Exception:
        # Never leak MCP exceptions; partial verification is not a pass.
        return _result([issue("mcp_verification_failed", route_to="orchestrator", unavailable=True)], fingerprint)
    return _result(problems, fingerprint, verified, rechecks)


def make_audit_node(client: ToolClient | None = None):
    """Bind a trusted initialized client; its lifecycle belongs to the caller."""
    async def node(state: dict) -> dict:
        return {"audit_result": await audit(state, client)}
    return node


audit_node = make_audit_node()
