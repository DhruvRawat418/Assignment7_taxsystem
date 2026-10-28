"""Integration skeleton: real orchestration, explicit missing business providers."""
import asyncio
from copy import deepcopy
import inspect
import re
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from src.agents.audit import input_fingerprint
from src.document_extraction.models import ExtractionResult
from src.integration.adapters import prepare_packet, validate_intake, validate_payload
from src.integration.contracts import IntegrationError, ProviderResult
from src.integration.runtime import default_runtime
from src.integration.state import (
    CaseState, active_extractions, context_fingerprint, digest, invalidate, progress_fingerprint,
    semantic_digest,
)

STAGES = {"intake", "rules", "compute", "audit", "adversarial", "human", "complete", "extract"}
OWNERS = {"intake", "rules", "compute", "adversarial"}


def _code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z_]{0,63}", value) else "provider_issue"


def _issue(code, owner="orchestrator"):
    return dict(code=_code(code), owner=owner)


def _blocked(code, owner="orchestrator"):
    return dict(status="blocked", next_stage="end", issues=[_issue(code, owner)], human_response={})


async def _call(function, state):
    snapshot = deepcopy(state)
    if inspect.iscoroutinefunction(function):
        return await asyncio.wait_for(function(snapshot), 60)
    output = await asyncio.wait_for(asyncio.to_thread(function, snapshot), 60)
    if inspect.isawaitable(output):
        return await asyncio.wait_for(output, 60)
    return output


def _packet(state):
    packet = prepare_packet(state["intake_snapshot"], state["rules_output"], active_extractions(state))
    packet["computation_result"] = deepcopy(state["computation_result"])
    return packet


def _audit_view(packet):
    return {key: packet[key] for key in ("computation_input", "computation_result", "extractions", "audit_source_bindings")}


def build_graph(providers=None, checkpointer=None, *, max_review_attempts=3, max_hops=40, no_progress_limit=2):
    """Caller owns deployment/authentication. Default checkpoints are RAM-only."""
    for limit in (max_review_attempts, max_hops, no_progress_limit):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Limits must be integers from 1 to 200")
    p = default_runtime(providers)

    async def provider(owner, state):
        function = getattr(p, owner)
        if function is None:
            return None, _blocked("provider_not_configured", owner)
        try:
            snapshot = dict(state)
            if state.get("human_response", {}).get("owner") != owner:
                snapshot["human_response"] = {}
            output = await _call(function, snapshot)
            if not isinstance(output, ProviderResult):
                return None, _blocked("invalid_provider_result", owner)
            validate_payload(output.data)
            if output.status == "ready":
                return output, None
            issues = [_issue(code, owner) for code in output.issue_codes[:128]] or [_issue("provider_requires_attention", owner)]
            if output.status == "needs_human_review":
                return None, dict(status="running", next_stage="human", pending_owner=owner, issues=issues, human_response={})
            if output.status == "needs_input":
                # Only Intake is allowed to engage the taxpayer. Other owners
                # hand missing-fact requests back to it, not a side dialogue.
                if owner != "intake":
                    return None, dict(status="running", next_stage="intake", issues=issues, human_response={})
                return None, dict(status="needs_input", next_stage="end", pending_owner="intake", issues=issues, human_response={})
            return None, _blocked("provider_not_configured" if output.status == "not_configured" else "provider_failed", owner)
        except asyncio.CancelledError:
            raise
        except Exception:
            return None, _blocked("provider_failed", owner)

    def supervisor(state):
        if state.get("status") != "running":
            return {}
        stage = state.get("next_stage")
        if stage not in STAGES:
            return _blocked("invalid_stage")
        if state.get("hops", 0) >= max_hops:
            return _blocked("hop_limit")
        if stage == "audit" and state.get("review_attempts", 0) >= max_review_attempts:
            return _blocked("review_limit")
        signature = progress_fingerprint(state)
        seen = dict(state.get("seen_progress", {}))
        seen[signature] = seen.get(signature, 0) + 1
        if seen[signature] > no_progress_limit:
            return _blocked("no_progress")
        return dict(hops=state.get("hops", 0) + 1, seen_progress=seen, mode=p.mode,
                    events=[*state.get("events", []), {"stage": stage}])

    async def intake(state):
        output, stop = await provider("intake", state)
        if stop:
            return stop
        try:
            data = validate_intake(output.data)
            registry = dict(state.get("document_registry", {}))
            for request in data["documents"]:
                old = registry.get(request["document_id"])
                if old is not None and old != request["path"]:
                    return _blocked("upload_id_reused", "intake")
                registry[request["document_id"]] = request["path"]
            if len(registry) > 256:
                return _blocked("document_history_limit", "intake")
            changed = digest(data) != digest(state.get("intake_snapshot", {}))
            return dict(intake_snapshot=data, documents=data["documents"], document_registry=registry,
                        revision=state.get("revision", 0) + int(changed), rules_output={},
                        human_response={},
                        human_resolution_fingerprint="" if changed else state.get("human_resolution_fingerprint", ""),
                        next_stage="extract", status="running", **invalidate())
        except IntegrationError as error:
            return _blocked(error.code, error.owner)

    async def extract_document(state):
        document_id = state["document"]["document_id"]
        try:
            output = await _call(p.extraction, state)
            validate_payload(output)
            results = output["extractions"]
            if set(output) != {"extractions"} or set(results) != {document_id} or results[document_id].get("document_id") != document_id:
                raise ValueError
            result = ExtractionResult.model_validate(results[document_id])
            return {"extractions": {document_id: result.model_dump(mode="json")}}
        except asyncio.CancelledError:
            raise
        except Exception:
            return {"extractions": {document_id: dict(document_id=document_id, status="needs_review", record=None,
                issues=[dict(code="extraction_failed", message="Extraction could not complete.")])}}

    def aggregate(state):
        results = active_extractions(state)
        if set(results) != {d["document_id"] for d in state["documents"]}:
            return _blocked("incomplete_extraction", "intake")
        if any(item.get("status") != "extracted" or item.get("issues") for item in results.values()):
            return dict(next_stage="intake", issues=[_issue("document_requires_attention", "intake")])
        return dict(next_stage="rules")

    async def rules(state):
        output, stop = await provider("rules", state)
        if stop:
            return stop
        try:
            packet = prepare_packet(state["intake_snapshot"], output.data, active_extractions(state))
            return {**invalidate(), "human_response": {}, "rules_output": deepcopy(output.data), "next_stage": "compute", "issues": [],
                    "computation_input": packet["computation_input"]}
        except IntegrationError as error:
            return _blocked(error.code, error.owner)

    async def compute(state):
        try:
            packet = prepare_packet(state["intake_snapshot"], state["rules_output"], active_extractions(state))
            snapshot = dict(state, **invalidate())
            snapshot["computation_input"] = packet["computation_input"]
            output = await _call(p.computation, snapshot)
            validate_payload(output)
            if set(output) != {"computation_result"} or not isinstance(output["computation_result"], dict):
                raise ValueError
            result = output["computation_result"]
            if result.get("status") != "completed":
                return dict(**invalidate(), **_blocked("computation_not_completed", "compute"))
            return {**invalidate(), "next_stage": "audit", "issues": [], "computation_input": packet["computation_input"],
                    "computation_result": result, "computed_for": context_fingerprint(state), "projection_notes": packet["projection_notes"]}
        except asyncio.CancelledError:
            raise
        except IntegrationError as error:
            return dict(**invalidate(), **_blocked(error.code, error.owner))
        except Exception:
            return dict(**invalidate(), **_blocked("computation_failed", "compute"))

    def findings_route(findings):
        mapping = {"computation": "compute", "compute": "compute", "document_extraction": "intake",
                   "intake": "intake", "eligibility_rules": "rules", "rules": "rules",
                   "adversarial": "adversarial", "human_review": "human"}
        if not isinstance(findings, list) or not findings or len(findings) > 128:
            return _blocked("invalid_review_result")
        owners, issues = [], []
        for finding in findings:
            if not isinstance(finding, dict) or finding.get("route_to") not in mapping:
                return _blocked("invalid_review_route")
            owners.append(mapping[finding["route_to"]])
            issues.append(_issue(finding.get("code"), owners[-1]))
        owner = "human" if "human" in owners else next((o for o in ("intake", "rules", "compute", "adversarial") if o in owners))
        return dict(next_stage=owner, issues=issues, pending_owner="rules" if owner == "human" else owner)

    async def audit(state):
        try:
            if state.get("computed_for") != context_fingerprint(state):
                return _blocked("stale_computation", "compute")
            packet = _audit_view(_packet(state))
            output = await _call(p.audit, packet)
            validate_payload(output)
            if set(output) != {"audit_result"} or not isinstance(output["audit_result"], dict):
                raise ValueError
            result = output["audit_result"]
            common = dict(audit_result=result, adversarial_result={}, review_attempts=state.get("review_attempts", 0) + 1)
            if result.get("status") == "passed":
                if result.get("issues") != [] or result.get("input_fingerprint") != input_fingerprint(packet):
                    return dict(common, **_blocked("stale_audit"))
                return dict(common, next_stage="adversarial", audit_for=context_fingerprint(state), issues=[])
            if result.get("status") in ("revision_required", "needs_human_review"):
                return dict(common, **findings_route(result.get("issues")))
            return dict(common, **_blocked("audit_verification_unavailable"))
        except asyncio.CancelledError:
            raise
        except Exception:
            return _blocked("audit_failed")

    async def adversarial(state):
        output, stop = await provider("adversarial", state)
        if stop:
            return stop
        findings = output.data.get("findings")
        if set(output.data) != {"findings"} or not isinstance(findings, list):
            return _blocked("invalid_review_result", "adversarial")
        if findings:
            return dict(adversarial_result=deepcopy(output.data), human_response={}, **findings_route(findings))
        return dict(adversarial_result={"findings": []}, human_response={}, next_stage="complete", issues=[])

    def complete(state):
        try:
            if p.intake is None or p.rules is None or p.adversarial is None:
                return _blocked("provider_not_configured")
            if (state.get("computed_for") != context_fingerprint(state)
                    or state.get("audit_for") != context_fingerprint(state)
                    or state.get("audit_result", {}).get("status") != "passed"
                    or state["audit_result"]["input_fingerprint"] != input_fingerprint(_audit_view(_packet(state)))
                    or state.get("adversarial_result") != {"findings": []}):
                return _blocked("stale_audit")
            return dict(status="ready_for_human_review", next_stage="end", issues=[])
        except Exception:
            return _blocked("final_validation_failed")

    def human(state):
        owner = state.get("pending_owner")
        if owner not in OWNERS or getattr(p, owner if owner != "compute" else "computation") is None:
            return _blocked("provider_not_configured")
        response = interrupt(dict(case_id=state["case_id"], revision=state["revision"], owner=owner,
                                  issue_codes=[i["code"] for i in state.get("issues", [])], actions=["resolve", "stop"]))
        if isinstance(response, dict) and response == {"action": "stop"}:
            return dict(status="stopped", next_stage="end", human_response={})
        try:
            if (not isinstance(response, dict) or set(response) != {"action", "owner", "revision", "response"}
                    or response["action"] != "resolve" or response["owner"] != owner
                    or type(response["revision"]) is not int or response["revision"] != state["revision"]
                    or not isinstance(response["response"], dict)):
                raise ValueError
            validate_payload(response["response"], limit=1_000_000)
            if response["response"] == {"reload_intake": True}:
                if owner != "rules":
                    raise ValueError

                return dict(
                    human_response={},
                    human_resolution_fingerprint=semantic_digest(response),
                    status="running",
                    next_stage="intake",
                )
            return dict(human_response=deepcopy(response), human_resolution_fingerprint=semantic_digest(response),
                        status="running", next_stage=owner)
        except (ValueError, TypeError, RecursionError):
            return _blocked("invalid_human_response")

    def dispatch(state):
        if state.get("status") != "running":
            return END
        if state["next_stage"] == "extract":
            pending = [d for d in state["documents"] if d["document_id"] not in state.get("extractions", {})]
            return [Send("extract_document", {"document": deepcopy(d)}) for d in pending] or "aggregate"
        return state["next_stage"]

    builder = StateGraph(CaseState)
    builder.add_node("supervisor", supervisor)
    for name, worker in (("intake", intake), ("rules", rules), ("compute", compute), ("audit", audit),
                         ("adversarial", adversarial), ("human", human), ("complete", complete), ("aggregate", aggregate)):
        builder.add_node(name, worker)
        builder.add_edge(name, "supervisor")
    builder.add_node("extract_document", extract_document)
    builder.add_edge("extract_document", "aggregate")
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", dispatch, [*STAGES - {"extract"}, "extract_document", "aggregate", END])
    graph = builder.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())
    return graph.with_config({"recursion_limit": max_hops * 3 + 20})
