"""Decision table for Eligibility & Rules. No network, no model, no API key."""
import re
import unittest
from copy import deepcopy

from src.agents.eligibility import eligibility, make_eligibility_node
from src.agents.eligibility_contract import RulesOutput
from src.agents.eligibility_rules import RULES
from src.integration.adapters import prepare_packet
from src.integration.contracts import IntegrationError, ProviderResult
from tests.eligibility.fixtures import (
    clean_state, joint_state, state_without_documents, with_boxes,
)

SENIOR = "1952-04-09"
JUST_ELIGIBLE = "1961-01-01"
JUST_INELIGIBLE = "1961-01-02"
YOUNGER = "1970-03-15"

PACKET_KEYS = ("profile", "clearance", "box_dispositions")


def run(**overrides):
    return eligibility(clean_state(**overrides))


def to_adapter(state, data):
    return prepare_packet(state["intake_snapshot"], data,
                          state["extractions"])


class ProviderShapeTests(unittest.TestCase):
    def test_clean_case_is_ready(self):
        result = run()
        self.assertIsInstance(result, ProviderResult)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.issue_codes, ())

    def test_ready_output_matches_the_three_key_contract(self):
        data = run().data
        self.assertEqual(set(data), {*PACKET_KEYS, "line_12d_boxes"})
        RulesOutput.model_validate({k: data[k] for k in PACKET_KEYS})

    def test_ready_output_is_accepted_by_the_integration_adapter(self):
        """The real contract test: the adapter must build a computation packet."""
        state = clean_state()
        packet = to_adapter(state, eligibility(state).data)
        self.assertEqual(packet["computation_input"]["profile"]["filing_status"], "single")
        self.assertEqual(packet["computation_input"]["amounts"]["1z"][0]["value"], "50000.00")
        self.assertEqual(packet["computation_input"]["amounts"]["25a"][0]["value"], "4000.00")

    def test_node_factory_returns_a_callable_provider(self):
        self.assertEqual(make_eligibility_node()(clean_state()).status, "ready")

    def test_state_is_not_mutated(self):
        state = clean_state()
        before = deepcopy(state)
        eligibility(state)
        self.assertEqual(state, before)

    def test_invalid_state_fails_closed(self):
        self.assertEqual(eligibility(None).status, "failed")

    def test_issue_codes_match_the_orchestrator_pattern(self):
        for code in run(has_rental_income=True, requested_advice=True).issue_codes:
            self.assertRegex(code, r"^[a-z][a-z_]{0,63}$")


class AgeTests(unittest.TestCase):
    def test_boundary_birthdates(self):
        for dob, expected in ((JUST_ELIGIBLE, "ready"), (JUST_INELIGIBLE, "needs_human_review"),
                              (SENIOR, "ready"), (YOUNGER, "needs_human_review")):
            with self.subTest(dob=dob):
                self.assertEqual(run(taxpayer_date_of_birth=dob).status, expected)

    def test_joint_return_needs_only_one_qualifying_spouse(self):
        result = eligibility(joint_state(taxpayer_date_of_birth=YOUNGER))
        self.assertEqual(result.status, "ready")
        self.assertTrue(result.data["profile"]["spouse_65_or_older"])
        self.assertFalse(result.data["profile"]["taxpayer_65_or_older"])

    def test_neither_spouse_qualifies_escalates(self):
        result = eligibility(joint_state(taxpayer_date_of_birth=YOUNGER,
                                         spouse_date_of_birth=YOUNGER))
        self.assertEqual(result.status, "needs_human_review")
        self.assertIn("not_eligible_for_1040sr", result.issue_codes)

    def test_age_is_derived_from_birth_date_not_a_self_reported_flag(self):
        state = clean_state()
        state["intake_snapshot"]["facts"]["taxpayer_65_or_older"] = False
        self.assertTrue(eligibility(state).data["profile"]["taxpayer_65_or_older"])


class MissingFactTests(unittest.TestCase):
    def test_missing_birth_date_asks_intake_rather_than_assuming(self):
        state = clean_state()
        del state["intake_snapshot"]["facts"]["taxpayer_date_of_birth"]
        result = eligibility(state)
        self.assertEqual(result.status, "needs_input")
        self.assertIn("taxpayer_date_of_birth", result.data["missing_facts"])

    def test_missing_filing_status_asks_intake(self):
        state = clean_state()
        del state["intake_snapshot"]["facts"]["filing_status"]
        self.assertEqual(eligibility(state).status, "needs_input")

    def test_joint_return_without_spouse_details_asks_intake(self):
        self.assertEqual(run(filing_status="mfj").status, "needs_input")

    def test_separate_return_without_living_arrangement_asks_intake(self):
        self.assertEqual(run(filing_status="mfs").status, "needs_input")

    def test_unknown_blindness_is_not_silently_false(self):
        state = clean_state()
        del state["intake_snapshot"]["facts"]["taxpayer_blind"]
        self.assertEqual(eligibility(state).status, "needs_input")


class ProfileTests(unittest.TestCase):
    def test_spouse_boxes_are_false_when_not_married(self):
        profile = run().data["profile"]
        self.assertFalse(profile["spouse_65_or_older"])
        self.assertFalse(profile["spouse_blind"])

    def test_joint_return_counts_both_spouses(self):
        profile = eligibility(joint_state(spouse_blind=True)).data["profile"]
        self.assertTrue(profile["spouse_65_or_older"])
        self.assertTrue(profile["spouse_blind"])

    def test_separate_return_spouse_boxes_are_flagged_not_guessed(self):
        result = run(filing_status="mfs", mfs_lived_with_spouse=False,
                     spouse_date_of_birth=SENIOR, spouse_blind=False)
        self.assertEqual(result.status, "needs_human_review")
        self.assertIn("separate_return_spouse_boxes", result.issue_codes)

    def test_separate_return_without_spouse_boxes_clears(self):
        result = run(filing_status="mfs", mfs_lived_with_spouse=False,
                     spouse_date_of_birth=YOUNGER, spouse_blind=False)
        self.assertEqual(result.status, "ready")
        self.assertFalse(result.data["profile"]["mfs_spouse_allowance_approved"])

    def test_line_12d_boxes_are_reported_for_the_dashboard(self):
        result = eligibility(joint_state(spouse_blind=True))
        self.assertEqual(sorted(result.data["line_12d_boxes"]),
                         ["spouse_65_or_older", "spouse_blind", "taxpayer_65_or_older"])

    def test_no_dollar_amount_is_emitted(self):
        """Money belongs to Computation. Rules emits parameters only."""
        text = str(run().data).replace(",", "")
        for amount in ("15750", "31500", "23625", "2000", "1600", "6000", "12000"):
            self.assertNotIn(amount, text)


class ScopeTests(unittest.TestCase):
    def test_each_out_of_scope_signal_escalates(self):
        for flag, code in (("wants_to_itemize", "itemized_deductions_out_of_scope"),
                           ("has_self_employment_income", "self_employment_income_out_of_scope"),
                           ("has_rental_income", "rental_income_out_of_scope"),
                           ("has_capital_gains", "capital_gains_out_of_scope"),
                           ("has_digital_assets", "digital_assets_out_of_scope"),
                           ("has_foreign_income_or_accounts", "foreign_income_out_of_scope"),
                           ("is_amended_or_prior_year", "amended_or_prior_year_out_of_scope"),
                           ("needs_state_return", "state_return_out_of_scope"),
                           ("requested_advice", "tax_advice_requested"),
                           ("third_party_pressure_observed", "possible_exploitation")):
            with self.subTest(flag=flag):
                result = run(**{flag: True})
                self.assertEqual(result.status, "needs_human_review")
                self.assertIn(code, result.issue_codes)

    def test_chart_disqualifiers_escalate(self):
        for flag, code in (("taxpayer_can_be_claimed_as_dependent", "claimed_as_dependent"),
                           ("taxpayer_dual_status_alien", "dual_status_alien")):
            with self.subTest(flag=flag):
                self.assertIn(code, run(**{flag: True}).issue_codes)

    def test_separately_filing_spouse_who_itemizes_escalates(self):
        result = run(filing_status="mfs", mfs_lived_with_spouse=True,
                     separate_spouse_itemizes=True)
        self.assertIn("separate_spouse_itemizes", result.issue_codes)

    def test_bereavement_escalates(self):
        result = eligibility(joint_state(spouse_died_during_tax_year=True))
        self.assertEqual(result.status, "needs_human_review")
        self.assertIn("filing_status_ambiguous", result.issue_codes)

    def test_unclassified_free_text_escalates_without_a_model(self):
        result = run(free_text_notes=["my son handles all of this for me"])
        self.assertIn("unclassified_free_text", result.issue_codes)

    def test_all_blockers_are_collected_in_one_pass(self):
        """Three problems reach a human once, together, not over three rounds."""
        result = run(has_rental_income=True, requested_advice=True,
                     taxpayer_can_be_claimed_as_dependent=True)
        self.assertEqual(result.status, "needs_human_review")
        self.assertGreaterEqual(len(result.data["blocking_conditions"]), 3)


class BoxDispositionTests(unittest.TestCase):
    def test_every_extracted_box_is_accounted_for(self):
        state = with_boxes({"1": "50000.00", "2": "4000.00", "3": "50000.00", "4": "3100.00"})
        decisions = eligibility(state).data["box_dispositions"]["w2-1"]
        self.assertEqual(set(decisions), {"1", "2", "3", "4"})
        self.assertEqual(decisions["1"], {"action": "use", "line": "1z"})
        self.assertEqual(decisions["2"], {"action": "use", "line": "25a"})
        self.assertEqual(decisions["3"]["action"], "not_used")

    def test_excluded_boxes_carry_a_reason_and_a_citation(self):
        state = with_boxes({"1": "50000.00", "2": "4000.00", "17": "1200.00"})
        decision = eligibility(state).data["box_dispositions"]["w2-1"]["17"]
        self.assertTrue(decision["reason"].strip())
        self.assertTrue(decision["citations"])
        for rule_id in decision["citations"]:
            self.assertIn(rule_id, RULES)

    def test_excluded_boxes_survive_the_adapter_as_projection_notes(self):
        state = with_boxes({"1": "50000.00", "2": "4000.00", "3": "50000.00"})
        packet = to_adapter(state, eligibility(state).data)
        self.assertEqual(packet["projection_notes"][0]["excluded_boxes"], ["3"])

    def test_unrecognised_box_escalates_rather_than_being_dropped(self):
        state = with_boxes({"1": "50000.00", "2": "4000.00", "zz": "99.00"})
        result = eligibility(state)
        self.assertEqual(result.status, "needs_human_review")
        self.assertIn("unrecognized_document_box", result.issue_codes)

    def test_document_with_issues_escalates(self):
        state = clean_state()
        state["extractions"]["w2-1"]["issues"] = [dict(code="low_confidence", field="1",
                                                       message="unclear")]
        self.assertIn("document_requires_attention", eligibility(state).issue_codes)

    def test_missing_extraction_escalates(self):
        state = clean_state()
        state["extractions"] = {}
        self.assertIn("extraction_missing", eligibility(state).issue_codes)

    def test_incomplete_w2_escalates(self):
        self.assertIn("incomplete_w2", eligibility(with_boxes({"1": "50000.00"})).issue_codes)

    def test_case_without_documents_still_clears(self):
        result = eligibility(state_without_documents())
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.data["box_dispositions"], {})


class ClearanceTests(unittest.TestCase):
    def test_cleared_output_carries_citations_and_no_blocking_conditions(self):
        clearance = run().data["clearance"]
        self.assertTrue(clearance["approved"])
        self.assertTrue(clearance["citations"])
        self.assertEqual(clearance["blocking_conditions"], [])

    def test_every_clearance_citation_resolves(self):
        for rule_id in run().data["clearance"]["citations"]:
            self.assertIn(rule_id, RULES)

    def test_blocked_result_cites_the_authority_for_blocking(self):
        result = run(has_rental_income=True)
        self.assertTrue(result.data["citations"])
        for rule_id in result.data["citations"]:
            self.assertIn(rule_id, RULES)

    def test_adapter_refuses_an_uncleared_packet(self):
        """A withheld clearance must never reach Computation."""
        state = clean_state()
        data = eligibility(state).data
        data["clearance"] = dict(approved=False, citations=["SCOPE-04"],
                                 blocking_conditions=["rental_income_out_of_scope"])
        with self.assertRaises(IntegrationError) as caught:
            to_adapter(state, data)
        self.assertEqual(caught.exception.code, "rules_not_cleared")


if __name__ == "__main__":
    unittest.main()
