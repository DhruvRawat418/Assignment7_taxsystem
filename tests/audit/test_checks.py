"""Structural checks must reject incomplete or self-inconsistent audit packets."""
import unittest
from copy import deepcopy
from tests.audit.fixtures import clean_state

from src.agents.audit_checks import check_state


class CheckTests(unittest.TestCase):
    def codes(self, state):
        return {issue["code"] for issue in check_state(state)}

    def test_clean_packet_has_no_structural_issues(self):
        state = clean_state()
        original = deepcopy(state)
        self.assertEqual(check_state(state), [])
        self.assertEqual(state, original)

    def test_empty_packet_is_not_approved(self):
        self.assertIn("invalid_contract", self.codes({}))

    def test_rules_blocker_requires_human(self):
        state = clean_state()
        state["computation_input"]["rules"]["blocking_conditions"] = ["unresolved conflict"]
        issues = check_state(state)
        self.assertTrue(any(i["code"] == "rules_not_cleared" and i["route_to"] == "human_review" for i in issues))

    def test_non_completed_computation_is_not_a_draft(self):
        for status in ("invalid_input", "needs_human_review", "tool_error"):
            with self.subTest(status=status):
                state = clean_state()
                state["computation_result"]["status"] = status
                self.assertIn("computation_not_completed", self.codes(state))

    def test_missing_and_unexpected_lines_are_rejected(self):
        for key in ("1z", "6b", "16", "37"):
            state = clean_state()
            del state["computation_result"]["lines"][key]
            self.assertIn("line_contract_mismatch", self.codes(state))
        state = clean_state()
        state["computation_result"]["lines"]["999"] = deepcopy(state["computation_result"]["lines"]["1z"])
        self.assertIn("line_contract_mismatch", self.codes(state))

    def test_invalid_money_never_crashes_or_passes(self):
        for value in (True, 12.5, "NaN", "Infinity", "0.001", "1e1000", None, {}, -1):
            state = clean_state()
            state["computation_result"]["lines"]["1z"]["value"] = value
            with self.subTest(value=value):
                self.assertIn("invalid_contract", self.codes(state))

    def test_duplicate_call_id_is_rejected(self):
        state = clean_state()
        state["computation_result"]["tool_calls"][1]["call_id"] = "call-1z"
        self.assertIn("duplicate_tool_call", self.codes(state))

    def test_dangling_and_wrong_output_calls_are_rejected(self):
        for mutate in (lambda s: s["computation_result"]["lines"]["1z"].update(tool_call_id="absent"),
                       lambda s: s["computation_result"]["tool_calls"][0].update(output_key="2b")):
            state = clean_state()
            mutate(state)
            self.assertIn("tool_link_mismatch", self.codes(state))

    def test_tampered_amount_and_unexpected_tool_are_rejected(self):
        state = clean_state()
        state["computation_result"]["lines"]["1z"]["value"] = "999.00"
        self.assertIn("recorded_value_mismatch", self.codes(state))
        state = clean_state()
        state["computation_result"]["tool_calls"][0]["tool"] = "send_payment"
        self.assertIn("tool_recipe_mismatch", self.codes(state))

    def test_wrong_dependency_or_cycle_is_rejected(self):
        for deps in (["9"], ["not-a-line"]):
            state = clean_state()
            state["computation_result"]["lines"]["9"]["depends_on"] = deps
            self.assertIn("dependency_mismatch", self.codes(state))

    def test_missing_and_forged_transitive_sources_are_rejected(self):
        for sources in ([], [dict(kind="document", reference="made-up", field="box 1")]):
            state = clean_state()
            state["computation_result"]["lines"]["9"]["sources"] = sources
            self.assertIn("source_chain_mismatch", self.codes(state))

    def test_missing_binding_and_failed_extraction_prevent_verification(self):
        state = clean_state()
        state["audit_source_bindings"] = []
        self.assertIn("source_unavailable", self.codes(state))
        state = clean_state()
        state["extractions"]["w2-1"]["status"] = "needs_review"
        self.assertIn("source_unavailable", self.codes(state))

    def test_source_amount_hash_and_box_must_match(self):
        mutations = [lambda s: s["extractions"]["w2-1"]["record"]["amounts"]["box_1"].update(value="60000.00"),
                     lambda s: s["extractions"]["w2-1"].update(sha256="b" * 64),
                     lambda s: s["extractions"]["w2-1"]["record"]["amounts"]["box_1"]["source"].update(box="2")]
        for mutate in mutations:
            state = clean_state()
            mutate(state)
            self.assertIn("source_evidence_mismatch", self.codes(state))

    def test_direct_inputs_require_actor_and_timezone(self):
        for field in ("entered_by", "recorded_at"):
            state = clean_state()
            del state["computation_input"]["amounts"]["2a"][0]["sources"][0][field]
            self.assertIn("invalid_contract", self.codes(state))
        state = clean_state()
        state["computation_input"]["amounts"]["2a"][0]["sources"][0]["recorded_at"] = "2026-10-24T00:00:00"
        self.assertIn("invalid_contract", self.codes(state))

    def test_duplicate_input_sources_are_not_counted_twice(self):
        state = clean_state()
        state["computation_input"]["amounts"]["1z"] *= 2
        self.assertIn("duplicate_input_source", self.codes(state))

    def test_taxable_amount_cannot_exceed_total(self):
        state = clean_state()
        state["computation_result"]["lines"]["6b"]["value"] = "1.00"
        state["computation_result"]["tool_calls"][23]["result"]["value"] = "1.00"
        self.assertIn("inconsistent_lines", self.codes(state))

    def test_non_draft_result_and_wrong_year_are_rejected(self):
        for field, value in (("draft_only", False), ("tax_year", 2024)):
            state = clean_state()
            state["computation_result"][field] = value
            self.assertIn("invalid_contract", self.codes(state))

    def test_malformed_nested_records_return_sanitized_errors(self):
        for key, value in (("computation_input", []), ("computation_result", None), ("audit_source_bindings", {})):
            state = clean_state()
            state[key] = value
            self.assertTrue(check_state(state))

    def test_unreferenced_active_document_is_not_silently_omitted(self):
        state = clean_state()
        extra = deepcopy(state["extractions"]["w2-1"])
        extra["document_id"] = "w2-2"
        state["extractions"]["w2-2"] = extra
        self.assertIn("unreviewed_document", self.codes(state))

    def test_unresolved_extraction_outside_used_sources_still_blocks(self):
        state = clean_state()
        state["extractions"]["unread"] = {"document_id": "unread", "status": "needs_review", "record": None, "issues": []}
        self.assertIn("unreviewed_document", self.codes(state))

    def test_document_box_cannot_be_mapped_to_wrong_tax_line(self):
        state = clean_state()
        amount = state["computation_input"]["amounts"]["1z"][0]
        state["computation_input"]["amounts"]["2b"] = [deepcopy(amount)]
        self.assertIn("source_line_mismatch", self.codes(state))

    def test_timestamp_equivalents_are_the_same_direct_input_record(self):
        state = clean_state()
        state["computation_input"]["amounts"]["2a"][0]["sources"][0]["recorded_at"] = "2026-10-24T00:00:00+00:00"
        self.assertEqual(check_state(state), [])


if __name__ == "__main__":
    unittest.main()
