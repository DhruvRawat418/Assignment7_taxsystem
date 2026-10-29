"""Cross-agent conformance: does each registered guardrail actually fire?

A guardrail whose component is absent from this checkout is skipped, not
passed. Skips are visible in the pytest output, so coverage cannot be inflated
by running the harness where the agents are missing.
"""
import unittest

from src.guardrails import probes
from src.guardrails.probes import Outcome
from src.guardrails.registry import Status, all_guardrails, get


def check(test: unittest.TestCase, guardrail_id: str) -> probes.ProbeResult:
    guardrail = get(guardrail_id)
    result = probes.run(guardrail.probe)
    if result.outcome is Outcome.ABSENT:
        test.skipTest(f"{guardrail_id}: {result.detail}")
    test.assertIsNot(result.outcome, Outcome.FAIL,
                     f"{guardrail_id} ({guardrail.statement}) — {result.detail}")
    return result


class ProhibitionTests(unittest.TestCase):
    def test_draft_only(self):
        """P1: the system cannot emit a result that claims not to be a draft."""
        check(self, "P1")

    def test_advice_escalates(self):
        """P2 / E4: a request for advice stops the case."""
        check(self, "P2")

    def test_amounts_require_sources(self):
        """P3: an unsourced dollar amount cannot be constructed."""
        check(self, "P3")

    def test_escalation_surface(self):
        """P4: a block names its conditions and the authority for each."""
        check(self, "P4")

    def test_out_of_scope_escalates(self):
        """P5 / E1: an out-of-scope item stops the case."""
        check(self, "P5")

    def test_citation_integrity(self):
        """P6: an authority outside the corpus cannot be cited."""
        check(self, "P6")


class IdentifierTests(unittest.TestCase):
    def test_ssn_range(self):
        """I1: only 900-999 area numbers are accepted."""
        check(self, "I1")

    def test_rejected_ssn_not_echoed(self):
        """I2: a rejected identifier never reaches an error message or log."""
        check(self, "I2")


class EscalationTests(unittest.TestCase):
    def test_out_of_scope_condition(self):
        check(self, "E1")

    def test_document_conflict(self):
        check(self, "E2")

    def test_1099r_rule_exists(self):
        check(self, "E3")

    def test_advice_condition(self):
        check(self, "E4")

    def test_filing_status_ambiguity(self):
        """E5: bereavement blocks before any status is chosen."""
        check(self, "E5")

    def test_exploitation_is_observed_not_judged(self):
        """E6: the system notices and stops; it does not adjudicate."""
        check(self, "E6")


class OrchestrationTests(unittest.TestCase):
    def test_loop_guard(self):
        check(self, "O1")

    def test_clearance_required(self):
        check(self, "O2")


class ProbeContractTests(unittest.TestCase):
    """The harness itself must not be the weak link."""

    def test_no_probe_raises(self):
        for guardrail in all_guardrails():
            with self.subTest(guardrail=guardrail.id):
                result = probes.run(guardrail.probe)
                self.assertIsInstance(result, probes.ProbeResult)
                self.assertTrue(result.detail.strip())

    def test_unknown_probe_fails_rather_than_raising(self):
        result = probes.run("probe_that_does_not_exist")
        self.assertIs(result.outcome, Outcome.FAIL)

    def test_recorded_status_is_not_better_than_reality(self):
        """A guardrail marked enforced must not be failing its own probe."""
        for guardrail in all_guardrails():
            if guardrail.status is not Status.ENFORCED:
                continue
            with self.subTest(guardrail=guardrail.id):
                result = probes.run(guardrail.probe)
                self.assertIsNot(result.outcome, Outcome.FAIL,
                                 f"{guardrail.id} is recorded as enforced but its "
                                 f"probe fails: {result.detail}")


if __name__ == "__main__":
    unittest.main()
