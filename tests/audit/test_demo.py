import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests.audit.fixtures import clean_state

ROOT = Path(__file__).resolve().parents[2]


class DemoTests(unittest.TestCase):
    def run_demo(self, *arguments):
        return subprocess.run([sys.executable, "-m", "demo.run_audit", *arguments], cwd=ROOT,
                              text=True, capture_output=True, timeout=10)

    def test_explicit_synthetic_demo_passes_but_is_not_claimed_to_be_mcp(self):
        result = self.run_demo("--synthetic-demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "passed")
        self.assertEqual(output["execution_mode"], "synthetic_test_double")

    def test_tampered_synthetic_demo_requires_revision(self):
        result = self.run_demo("--synthetic-demo", "--tamper")
        self.assertTrue(result.stdout.startswith("{"), result.stderr)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "revision_required")

    def test_real_packet_without_configured_client_is_never_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(clean_state()))
            result = self.run_demo(str(path))
        self.assertTrue(result.stdout.startswith("{"), result.stderr)
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "verification_unavailable")
        self.assertEqual(output["execution_mode"], "no_mcp_client")

    def test_malformed_file_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("secret-901-12-3456")
            result = self.run_demo(str(path))
        self.assertTrue(result.stdout.startswith("{"), result.stderr)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("secret", result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "revision_required")
