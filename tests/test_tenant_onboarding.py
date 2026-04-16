import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import yaml

from slack_mirror.cli.main import cmd_tenants_onboard, cmd_tenants_status
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name
from slack_mirror.service.tenant_onboarding import (
    normalize_slack_domain,
    scaffold_tenant,
    tenant_status,
)


class TenantOnboardingTests(unittest.TestCase):
    def _write_config(self, root: Path) -> Path:
        cfg = root / "config.yaml"
        cfg.write_text(
            "storage:\n"
            "  db_path: ./mirror.db\n"
            "workspaces:\n"
            "  - name: default\n"
            "    domain: default-team\n"
            "    token: xoxb-default\n"
            "    outbound_token: xoxb-default-write\n"
            "    enabled: true\n",
            encoding="utf-8",
        )
        return cfg

    def test_normalize_slack_domain_accepts_workspace_url(self):
        self.assertEqual(
            normalize_slack_domain("https://polymerconsul-clo9441.slack.com"),
            "polymerconsul-clo9441",
        )

    def test_scaffold_tenant_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            manifest = root / "polymer.json"

            result = scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="https://polymerconsul-clo9441.slack.com",
                display_name="Polymer Consulting Group",
                manifest_path=manifest,
                dry_run=True,
            )

            self.assertFalse(manifest.exists())
            self.assertIsNone(result.backup_path)
            self.assertEqual(result.tenant["name"], "polymer")
            self.assertEqual(result.tenant["next_action"], "credentials_required")
            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in raw["workspaces"]], ["default"])

    def test_scaffold_tenant_writes_config_manifest_backup_and_db_sync(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            manifest = root / "polymer.json"

            result = scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                display_name="Polymer Consulting Group",
                manifest_path=manifest,
            )

            self.assertTrue(result.changed)
            self.assertTrue(Path(result.backup_path).exists())
            self.assertTrue(manifest.exists())
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["display_information"]["name"], "Slack Mirror Polymer Consulting Group")

            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            polymer = [item for item in raw["workspaces"] if item["name"] == "polymer"][0]
            self.assertFalse(polymer["enabled"])
            self.assertEqual(polymer["token"], "${SLACK_POLYMER_BOT_TOKEN:-}")

            conn = connect(str(root / "mirror.db"))
            apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
            self.assertIsNotNone(get_workspace_by_name(conn, "polymer"))

    def test_tenant_status_reports_missing_credentials_without_secret_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            row = tenant_status(config_path=cfg, name="polymer")[0]

            self.assertFalse(row["enabled"])
            self.assertFalse(row["credential_ready"])
            self.assertIn("token", row["missing_required_credentials"])
            self.assertEqual(row["credential_presence"]["token"]["env"], "SLACK_POLYMER_BOT_TOKEN")
            rendered = json.dumps(row)
            self.assertNotIn("xox", rendered)

    def test_cli_tenants_onboard_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            args = SimpleNamespace(
                config=str(cfg),
                name="polymer",
                domain="polymerconsul-clo9441",
                display_name="Polymer Consulting Group",
                manifest_path=str(root / "polymer.json"),
                dry_run=True,
                no_sync=False,
                json=True,
            )

            with redirect_stdout(io.StringIO()) as out:
                rc = cmd_tenants_onboard(args)

            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["tenant"]["name"], "polymer")

    def test_cli_tenants_status_plain(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            args = SimpleNamespace(config=str(cfg), name=None, json=False)

            with redirect_stdout(io.StringIO()) as out:
                rc = cmd_tenants_status(args)

            self.assertEqual(rc, 0)
            self.assertIn("default\tenabled", out.getvalue())


if __name__ == "__main__":
    unittest.main()

