"""Deterministic contract, provenance and consistency checks; no state mutation."""
import re
from src.agents.audit_contract import (
    ALL_LINES, INPUT_LINES, INTERMEDIATES, SPECS, issue, money,
    normalized_profile, references, source_key, text,
)


def _sources(items):
    if not isinstance(items, list) or len(items) > 256:
        raise ValueError("Invalid sources")
    keys = [source_key(source) for source in items]
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated source metadata")
    return set(keys)


def _document_check(state, source, value, line):
    bindings = state.get("audit_source_bindings", [])
    if not isinstance(bindings, list) or len(bindings) > 512:
        raise ValueError("Invalid bindings")
    matches = [b for b in bindings if isinstance(b, dict) and
               (b.get("reference"), b.get("field")) == (source["reference"], source["field"])]
    if not matches:
        return issue("source_unavailable", line, "document_extraction", True)
    if len(matches) != 1:
        return issue("source_evidence_mismatch", line, "document_extraction")
    binding = matches[0]
    document_id, amount_key = text(binding.get("document_id")), text(binding.get("amount_key"))
    extraction = state.get("extractions", {}).get(document_id)
    if not isinstance(extraction, dict) or extraction.get("status") != "extracted":
        return issue("source_unavailable", line, "document_extraction", True)
    record = extraction.get("record")
    if not isinstance(record, dict) or record.get("document_type") != "W-2":
        return issue("source_unavailable", line, "document_extraction", True)
    fact = record.get("amounts", {}).get(amount_key)
    if not isinstance(fact, dict):
        return issue("source_unavailable", line, "document_extraction", True)
    evidence = fact.get("source", {})
    expected_box = {"box_1": "1", "box_2": "2"}.get(amount_key)
    # Only the supplied W-2 extraction schema is implemented. No guessed 1099 mapping.
    if expected_box is None:
        return issue("source_unavailable", line, "document_extraction", True)
    if line != {"box_1": "1z", "box_2": "25a"}[amount_key]:
        return issue("source_line_mismatch", line, "eligibility_rules")
    if (extraction.get("document_id") != document_id or evidence.get("document_id") != document_id
            or not re.fullmatch(r"[0-9a-fA-F]{64}", str(extraction.get("sha256", "")))
            or evidence.get("sha256") != extraction["sha256"]
            or str(evidence.get("box")) != expected_box
            or record.get("tax_year", {}).get("value") != "2025"
            or extraction.get("issues") or fact.get("origin") != "document"
            or money(fact.get("value")) != money(value)):
        return issue("source_evidence_mismatch", line, "document_extraction")
    return None


def _check(state):
    if not isinstance(state, dict):
        raise ValueError("Invalid state")
    request, result = state["computation_input"], state["computation_result"]
    if not isinstance(request, dict) or not isinstance(result, dict):
        raise ValueError("Invalid packet")
    if (type(request.get("tax_year")) is not int or request["tax_year"] != 2025
            or type(result.get("tax_year")) is not int or result["tax_year"] != 2025
            or result.get("draft_only") is not True):
        raise ValueError("Only 2025 drafts")
    profile = normalized_profile(request["profile"])
    rules = request["rules"]
    if not isinstance(rules, dict) or type(rules.get("approved")) is not bool or not isinstance(rules.get("blocking_conditions"), list):
        raise ValueError("Invalid clearance")
    references(rules.get("citations"))
    if not rules["approved"] or rules["blocking_conditions"]:
        return [issue("rules_not_cleared", route_to="human_review")]
    if (not profile["taxpayer_65_or_older"] and not
            (profile["filing_status"] == "mfj" and profile["spouse_65_or_older"])):
        return [issue("eligibility_not_cleared", route_to="eligibility_rules")]
    if (profile["filing_status"] == "mfs" and (profile["spouse_65_or_older"] or profile["spouse_blind"])
            and not profile["mfs_spouse_allowance_approved"]):
        return [issue("eligibility_not_cleared", route_to="eligibility_rules")]
    if result.get("status") != "completed":
        owner = "human_review" if result.get("status") == "needs_human_review" else "computation"
        return [issue("computation_not_completed", route_to=owner)]
    if result.get("issues") != []:
        return [issue("unresolved_computation_issues", route_to="human_review")]
    amounts = request["amounts"]
    if not isinstance(amounts, dict) or set(amounts) != set(INPUT_LINES):
        raise ValueError("Missing explicit input lines")
    if not isinstance(state.get("extractions", {}), dict) or not isinstance(state.get("audit_source_bindings", []), list):
        raise ValueError("Invalid evidence container")
    problems, inherited, verified_fields = [], {}, set()
    for line, entries in amounts.items():
        if not isinstance(entries, list) or not entries or len(entries) > 128:
            raise ValueError("Explicit sourced amounts required")
        seen, canonical_seen, inherited[line] = set(), set(), set()
        for entry in entries:
            amount = money(entry["value"])
            if line != "8" and amount < 0:
                raise ValueError("Negative input")
            sources = entry["sources"]
            if not sources:
                raise ValueError("Unsourced input")
            inherited[line].update(_sources(sources))
            identities = {(s["kind"], s["reference"], s["field"]) for s in sources}
            if seen.intersection(identities):
                problems.append(issue("duplicate_input_source", line, "eligibility_rules"))
            seen.update(identities)
            entry_facts = set()
            for source in sources:
                if source["kind"] == "document":
                    problem = _document_check(state, source, entry["value"], line)
                    if problem:
                        problems.append(problem)
                    else:
                        binding = next(b for b in state["audit_source_bindings"] if
                                       (b.get("reference"), b.get("field")) == (source["reference"], source["field"]))
                        verified_fields.add((binding["document_id"], binding["amount_key"]))
                        # Aliases and repeat uploads of the same file do not
                        # create independent monetary facts. Multiple supporting
                        # aliases within ONE entry are allowed; separate entries
                        # must not consume that same evidence twice.
                        extraction = state["extractions"][binding["document_id"]]
                        entry_facts.add((extraction["sha256"].lower(), binding["amount_key"]))
            if canonical_seen.intersection(entry_facts):
                problems.append(issue("duplicate_document_fact", line, "eligibility_rules"))
            canonical_seen.update(entry_facts)

    # The integration layer must provide only active documents here. Superseded
    # uploads belong in historical storage, not silently ignored active evidence.
    for document_id, extraction in state.get("extractions", {}).items():
        if (not isinstance(extraction, dict) or extraction.get("status") != "extracted"
                or extraction.get("issues") or not isinstance(extraction.get("record"), dict)
                or extraction["record"].get("document_type") != "W-2"
                or not extraction["record"].get("amounts")
                or any((document_id, key) not in verified_fields for key in extraction["record"]["amounts"])):
            problems.append(issue("unreviewed_document", route_to="eligibility_rules"))

    form, work = result["lines"], result["intermediates"]
    if (not isinstance(form, dict) or not isinstance(work, dict)
            or set(form) != ALL_LINES - INTERMEDIATES or set(work) != INTERMEDIATES):
        return problems + [issue("line_contract_mismatch")]
    lines = {**form, **work}
    calls = result["tool_calls"]
    if not isinstance(calls, list) or len(calls) != len(SPECS):
        return problems + [issue("tool_link_mismatch")]
    by_id, positions = {}, {}
    for position, call in enumerate(calls):
        call_id = text(call["call_id"])
        if call_id in by_id:
            return problems + [issue("duplicate_tool_call")]
        if not isinstance(call["arguments"], dict) or not isinstance(call["result"], dict):
            raise ValueError("Invalid tool record")
        text(call["tool"])
        by_id[call_id], positions[call_id] = call, position
    used_calls = set()
    for key, tool, deps in SPECS:
        line = lines[key]
        value = money(line["value"])
        if key not in ("8", "9", "11a", "11b", "income_before_ss") and value < 0:
            raise ValueError("Negative line")
        references(line["rule_references"])
        if not set(rules["citations"]).issubset(line["rule_references"]):
            problems.append(issue("rule_reference_mismatch", key))
        call_id = text(line["tool_call_id"])
        call = by_id.get(call_id)
        if call is None or call.get("output_key") != key or call_id in used_calls:
            problems.append(issue("tool_link_mismatch", key))
            continue
        used_calls.add(call_id)
        references(call["result"].get("rule_references"))
        if not set(call["result"]["rule_references"]).issubset(line["rule_references"]):
            problems.append(issue("rule_reference_mismatch", key))
        if money(call["result"].get("value")) != value:
            problems.append(issue("recorded_value_mismatch", key))
        if call["tool"] != tool:
            problems.append(issue("tool_recipe_mismatch", key))
        if line["depends_on"] != list(deps):
            problems.append(issue("dependency_mismatch", key))
        if any(positions.get(lines[d].get("tool_call_id"), len(calls)) >= positions[call_id] for d in deps):
            problems.append(issue("dependency_order_mismatch", key))
        if key not in inherited:
            inherited[key] = set().union(*(inherited[d] for d in deps)) if deps else set()
        if _sources(line["sources"]) != inherited[key]:
            problems.append(issue("source_chain_mismatch", key))
    for part, whole in (("3a", "3b"), ("4b", "4a"), ("5b", "5a"), ("6b", "6a"), ("ss_adjustments", "10")):
        if money(lines[part]["value"]) > money(lines[whole]["value"]):
            problems.append(issue("inconsistent_lines", part, "eligibility_rules"))
    if money(lines["34"]["value"]) > 0 and money(lines["37"]["value"]) > 0:
        problems.append(issue("inconsistent_lines", "34"))
    return problems


def check_state(state):
    """Malformed/unavailable evidence fails closed with sanitized issues."""
    try:
        return _check(state)
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        return [issue("invalid_contract", route_to="orchestrator")]
