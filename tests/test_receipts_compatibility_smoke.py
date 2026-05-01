import json
import subprocess
import sys
import unittest
from pathlib import Path


class ReceiptsCompatibilitySmokeTests(unittest.TestCase):
    def test_fixture_smoke_gate_returns_structured_pass(self):
        repo_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/smoke_receipts_compatibility.py", "--json"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        for name in [
            "profile",
            "context",
            "artifact-create",
            "events",
            "artifact-open",
            "guest-artifact-read",
            "guest-local-only-denials",
        ]:
            self.assertTrue(checks[name]["ok"])


if __name__ == "__main__":
    unittest.main()
