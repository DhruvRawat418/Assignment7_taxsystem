"""Fresh-process test driver. All Intake/Extraction/adversarial data is synthetic.

Rules, mapping, Computation, Audit, MCP and LangGraph come from explicit source
checkouts. The three-key projection is test-only and preserves dashboard
metadata separately. It never creates a clearance or changes an amount.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from src.agents.audit import audit
from src.agents.computation import compute, computation_node, computation_tools
from src.agents.eligibility import eligibility
from src.agents.eligibility_contract import SCOPE_FLAGS
from src.document_extraction.models import ExtractionResult
from src.integration.adapters import prepare_packet
from src.integration.contracts import IntegrationError, ProviderResult, Providers
from src.integration.graph import build_graph
from src.integration.state import new_case

PACKET_KEYS = {"profile", "clearance", "box_dispositions"}
CHECKBOXES = ("taxpayer_65_or_older", "taxpayer_blind", "spouse_65_or_older", "spouse_blind")


def fixture(scenario):
    original = json.loads(Path("computation_clean.json").read_text())
    amounts = deepcopy(original["amounts"])
    del amounts["1z"], amounts["25a"]
    facts = {flag: False for flag in SCOPE_FLAGS}
    facts.update(filing_status="single", taxpayer_date_of_birth="1952-04-09", taxpayer_blind=False)
    if scenario in ("joint_one_senior", "joint_both_senior", "missing_spouse"):
        facts.update(filing_status="mfj", spouse_date_of_birth="1955-01-03", spouse_blind=False)
        if scenario == "joint_one_senior":
            facts["taxpayer_date_of_birth"] = "1970-03-15"
        if scenario == "missing_spouse":
            del facts["spouse_blind"]
    if scenario == "rules_blocked":
        facts["has_rental_income"] = True
    if scenario == "missing_amount":
        del amounts["2a"]

    documents, extractions = [], {}
    count = 2 if scenario == "multiple_w2" else 1
    for index in range(count):
        document_id = f"synthetic-w2-{index + 1}"
        sha = hashlib.sha256(document_id.encode()).hexdigest()  # Invented evidence, not an image hash.

        def source(box):
            return dict(document_id=document_id, sha256=sha, page=1, box=box,
                        bbox=[0, 0, 10, 10], image_size=[100, 100], raw_text="synthetic fixture",
                        confidence=1.0, agent="document_extraction", engine="test-only-no-OCR",
                        timestamp="2026-10-26T00:00:00Z")

        boxes = {"1": "25000.00", "2": "2000.00"} if count == 2 else {"1": "50000.00", "2": "4000.00"}
        if scenario == "extra_boxes":
            boxes.update({"3": "50000.00", "4": "3100.00"})
        record = dict(document_type="W-2", tax_year=dict(value="2025", source=source("tax_year")),
                      amounts={box: dict(value=value, origin="document", source=source(box))
                               for box, value in boxes.items()})
        item = dict(document_id=document_id, sha256=sha, status="extracted", issues=[], record=record)
        extractions[document_id] = ExtractionResult.model_validate(item).model_dump(mode="json")
        documents.append(dict(document_id=document_id, path=f"synthetic/{document_id}.jpg"))
    intake = dict(facts=facts, amounts=amounts, documents=documents)
    return dict(intake_snapshot=intake, documents=documents, extractions=extractions)


def project_rules(result):
    """A labelled test proposal, not a production compatibility fallback."""
    data = deepcopy(result.data)
    if not PACKET_KEYS.issubset(data) or set(data) - PACKET_KEYS - {"line_12d_boxes"}:
        raise ValueError("Unknown Rules packet shape")
    metadata = {}
    if "line_12d_boxes" in data:
        boxes = data.pop("line_12d_boxes")
        expected = [key for key in CHECKBOXES if data["profile"][key]]
        if not isinstance(boxes, list) or sorted(boxes) != sorted(expected):
            raise ValueError("Rules checkbox metadata disagrees with the profile")
        metadata["line_12d_boxes"] = boxes
    return data, metadata


async def graph_probe(state):
    calls = []

    def intake(_):
        return ProviderResult(status="ready", data=deepcopy(state["intake_snapshot"]))

    def extraction(payload):
        key = payload["document"]["document_id"]
        return {"extractions": {key: deepcopy(state["extractions"][key])}}

    def rules(payload):
        decision = eligibility(payload)
        if decision.status != "ready":
            return decision
        data, _metadata = project_rules(decision)
        return ProviderResult(status="ready", data=data)

    async def computation(payload):
        calls.append(True)
        return await computation_node(payload)

    providers = Providers(intake=intake, rules=rules, extraction=extraction,
                          computation=computation, mode="synthetic",
                          adversarial=lambda _: ProviderResult(status="ready", data={"findings": []}))
    graph = build_graph(providers)
    output = await graph.ainvoke(new_case("team-probe"), {"configurable": {"thread_id": "team-probe"}})
    return dict(status=output["status"], audit_status=output.get("audit_result", {}).get("status"),
                computation_calls=len(calls), projection="test_only_three_key_rules_packet")


async def run(scenario):
    state = fixture(scenario)
    if scenario == "graph":
        return await graph_probe(state)
    before = deepcopy(state)
    decision = eligibility(state)
    result = dict(rules_status=decision.status, rules_issue_codes=list(decision.issue_codes), computation_calls=0)
    if decision.status != "ready":
        return result
    if scenario == "raw_contract":
        result["unexpected_keys"] = sorted(set(decision.data) - PACKET_KEYS)
        result["missing_keys"] = sorted(PACKET_KEYS - set(decision.data))
        try:
            prepare_packet(state["intake_snapshot"], decision.data, state["extractions"])
            result["mapping_error"] = None
        except IntegrationError as error:
            result["mapping_error"] = error.code
        # Only classify the known extra metadata as an expected failure when
        # the remaining unmodified data really passes the published adapter.
        try:
            packet, _metadata = project_rules(decision)
            prepare_packet(state["intake_snapshot"], packet, state["extractions"])
            result["projected_mapping_error"] = None
        except (IntegrationError, ValueError) as error:
            result["projected_mapping_error"] = getattr(error, "code", "invalid_metadata")
        return result

    rules, metadata = project_rules(decision)
    result["test_only_rules_metadata"] = metadata
    try:
        packet = prepare_packet(state["intake_snapshot"], rules, state["extractions"])
    except IntegrationError as error:
        result["mapping_error"] = error.code
        return result
    async with computation_tools() as client:
        computed = await compute(packet["computation_input"], client)
        result.update(computation_calls=1, computation_status=computed.status)
        if computed.status != "completed":
            return result
        packet["computation_result"] = computed.model_dump(mode="json")
        if scenario == "tampered":
            packet["computation_result"]["lines"]["1z"]["value"] = "99999.00"
            for call in packet["computation_result"]["tool_calls"]:
                if call["output_key"] == "1z":
                    call["arguments"]["values"] = ["99999.00"]
                    call["result"]["value"] = "99999.00"
        checked = await audit(packet, client)
    result.update(audit_status=checked["status"], verified_lines=len(checked["verified_lines"]),
                  audit_issue_codes=[item["code"] for item in checked["issues"]],
                  lines={line: str(value.value) for line, value in computed.lines.items()},
                  wage_sources=len(computed.lines["1z"].sources),
                  projection_notes=packet["projection_notes"], input_unchanged=state == before)
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(sys.argv[1]))))
