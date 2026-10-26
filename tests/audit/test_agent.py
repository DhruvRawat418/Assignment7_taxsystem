"""Independent test-only arithmetic service; never represented as real MCP."""
import asyncio
from copy import deepcopy
from decimal import Decimal
import unittest
from tests.audit.fixtures import clean_state

from src.agents.audit import audit, make_audit_node


class SyntheticToolClient:
    """Real elementary arithmetic, literal special-case answers for one fixture.

    Not a tax engine. Special tools reject other profiles/amounts rather than
    silently pretend to implement tax law. Tests and the labelled demo only.
    """
    async def call(self, name, arguments):
        if name == "sum_amounts":
            value = sum((Decimal(v) for v in arguments["values"]), Decimal("0"))
        elif name == "difference":
            value = Decimal(arguments["left"]) - Decimal(arguments["right"])
            if arguments["floor_zero"]:
                value = max(Decimal("0"), value)
        elif name == "standard_deduction":
            assert arguments["profile"]["filing_status"] == "single"
            assert arguments["profile"]["taxpayer_65_or_older"] is True
            value = Decimal("17750.00")
        elif name == "senior_deduction":
            assert Decimal(arguments["agi"]) == Decimal("50000")
            value = Decimal("6000.00")
        elif name == "social_security_taxable":
            assert Decimal(arguments["benefits"]) == Decimal("0")
            assert Decimal(arguments["other_income"]) == Decimal("50000")
            value = Decimal("0.00")
        elif name == "income_tax":
            assert Decimal(arguments["taxable_income"]) == Decimal("26250")
            assert Decimal(arguments["qualified_dividends"]) == Decimal("0")
            assert arguments["filing_status"] == "single"
            value = Decimal("2911.50")
        else:
            raise AssertionError("An unapproved tool was executed")
        return {"value": str(value), "rule_references": ["synthetic-rule"]}


class AuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_packet_passes_independent_recheck_without_mutation(self):
        state = clean_state()
        before = deepcopy(state)
        result = await audit(state, SyntheticToolClient())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["issues"], [])
        self.assertEqual(len(result["verified_lines"]), 40)
        self.assertEqual(result["review_scope"], "deterministic_component")
        self.assertEqual(state, before)

    async def test_missing_client_fails_closed(self):
        result = await audit(clean_state())
        self.assertEqual(result["status"], "verification_unavailable")
        self.assertIn("mcp_unavailable", {i["code"] for i in result["issues"]})

    async def test_self_consistent_forgery_is_caught_from_original_inputs(self):
        state = clean_state()
        state["computation_result"]["lines"]["1z"]["value"] = "99999.00"
        call = state["computation_result"]["tool_calls"][0]
        call["arguments"]["values"] = ["99999.00"]
        call["result"]["value"] = "99999.00"
        result = await audit(state, SyntheticToolClient())
        self.assertEqual(result["status"], "revision_required")
        self.assertTrue({"tool_arguments_mismatch", "recomputed_value_mismatch"}.issubset({i["code"] for i in result["issues"]}))

    async def test_unknown_recorded_tool_is_never_executed(self):
        class MustNotCall:
            async def call(self, *args):
                raise AssertionError("Structural failures must not call any tools")
        state = clean_state()
        state["computation_result"]["tool_calls"][0]["tool"] = "delete_files"
        result = await audit(state, MustNotCall())
        self.assertEqual(result["status"], "revision_required")
        self.assertEqual(result["verified_lines"], [])

    async def test_failed_mcp_response_cannot_pass_and_does_not_leak_error(self):
        class Broken:
            async def call(self, *args):
                raise RuntimeError("secret-901-12-3456")
        result = await audit(clean_state(), Broken())
        self.assertEqual(result["status"], "verification_unavailable")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("901-12-3456", str(result))

    async def test_malformed_tool_responses_are_rejected(self):
        for response in (None, {"value": "NaN", "rule_references": ["x"]},
                         {"value": "1.00", "rule_references": []}):
            class Broken:
                async def call(self, *args):
                    return response
            result = await audit(clean_state(), Broken())
            self.assertEqual(result["status"], "verification_unavailable")

    async def test_timeout_is_bounded(self):
        class Slow:
            async def call(self, *args):
                await asyncio.sleep(1)
        result = await audit(clean_state(), Slow(), tool_timeout=0.001)
        self.assertEqual(result["status"], "verification_unavailable")

    async def test_cancellation_is_not_swallowed(self):
        class Cancelled:
            async def call(self, *args):
                raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await audit(clean_state(), Cancelled())

    async def test_rules_and_missing_sources_route_without_tools(self):
        state = clean_state()
        state["computation_input"]["rules"]["approved"] = False
        self.assertEqual((await audit(state))["status"], "needs_human_review")
        state = clean_state()
        state["audit_source_bindings"] = []
        self.assertEqual((await audit(state))["status"], "verification_unavailable")

    async def test_node_returns_only_own_namespace_and_clears_stale_success(self):
        node = make_audit_node(SyntheticToolClient())
        state = clean_state()
        first = await node(state)
        self.assertEqual(set(first), {"audit_result"})
        self.assertEqual(first["audit_result"]["status"], "passed")
        state.update(first)
        state["computation_input"]["rules"]["approved"] = False
        second = await node(state)
        self.assertEqual(second["audit_result"]["status"], "needs_human_review")
        self.assertEqual(second["audit_result"]["verified_lines"], [])
        self.assertNotEqual(first["audit_result"]["input_fingerprint"], second["audit_result"]["input_fingerprint"])

    async def test_semantically_equal_decimal_strings_do_not_false_alarm(self):
        state = clean_state()
        state["computation_result"]["tool_calls"][0]["arguments"]["values"] = ["50000"]
        self.assertEqual((await audit(state, SyntheticToolClient()))["status"], "passed")

    async def test_tool_return_value_is_checked_not_only_recorded_trace(self):
        class Wrong(SyntheticToolClient):
            async def call(self, name, arguments):
                result = await super().call(name, arguments)
                if name == "income_tax":
                    result["value"] = "3000.00"
                return result
        result = await audit(clean_state(), Wrong())
        self.assertEqual(result["status"], "revision_required")
        self.assertIn("recomputed_value_mismatch", {i["code"] for i in result["issues"]})

    async def test_fix_and_resubmit_reaudits_instead_of_modifying_input(self):
        state = clean_state()
        original = deepcopy(state)
        state["computation_result"]["lines"]["16"]["value"] = "9000.00"
        self.assertEqual((await audit(state, SyntheticToolClient()))["status"], "revision_required")
        self.assertEqual(state["computation_result"]["lines"]["16"]["value"], "9000.00")
        self.assertEqual((await audit(original, SyntheticToolClient()))["status"], "passed")


if __name__ == "__main__":
    unittest.main()
