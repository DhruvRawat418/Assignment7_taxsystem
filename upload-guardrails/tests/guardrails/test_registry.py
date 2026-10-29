"""The register must be well formed; a malformed guardrail is an unkept promise.

These tests need no other agent, so they pass on a branch that contains only
this component.
"""
import unittest

from src.guardrails.probes import PROBES
from src.guardrails.registry import (
    Kind, Status, all_guardrails, by_kind, by_owner, get, open_gaps,
)


class RegistryShapeTests(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [g.id for g in all_guardrails()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_guardrail_is_fully_specified(self):
        for guardrail in all_guardrails():
            with self.subTest(guardrail=guardrail.id):
                self.assertTrue(guardrail.statement.strip())
                self.assertTrue(guardrail.source.strip())
                self.assertTrue(guardrail.owner.strip())
                self.assertIsInstance(guardrail.kind, Kind)
                self.assertIsInstance(guardrail.status, Status)

    def test_every_guardrail_names_an_enforcement_point(self):
        """A guardrail with nowhere to be enforced is a wish."""
        for guardrail in all_guardrails():
            with self.subTest(guardrail=guardrail.id):
                self.assertTrue(guardrail.enforcement_points)
                for point in guardrail.enforcement_points:
                    self.assertTrue(point.startswith("src."), point)

    def test_every_guardrail_has_an_implemented_probe(self):
        """The property that makes the register more than a checklist."""
        for guardrail in all_guardrails():
            with self.subTest(guardrail=guardrail.id):
                self.assertIn(guardrail.probe, PROBES)

    def test_no_probe_is_orphaned(self):
        used = {g.probe for g in all_guardrails()}
        self.assertEqual(set(PROBES) - used, set())

    def test_partial_and_open_guardrails_explain_themselves(self):
        """An unmet guardrail must say what is missing, or the status is noise."""
        for guardrail in open_gaps():
            with self.subTest(guardrail=guardrail.id):
                self.assertTrue(guardrail.note.strip(),
                                f"{guardrail.id} is {guardrail.status.value} with no note")


class RegistryCoverageTests(unittest.TestCase):
    def test_all_six_standing_prohibitions_are_registered(self):
        self.assertEqual({g.id for g in by_kind(Kind.PROHIBITION)},
                         {"P1", "P2", "P3", "P4", "P5", "P6"})

    def test_all_six_escalation_conditions_are_registered(self):
        """Assignment 4.4 lists six; all six must appear."""
        escalations = by_kind(Kind.ESCALATION)
        self.assertEqual({g.id for g in escalations},
                         {"E1", "E2", "E3", "E4", "E5", "E6"})
        for guardrail in escalations:
            with self.subTest(guardrail=guardrail.id):
                self.assertIn("4.4", guardrail.source)

    def test_identifier_guardrails_cover_range_and_echo(self):
        self.assertEqual({g.id for g in by_kind(Kind.IDENTIFIER)}, {"I1", "I2"})

    def test_ssn_guardrail_has_defence_in_depth(self):
        """The 900-series rule is the template: more than one enforcement point."""
        self.assertGreaterEqual(len(get("I1").enforcement_points), 2)

    def test_every_guardrail_has_an_owner_on_the_team(self):
        owners = {"eligibility", "computation", "orchestrator", "guardrails",
                  "intake", "extraction", "audit"}
        for guardrail in all_guardrails():
            with self.subTest(guardrail=guardrail.id):
                self.assertIn(guardrail.owner, owners)

    def test_by_owner_partitions_the_register(self):
        owners = {g.owner for g in all_guardrails()}
        total = sum(len(by_owner(owner)) for owner in owners)
        self.assertEqual(total, len(all_guardrails()))

    def test_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            get("P99")


if __name__ == "__main__":
    unittest.main()
