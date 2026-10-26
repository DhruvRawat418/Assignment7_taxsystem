"""Pure W-2 mapping and Audit projection, with explicit Rules dispositions."""
from copy import deepcopy
from decimal import Decimal, DecimalException
import json
import re
from pydantic import ValidationError

from src.agents.computation_contract import ComputationRequest, RulesClearance
from src.document_extraction.models import ExtractionResult
from src.document_extraction.validation import validate_synthetic_ssn
from src.integration.contracts import IntegrationError


def _privacy_check(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            _privacy_check(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            _privacy_check(child, key)
    elif isinstance(value, str):
        candidates = re.findall(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)", value)
        if "ssn" in key.lower():
            candidates.append(value)
        for candidate in candidates:
            try:
                validate_synthetic_ssn(candidate)
            except ValueError:
                raise IntegrationError("unsafe_identifier", "intake") from None


def validate_intake(data):
    """Validate before persisting provider output. No user dialogue or tax rules."""
    try:
        if not isinstance(data, dict) or set(data) != {"facts", "amounts", "documents"}:
            raise ValueError
        if not isinstance(data["facts"], dict) or not isinstance(data["amounts"], dict):
            raise ValueError
        def encode(value):
            if isinstance(value, Decimal):
                return str(value)
            raise TypeError("Unsupported state value")
        if len(json.dumps(data, allow_nan=False, default=encode)) > 1_000_000:
            raise ValueError
        _privacy_check(data)
        documents = data["documents"]
        if not isinstance(documents, list) or len(documents) > 64:
            raise ValueError
        seen = set()
        for request in documents:
            if not isinstance(request, dict) or set(request) != {"document_id", "path"}:
                raise ValueError
            document_id, path = request["document_id"], request["path"]
            if (not isinstance(document_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:#-]{0,99}", document_id)
                    or document_id in seen or not isinstance(path, str) or not path or len(path) > 1000):
                raise ValueError
            seen.add(document_id)
        return deepcopy(data)
    except IntegrationError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise IntegrationError("invalid_intake", "intake") from None


def prepare_packet(intake, rules, extractions):
    """Return computation input and a provenance-preserving Audit view.

    Original extractions are not changed. Non-return boxes require explicit
    owner-supplied explanations; they are never silently discarded or assumed 0.
    """
    try:
        intake = validate_intake(intake)
        if not isinstance(rules, dict) or set(rules) != {"profile", "clearance", "box_dispositions"}:
            raise ValueError
        clearance = RulesClearance.model_validate(rules["clearance"])
        if not clearance.approved or clearance.blocking_conditions:
            raise IntegrationError("rules_not_cleared", "rules")
        ids = [request["document_id"] for request in intake["documents"]]
        if not isinstance(extractions, dict) or set(extractions) != set(ids):
            raise IntegrationError("document_inventory_mismatch", "intake")
        if not isinstance(rules["box_dispositions"], dict) or set(rules["box_dispositions"]) != set(ids):
            raise IntegrationError("missing_box_dispositions", "rules")
        amounts, view, bindings, notes = deepcopy(intake["amounts"]), {}, [], []
        if ids and ("1z" in amounts or "25a" in amounts):
            raise IntegrationError("conflicting_w2_input_owner", "intake")
        if ids:
            amounts["1z"], amounts["25a"] = [], []
        for document_id in ids:
            extraction = ExtractionResult.model_validate(extractions[document_id])
            record = extraction.record
            if (not extraction.ready or extraction.issues or record is None
                    or extraction.document_id != document_id or record.tax_year is None
                    or record.tax_year.value != "2025" or not {"1", "2"}.issubset(record.amounts)):
                raise IntegrationError("document_not_cleared", "rules")
            decisions = rules["box_dispositions"][document_id]
            if not isinstance(decisions, dict) or set(decisions) != set(record.amounts):
                raise IntegrationError("unaccounted_document_boxes", "rules")
            projected, excluded = {}, []
            for box, fact in record.amounts.items():
                decision = decisions[box]
                if not isinstance(decision, dict):
                    raise ValueError
                if box in ("1", "2"):
                    line = {"1": "1z", "2": "25a"}[box]
                    if decision != {"action": "use", "line": line}:
                        raise IntegrationError("invalid_w2_mapping", "rules")
                    if (fact.source.document_id != document_id or fact.source.sha256 != extraction.sha256
                            or fact.source.box != box):
                        raise IntegrationError("source_evidence_mismatch", "rules")
                    field = "box " + box
                    amounts[line].append(dict(value=str(fact.value), sources=[
                        dict(kind="document", reference=document_id, field=field)]))
                    amount_key = "box_" + box
                    projected[amount_key] = fact.model_dump(mode="json")
                    bindings.append(dict(reference=document_id, field=field, document_id=document_id, amount_key=amount_key))
                else:
                    if (set(decision) != {"action", "reason", "citations"} or decision["action"] != "not_used"
                            or not isinstance(decision["reason"], str) or not decision["reason"].strip()
                            or not isinstance(decision["citations"], list) or not decision["citations"]
                            or not all(isinstance(c, str) and c.strip() for c in decision["citations"])):
                        raise IntegrationError("unaccounted_document_boxes", "rules")
                    excluded.append(box)
            view[document_id] = dict(document_id=document_id, sha256=extraction.sha256,
                                     status="extracted", issues=[], record=dict(document_type="W-2",
                                     tax_year=record.tax_year.model_dump(mode="json"), amounts=projected))
            if excluded:
                notes.append(dict(document_id=document_id, excluded_boxes=sorted(excluded),
                                  dispositions={box: deepcopy(decisions[box]) for box in excluded}))
        request = ComputationRequest.model_validate(dict(tax_year=2025, profile=rules["profile"],
                                                         rules=clearance.model_dump(mode="json"), amounts=amounts))
        if intake["facts"].get("filing_status", request.profile.filing_status) != request.profile.filing_status:
            raise IntegrationError("filing_status_conflict", "rules")
        return dict(computation_input=request.model_dump(mode="json"), extractions=view,
                    audit_source_bindings=bindings, projection_notes=notes)
    except IntegrationError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError, DecimalException, RecursionError):
        raise IntegrationError("invalid_mapping", "rules") from None
