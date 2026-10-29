"""The corpus is the only source of authority; citations must be verifiable."""
import unittest

from src.agents.eligibility import BASE_CITATIONS, disposition_for_box
from src.agents.eligibility_rules import (
    RULES, UnknownRuleError, W2_LINE_BOXES, W2_NOT_USED, cite, describe, get_rule,
    validate_rule_ids,
)


class CorpusTests(unittest.TestCase):
    def test_rule_ids_are_unique_and_self_consistent(self):
        for rule_id, rule in RULES.items():
            self.assertEqual(rule_id, rule.id)
            self.assertTrue(rule.title.strip())
            self.assertTrue(rule.text.strip())
            self.assertTrue(rule.source.strip())

    def test_unknown_rule_cannot_be_cited(self):
        with self.assertRaises(UnknownRuleError):
            cite("SD-99")

    def test_a_determination_must_cite_something(self):
        with self.assertRaises(UnknownRuleError):
            cite()

    def test_get_rule_rejects_an_unknown_id(self):
        with self.assertRaises(UnknownRuleError):
            get_rule("NOPE-01")

    def test_validate_rule_ids_splits_known_from_unknown(self):
        known, unknown = validate_rule_ids(["SCOPE-04", "INVENTED-01"])
        self.assertEqual(known, ["SCOPE-04"])
        self.assertEqual(unknown, ["INVENTED-01"])

    def test_describe_renders_a_rule_for_the_dashboard(self):
        self.assertEqual(set(describe("SD-02")), {"rule_id", "title", "text", "source"})

    def test_base_citations_all_resolve(self):
        for rule_id in BASE_CITATIONS:
            self.assertIn(rule_id, RULES)


class BoxTableTests(unittest.TestCase):
    def test_line_boxes_and_excluded_boxes_do_not_overlap(self):
        self.assertFalse(set(W2_LINE_BOXES) & set(W2_NOT_USED))

    def test_every_excluded_box_names_a_real_rule(self):
        for box, rule_id in W2_NOT_USED.items():
            self.assertIn(rule_id, RULES, f"box {box}")

    def test_line_boxes_map_to_the_contract_lines(self):
        self.assertEqual(W2_LINE_BOXES, {"1": "1z", "2": "25a"})

    def test_known_box_yields_a_decision(self):
        self.assertEqual(disposition_for_box("1").line, "1z")
        self.assertEqual(disposition_for_box("5").action, "not_used")

    def test_unknown_box_yields_no_decision(self):
        self.assertIsNone(disposition_for_box("zz"))


if __name__ == "__main__":
    unittest.main()
