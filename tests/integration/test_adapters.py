from copy import deepcopy
import pytest
from tests.integration.fixtures import extracted, intake_data, rules_data

from src.integration.adapters import prepare_packet, validate_intake
from src.integration.contracts import IntegrationError


def test_real_extraction_schema_maps_to_computation_and_audit_without_mutation():
    intake, rules, extractions = intake_data(), rules_data(), {"w2-1": extracted()}
    before = deepcopy((intake, rules, extractions))
    packet = prepare_packet(intake, rules, extractions)
    assert "computation_input" in packet
    request = packet["computation_input"]
    assert request["amounts"]["1z"][0]["value"] == "50000.00"
    assert request["amounts"]["25a"][0]["value"] == "4000.00"
    assert request["amounts"]["1z"][0]["sources"][0]["reference"] == "w2-1"
    assert set(packet["extractions"]["w2-1"]["record"]["amounts"]) == {"box_1", "box_2"}
    assert "employee_ssn" not in packet["extractions"]["w2-1"]["record"]
    assert packet["audit_source_bindings"][0]["amount_key"] == "box_1"
    assert (intake, rules, extractions) == before


def test_missing_explicit_zero_is_not_invented():
    intake = intake_data()
    del intake["amounts"]["2a"]
    with pytest.raises(IntegrationError):
        prepare_packet(intake, rules_data(), {"w2-1": extracted()})


def test_denied_rules_and_unresolved_document_block():
    rules = rules_data()
    rules["clearance"]["approved"] = False
    with pytest.raises(IntegrationError):
        prepare_packet(intake_data(), rules, {"w2-1": extracted()})
    item = extracted()
    item["status"] = "needs_review"
    with pytest.raises(IntegrationError):
        prepare_packet(intake_data(), rules_data(), {"w2-1": item})


def test_additional_boxes_need_explicit_rule_disposition():
    item = extracted()
    item["record"]["amounts"]["3"] = deepcopy(item["record"]["amounts"]["1"])
    item["record"]["amounts"]["3"]["source"]["box"] = "3"
    with pytest.raises(IntegrationError):
        prepare_packet(intake_data(), rules_data(), {"w2-1": item})
    rules = rules_data()
    rules["box_dispositions"]["w2-1"]["3"] = {
        "action": "not_used", "reason": "Explicit synthetic Rules decision", "citations": ["synthetic-rule"]}
    packet = prepare_packet(intake_data(), rules, {"w2-1": item})
    assert "projection_notes" in packet
    assert packet["projection_notes"][0]["excluded_boxes"] == ["3"]


def test_missing_inventory_duplicate_id_and_reused_inputs_are_rejected():
    for mutate in (lambda i: i["documents"].append(deepcopy(i["documents"][0])),
                   lambda i: i["amounts"].update({"1z": [{"value": "0", "sources": []}]})):
        intake = intake_data()
        mutate(intake)
        with pytest.raises(IntegrationError):
            prepare_packet(intake, rules_data(), {"w2-1": extracted()})
    with pytest.raises(IntegrationError):
        prepare_packet(intake_data(), rules_data(), {})


def test_no_documents_still_requires_explicit_wage_and_withholding_inputs():
    intake = intake_data(documents=False)
    packet = prepare_packet(intake, rules_data(document_ids=()), {})
    assert "computation_input" in packet
    assert packet["computation_input"]["amounts"]["1z"][0]["value"] == "50000.00"


@pytest.mark.parametrize("facts", [{"ssn": "123-45-6789"}, {"note": "my number is 123-45-6789"}, {"spouse": {"ssn": "123456789"}}])
def test_intake_boundary_rejects_unsafe_ssns_without_echo(facts):
    intake = intake_data()
    intake["facts"].update(facts)
    with pytest.raises(IntegrationError) as caught:
        validate_intake(intake)
    assert "123" not in str(caught.value)


def test_unknown_and_malformed_disposition_is_not_clearance():
    for disposition in ({"action": "not_used"}, {"action": "use", "line": "2b"}, True):
        rules = rules_data()
        rules["box_dispositions"]["w2-1"]["1"] = disposition
        with pytest.raises(IntegrationError):
            prepare_packet(intake_data(), rules, {"w2-1": extracted()})


@pytest.mark.parametrize("section", ["facts", "amounts"])
def test_intake_rejects_non_json_objects_instead_of_serializing_them_as_null(section):
    intake = intake_data()
    intake[section]["unsupported"] = object()
    with pytest.raises(IntegrationError):
        validate_intake(intake)


def test_privacy_boundary_checks_amount_provenance_not_only_facts():
    intake = intake_data()
    intake["amounts"]["2a"][0]["sources"][0]["reference"] = "person-123-45-6789"
    with pytest.raises(IntegrationError):
        validate_intake(intake)
