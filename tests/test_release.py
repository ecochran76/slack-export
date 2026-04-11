import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from slack_mirror.service.release import release_check


class ReleaseCheckTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = \"slack-mirror\"\nversion = \"0.2.0-dev\"\n",
            encoding="utf-8",
        )
        (self.root / "scripts").mkdir(parents=True, exist_ok=True)

    def test_release_check_passes_with_dev_warning(self):
        output = []

        def runner(args, check=False, text=False, cwd=None, capture_output=False):
            if "check_generated_docs.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")
            if "audit_planning_contract.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"ok": true}\n', stderr="")
            if args[:3] == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected command: {args}")

        rc = release_check(repo_root=self.root, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("WARN  [DEV_VERSION]", rendered)
        self.assertIn("Summary: PASS with warnings", rendered)

    def test_release_check_fails_when_release_version_required(self):
        output = []

        def runner(args, check=False, text=False, cwd=None, capture_output=False):
            if "check_generated_docs.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")
            if "audit_planning_contract.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"ok": true}\n', stderr="")
            if args[:3] == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected command: {args}")

        rc = release_check(
            repo_root=self.root,
            runner=runner,
            out=output.append,
            require_release_version=True,
        )

        self.assertEqual(rc, 1)
        self.assertIn("FAIL  [RELEASE_VERSION_REQUIRED]", "\n".join(output))

    def test_release_check_json_reports_dirty_worktree_failure(self):
        output = []

        def runner(args, check=False, text=False, cwd=None, capture_output=False):
            if "check_generated_docs.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")
            if "audit_planning_contract.py" in " ".join(args):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"ok": true}\n', stderr="")
            if args[:3] == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=" M README.md\n", stderr="")
            raise AssertionError(f"unexpected command: {args}")

        rc = release_check(
            repo_root=self.root,
            runner=runner,
            out=output.append,
            json_output=True,
            require_clean=True,
        )

        self.assertEqual(rc, 1)
        payload = json.loads(output[0])
        self.assertEqual(payload["status"], "fail")
        self.assertIn("DIRTY_WORKTREE", payload["failure_codes"])
