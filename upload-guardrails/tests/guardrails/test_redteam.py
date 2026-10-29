"""The red-team corpus must be well formed, and nothing in it may slip through."""
import unittest

from src.guardrails.probes import Outcome
from src.guardrails.redteam import all_cases, run_all, run_case, summary
from src.guardrails.registry import REGISTRY


class CorpusShapeTests(unittest.TestCase):
    """These need no other agent and pass on a standalone branch."""

    def test_ids_are_unique(self):
        ids = [case.id for case in all_cases()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_is_fully_specified(self):
        for case in all_cases():
            with self.subTest(case=case.id):
                self.assertTrue(case.phrasing.strip())
                self.assertTrue(case.rationale.strip())
                self.assertTrue(case.section.strip())

    def test_every_case_targets_a_registered_guardrail(self):
        for case in all_cases():
            with self.subTest(case=case.id):
                self.assertIn(case.guardrail, REGISTRY)

    def test_blocking_cases_name_the_code_they_expect(self):
        for case in all_cases():
            if case.expect_block:
                with self.subTest(case=case.id):
                    self.assertTrue(case.expect_code,
                                    f"{case.id} expects a block but names no code")

    def test_no_case_phrases_the_thing_it_is_testing(self):
        """A case that says 'I have rental income' tests nothing adversarial."""
        tells = ("out of scope", "out-of-scope", "escalate", "guardrail")
        for case in all_cases():
            with self.subTest(case=case.id):
                lowered = case.phrasing.lower()
                for tell in tells:
                    self.assertNotIn(tell, lowered,
                                     f"{case.id} uses system vocabulary, not a "
                                     "taxpayer's words")

    def test_corpus_covers_every_escalation_condition(self):
        covered = {case.guardrail for case in all_cases()}
        for condition in ("E1", "E2", "E4", "E5", "E6"):
            with self.subTest(condition=condition):
                self.assertIn(condition, covered)

    def test_corpus_covers_advice_disguised_as_transcription(self):
        advice = [c for c in all_cases() if c.guardrail == "E4"]
        self.assertGreaterEqual(len(advice), 3)


class CorpusExecutionTests(unittest.TestCase):
    """Skipped where the agent under test is absent."""

    def setUp(self):
        try:
            import src.agents.eligibility  # noqa: F401
        except Exception:
            self.skipTest("Eligibility & Rules is not present in this checkout")

    def test_no_case_slips_through(self):
        failures = [r for r in run_all() if r.outcome is Outcome.FAIL]
        self.assertEqual(
            failures, [],
            "guardrails were talked out of firing: "
            + "; ".join(f"{r.case.id} ({r.detail})" for r in failures))

    def test_each_case_individually(self):
        for case in all_cases():
            with self.subTest(case=case.id, phrasing=case.phrasing[:40]):
                result = run_case(case)
                self.assertIsNot(result.outcome, Outcome.FAIL, result.detail)

    def test_vague_free_text_never_silently_clears(self):
        """Vagueness must not resolve to nothing."""
        for case in all_cases():
            if "free_text_notes" not in case.intake_sets:
                continue
            with self.subTest(case=case.id):
                result = run_case(case)
                self.assertIs(result.outcome, Outcome.PASS)
                self.assertIn("unclassified_free_text", result.codes)

    def test_summary_reports_intake_dependence_honestly(self):
        """A pass here does not prove Intake will recognise the phrasing."""
        report = summary(run_all())
        self.assertEqual(report["total"], len(all_cases()))
        self.assertGreater(report["intake_dependent"], 0)


if __name__ == "__main__":
    unittest.main()
