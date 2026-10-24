"""Tool-only Computation Agent. No arithmetic, LLM, tax advice, or global graph.

    async def computation_node(state) -> {"computation_result": result}

The node owns only this result key. The team's Orchestrator owns routing and HITL.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

from src.agents.computation_contract import (
    ComputationRequest, ComputationResult, ComputedLine, Issue, Source, ToolCall, parse_money,
)


class ToolClient(Protocol):
    """Adapter seam for the team's eventual supplied tax_math MCP service."""

    async def call(self, name: str, arguments: dict) -> dict: ...


class MCPToolClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def call(self, name: str, arguments: dict) -> dict:
        result = await self.session.call_tool(name, arguments=arguments)
        if result.isError:
            # Don't echo tool error text: it can contain submitted data.
            raise RuntimeError(f"MCP tool {name} returned an error")
        payload = result.structuredContent
        if payload is None:
            text_parts = [part.text for part in result.content if part.type == "text"]
            payload = json.loads("".join(text_parts))
        if not isinstance(payload, dict):
            raise RuntimeError("MCP tool did not return an object")
        parse_money(payload.get("value"))
        refs = payload.get("rule_references")
        if not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r for r in refs):
            raise RuntimeError("MCP tool omitted its rule references")
        return payload


@asynccontextmanager
async def computation_tools():
    root = str(Path(__file__).resolve().parents[2])
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.tools.computation_mcp_server"],
        env={"PYTHONPATH": root, "PYTHONUNBUFFERED": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield MCPToolClient(session)


def _unique_sources(sources: list[Source]) -> list[Source]:
    return list({source.model_dump_json(): source for source in sources}.values())


def _preflight(request: ComputationRequest) -> list[Issue]:
    issues = []
    if not request.rules.approved or request.rules.blocking_conditions:
        issues.append(Issue(code="rules_not_cleared", message="Eligibility & Rules must clear this case first"))
    p = request.profile
    if not p.taxpayer_65_or_older and not (p.filing_status == "mfj" and p.spouse_65_or_older):
        issues.append(Issue(code="not_1040_sr_eligible", message="Rules must resolve 1040-SR age eligibility"))
    if p.filing_status == "mfs" and (p.spouse_65_or_older or p.spouse_blind):
        if not p.mfs_spouse_allowance_approved:
            issues.append(Issue(code="mfs_spouse_boxes", message="Rules must approve MFS spouse deduction boxes"))
    for line, entries in request.amounts.items():
        seen = set()
        for entry in entries:
            identities = {(s.kind, s.reference, s.field) for s in entry.sources}
            if seen.intersection(identities):
                issues.append(Issue(code="duplicate_input_source",
                    message=f"Line {line} repeats a source field; resolve duplicates upstream"))
                break
            seen.update(identities)
    return issues


async def compute(request_data: dict | ComputationRequest, client: ToolClient) -> ComputationResult:
    """Run only Computation, using an initialized MCP client supplied by the caller."""
    try:
        request = ComputationRequest.model_validate(request_data)
    except ValidationError as error:
        # Exclude inputs and contexts so raw source material is not copied into logs.
        locations = [".".join(map(str, item["loc"])) or "request" for item in error.errors()]
        return ComputationResult(status="invalid_input", issues=[
            Issue(code="invalid_contract", message="Invalid or incomplete fields: " + ", ".join(locations))])
    issues = _preflight(request)
    if issues:
        return ComputationResult(status="needs_human_review", issues=issues)

    lines: dict[str, ComputedLine] = {}
    calls: list[ToolCall] = []
    profile = request.profile.model_dump(mode="json")

    async def calculate(line: str, tool: str, arguments: dict,
                        depends_on: tuple[str, ...] = (), sources: list[Source] | None = None):
        output = await client.call(tool, arguments)
        amount = parse_money(output.get("value"))
        references = output.get("rule_references")
        if not isinstance(references, list) or not references or not all(isinstance(r, str) and r for r in references):
            raise RuntimeError("Tool omitted rule references")
        call = ToolCall(call_id=str(uuid4()), output_key=line, tool=tool, arguments=arguments, result=output)
        calls.append(call)
        inherited = [s for dependency in depends_on for s in lines[dependency].sources]
        inherited.extend(sources or [])
        lines[line] = ComputedLine(value=amount, tool_call_id=call.call_id,
                                  depends_on=list(depends_on), sources=_unique_sources(inherited),
                                  rule_references=list(dict.fromkeys([*request.rules.citations, *references])))

    def value(line: str) -> str:
        return str(lines[line].value)

    async def total(line: str, dependencies: tuple[str, ...]):
        await calculate(line, "sum_amounts", {"values": [value(d) for d in dependencies]}, dependencies)

    async def subtract(line: str, left: str, right: str, floor_zero: bool = False):
        await calculate(line, "difference", {"left": value(left), "right": value(right),
                                             "floor_zero": floor_zero}, (left, right))

    try:
        for line, entries in request.amounts.items():
            await calculate(line, "sum_amounts", {"values": [str(e.value) for e in entries]},
                            sources=[s for entry in entries for s in entry.sources])

        # Comparisons validate upstream consistency; arithmetic remains in MCP tools.
        for part, whole in (("3a", "3b"), ("4b", "4a"), ("5b", "5a")):
            if lines[part].value > lines[whole].value:
                return ComputationResult(status="needs_human_review", tool_calls=calls, issues=[
                    Issue(code="inconsistent_inputs", message=f"Line {part} exceeds line {whole}; resolve upstream")])
        if lines["ss_adjustments"].value > lines["10"].value:
            return ComputationResult(status="needs_human_review", tool_calls=calls, issues=[
                Issue(code="inconsistent_adjustments", message="SS worksheet adjustments exceed total adjustments")])

        await total("income_before_ss", ("1z", "2b", "3b", "4b", "5b", "8"))
        await calculate("6b", "social_security_taxable", {
            "benefits": value("6a"), "other_income": value("income_before_ss"),
            "tax_exempt_interest": value("2a"), "adjustments": value("ss_adjustments"),
            "profile": profile}, ("6a", "income_before_ss", "2a", "ss_adjustments"))
        await total("9", ("income_before_ss", "6b"))
        await subtract("11a", "9", "10")
        await total("11b", ("11a",))
        await calculate("12e", "standard_deduction", {"profile": profile})
        await calculate("13b", "senior_deduction", {"agi": value("11b"), "profile": profile}, ("11b",))
        await total("14", ("12e", "13b"))
        await subtract("15", "11b", "14", True)
        await calculate("16", "income_tax", {"taxable_income": value("15"),
                         "qualified_dividends": value("3a"),
                         "filing_status": request.profile.filing_status}, ("15", "3a"))
        await total("18", ("16", "17"))
        await total("21", ("19", "20"))
        await subtract("22", "18", "21", True)
        await total("24", ("22", "23"))
        await total("25d", ("25a", "25b", "25c"))
        await total("33", ("25d", "26", "32"))
        await subtract("34", "33", "24", True)
        await subtract("37", "24", "33", True)
    except asyncio.CancelledError:
        raise
    except Exception:
        # Never emit partially assembled return lines after a failed tool call.
        return ComputationResult(status="tool_error", tool_calls=calls, issues=[
            Issue(code="calculation_failed", message="A computation tool failed; do not render a return")])

    form_lines = {line: result for line, result in lines.items()
                  if line not in ("ss_adjustments", "income_before_ss")}
    intermediates = {line: result for line, result in lines.items() if line not in form_lines}
    return ComputationResult(status="completed", lines=form_lines,
                             intermediates=intermediates, tool_calls=calls)


async def computation_node(state: dict) -> dict:
    """LangGraph-compatible async node; returns only the Computation namespace.

    An Orchestrator must route non-completed statuses to correction/HITL. This
    node intentionally does not implement the team's graph or human approval.
    """
    request_data = state.get("computation_input")
    if request_data is None:
        result = ComputationResult(status="invalid_input", issues=[
            Issue(code="missing_input", message="computation_input is required")])
    else:
        try:
            async with computation_tools() as client:
                result = await compute(request_data, client)
        except asyncio.CancelledError:
            raise
        except Exception:
            result = ComputationResult(status="tool_error", issues=[
                Issue(code="mcp_unavailable", message="Could not start or communicate with the computation MCP server")])
    return {"computation_result": result.model_dump(mode="json")}
