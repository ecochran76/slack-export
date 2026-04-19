import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml

from slack_mirror.cli.main import cmd_tenants_onboard, cmd_tenants_status
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name
from slack_mirror.service import tenant_onboarding as onboarding_module
from slack_mirror.service.tenant_onboarding import (
    activate_tenant,
    install_tenant_live_units,
    install_tenant_credentials,
    manage_tenant_live_units,
    normalize_slack_domain,
    retire_tenant,
    run_tenant_backfill,
    scaffold_tenant,
    tenant_status,
)


class TenantOnboardingTests(unittest.TestCase):
    def _write_config(self, root: Path, *, include_dotenv: bool = False, create_dotenv: bool = False) -> Path:
        cfg = root / "config.yaml"
        lines = [
            "storage:",
            "  db_path: ./mirror.db",
            "workspaces:",
            "  - name: default",
            "    domain: default-team",
            "    token: xoxb-default",
            "    outbound_token: xoxb-default-write",
            "    enabled: true",
        ]
        if include_dotenv:
            lines.insert(0, "dotenv: ./tenant.env")
        cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if include_dotenv and create_dotenv:
            (root / "tenant.env").write_text("", encoding="utf-8")
        return cfg

    def test_normalize_slack_domain_accepts_workspace_url(self):
        self.assertEqual(
            normalize_slack_domain("https://polymerconsul-clo9441.slack.com"),
            "polymerconsul-clo9441",
        )

    def test_repo_root_prefers_managed_app_snapshot_when_package_lacks_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_package_file = (
                root
                / "venv"
                / "lib"
                / "python3.12"
                / "site-packages"
                / "slack_mirror"
                / "service"
                / "tenant_onboarding.py"
            )
            fake_package_file.parent.mkdir(parents=True)
            fake_package_file.write_text("", encoding="utf-8")
            managed_app = root / "home" / ".local" / "share" / "slack-mirror" / "app"
            manifest_template = managed_app / "manifests" / "slack-mirror-socket-mode.json"
            manifest_template.parent.mkdir(parents=True)
            manifest_template.write_text("{}", encoding="utf-8")

            with patch.object(onboarding_module, "__file__", str(fake_package_file)), patch.object(
                Path, "home", return_value=root / "home"
            ):
                self.assertEqual(onboarding_module._repo_root(), managed_app)

    def test_scaffold_tenant_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
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
            self.assertTrue(manifest_payload["features"]["app_home"]["messages_tab_enabled"])
            bot_scopes = manifest_payload["oauth_config"]["scopes"]["bot"]
            self.assertIn("chat:write", bot_scopes)
            self.assertIn("channels:write", bot_scopes)
            self.assertIn("groups:write", bot_scopes)
            self.assertIn("im:write", bot_scopes)
            self.assertIn("mpim:write", bot_scopes)

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
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
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

    def test_tenant_status_prefers_run_initial_sync_when_live_units_are_active_without_reconcile_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )
            install_tenant_credentials(
                config_path=cfg,
                name="polymer",
                credentials={
                    "token": "xoxb-polymer",
                    "outbound_token": "xoxb-polymer-write",
                    "app_token": "xapp-polymer",
                    "signing_secret": "secret",
                },
            )
            with patch.object(onboarding_module, "_tenant_live_unit_states", return_value={"webhooks": "active", "daemon": "active"}):
                result = activate_tenant(config_path=cfg, name="polymer", install_live_units=False)
                row = tenant_status(config_path=cfg, name="polymer")[0]

            self.assertTrue(result.tenant["enabled"])
            self.assertEqual(row["validation_status"], "needs_initial_sync")
            self.assertEqual(row["backfill_status"]["label"], "needs_initial_sync")
            self.assertEqual(row["next_action"], "run_initial_sync")

    def test_activate_tenant_blocks_until_required_credentials_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            with self.assertRaisesRegex(ValueError, "missing required credentials"):
                activate_tenant(config_path=cfg, name="polymer", install_live_units=False)

    def test_activate_tenant_enables_and_syncs_without_live_units(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            with patch.dict(
                os.environ,
                {
                    "SLACK_POLYMER_BOT_TOKEN": "xoxb-polymer",
                    "SLACK_POLYMER_WRITE_BOT_TOKEN": "xoxb-polymer-write",
                    "SLACK_POLYMER_APP_TOKEN": "xapp-polymer",
                    "SLACK_POLYMER_SIGNING_SECRET": "secret-polymer",
                },
                clear=False,
            ):
                result = activate_tenant(config_path=cfg, name="polymer", install_live_units=False)

            self.assertTrue(result.changed)
            self.assertTrue(Path(result.backup_path).exists())
            self.assertFalse(result.live_units_installed)
            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            polymer = [item for item in raw["workspaces"] if item["name"] == "polymer"][0]
            self.assertTrue(polymer["enabled"])

            conn = connect(str(root / "mirror.db"))
            apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
            row = get_workspace_by_name(conn, "polymer")
            self.assertIsNotNone(row)
            self.assertIn('"enabled": true', row["config_json"])

    def test_activate_tenant_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            with patch.dict(
                os.environ,
                {
                    "SLACK_POLYMER_BOT_TOKEN": "xoxb-polymer",
                    "SLACK_POLYMER_WRITE_BOT_TOKEN": "xoxb-polymer-write",
                    "SLACK_POLYMER_APP_TOKEN": "xapp-polymer",
                    "SLACK_POLYMER_SIGNING_SECRET": "secret-polymer",
                },
                clear=False,
            ):
                result = activate_tenant(config_path=cfg, name="polymer", dry_run=True)

            self.assertTrue(result.dry_run)
            self.assertTrue(result.tenant["enabled"])
            self.assertFalse(result.live_units_installed)
            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            polymer = [item for item in raw["workspaces"] if item["name"] == "polymer"][0]
            self.assertFalse(polymer["enabled"])

    def test_install_tenant_live_units_uses_product_script(self):
        runner = Mock()
        with tempfile.TemporaryDirectory() as td:
            cfg = self._write_config(Path(td))
            command = install_tenant_live_units(name="default", config_path=cfg, runner=runner)

        self.assertEqual(command[-2:], ["default", str(cfg.resolve())])
        runner.assert_called_once_with(command, check=True)

    def test_manage_tenant_live_units_dry_run_returns_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)

            result = manage_tenant_live_units(config_path=cfg, name="default", action="restart", dry_run=True)

            self.assertEqual(result.action, "restart")
            self.assertEqual(
                result.commands[0],
                [
                    "systemctl",
                    "--user",
                    "restart",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                ],
            )

    def test_install_tenant_live_units_wraps_called_process_error(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = self._write_config(Path(td))

            def failing_runner(*args, **kwargs):
                raise subprocess.CalledProcessError(
                    1,
                    args[0],
                    stderr="Job for slack-mirror-webhooks-default.service failed because the control process exited with error code.",
                )

            with self.assertRaisesRegex(RuntimeError, "Live-sync install failed for tenant 'default'"):
                install_tenant_live_units(name="default", config_path=cfg, runner=failing_runner)

    def test_run_tenant_backfill_dry_run_requires_enabled_and_bounds_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)

            result = run_tenant_backfill(config_path=cfg, name="default", dry_run=True, channel_limit=5)

            self.assertIn("mirror", result.commands[0])
            self.assertIn("backfill", result.commands[0])
            self.assertIn("--channel-limit", result.commands[0])
            self.assertIn("5", result.commands[0])

    def test_retire_tenant_dry_run_reports_db_counts_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="retireme",
                domain="retireme-team",
                manifest_path=root / "retireme.json",
            )

            conn = connect(str(root / "mirror.db"))
            apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
            ws = get_workspace_by_name(conn, "retireme")
            self.assertIsNotNone(ws)
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, username) VALUES (?, 'U1', 'user1')",
                (int(ws["id"]),),
            )
            conn.commit()

            result = retire_tenant(config_path=cfg, name="retireme", delete_db=True, dry_run=True)

            self.assertTrue(result.dry_run)
            self.assertTrue(result.db_deleted)
            self.assertEqual(result.db_counts["users"], 1)
            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            self.assertIn("retireme", [item["name"] for item in raw["workspaces"]])

    def test_retire_tenant_deletes_config_and_workspace_db_rows(self):
        runner = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="retireme",
                domain="retireme-team",
                manifest_path=root / "retireme.json",
            )
            conn = connect(str(root / "mirror.db"))
            apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
            ws = get_workspace_by_name(conn, "retireme")
            self.assertIsNotNone(ws)
            workspace_id = int(ws["id"])
            conn.execute(
                "INSERT INTO outbound_actions(workspace_id, kind, channel_id, text) VALUES (?, 'message', 'C1', 'hi')",
                (workspace_id,),
            )
            conn.execute(
                "INSERT INTO listeners(workspace_id, name) VALUES (?, 'listener')",
                (workspace_id,),
            )
            conn.commit()

            result = retire_tenant(config_path=cfg, name="retireme", delete_db=True, runner=runner)

            self.assertTrue(result.changed)
            self.assertTrue(result.db_deleted)
            self.assertTrue(Path(result.backup_path).exists())
            runner.assert_called_once()
            raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            self.assertNotIn("retireme", [item["name"] for item in raw["workspaces"]])
            self.assertIsNone(get_workspace_by_name(conn, "retireme"))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM outbound_actions WHERE workspace_id = ?", (workspace_id,)).fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM listeners WHERE workspace_id = ?", (workspace_id,)).fetchone()["c"],
                0,
            )

    def test_install_tenant_credentials_writes_dotenv_and_redacts_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
            dotenv = root / "tenant.env"
            dotenv.write_text("EXISTING=value\n", encoding="utf-8")
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            result = install_tenant_credentials(
                config_path=cfg,
                name="polymer",
                credentials={
                    "token": "xoxb-polymer",
                    "outbound_token": "xoxb-polymer-write",
                    "app_token": "xapp-polymer",
                    "signing_secret": "secret-polymer",
                    "unknown": "ignored",
                },
            )

            self.assertTrue(result.changed)
            self.assertTrue(Path(result.backup_path).exists())
            self.assertEqual(result.dotenv_path, str(dotenv.resolve()))
            self.assertIn("SLACK_POLYMER_BOT_TOKEN", result.installed_keys)
            self.assertIn("unknown", result.skipped_keys)
            self.assertTrue(result.tenant["credential_ready"])
            rendered = json.dumps(result.__dict__)
            self.assertNotIn("xoxb-polymer", rendered)
            self.assertNotIn("secret-polymer", rendered)
            dotenv_text = dotenv.read_text(encoding="utf-8")
            self.assertIn('SLACK_POLYMER_BOT_TOKEN="xoxb-polymer"', dotenv_text)
            self.assertIn("EXISTING=value", dotenv_text)

    def test_install_tenant_credentials_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )

            result = install_tenant_credentials(
                config_path=cfg,
                name="polymer",
                credentials={
                    "SLACK_POLYMER_BOT_TOKEN": "xoxb-polymer",
                    "SLACK_POLYMER_WRITE_BOT_TOKEN": "xoxb-polymer-write",
                    "SLACK_POLYMER_APP_TOKEN": "xapp-polymer",
                    "SLACK_POLYMER_SIGNING_SECRET": "secret-polymer",
                },
                dry_run=True,
            )

            self.assertTrue(result.dry_run)
            self.assertTrue(result.tenant["credential_ready"])
            self.assertEqual((root / "tenant.env").read_text(encoding="utf-8"), "")

    def test_cli_tenants_onboard_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
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

    def test_cli_tenants_activate_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )
            args = SimpleNamespace(config=str(cfg), name="polymer", dry_run=False, skip_live_units=True, json=True)

            with patch.dict(
                os.environ,
                {
                    "SLACK_POLYMER_BOT_TOKEN": "xoxb-polymer",
                    "SLACK_POLYMER_WRITE_BOT_TOKEN": "xoxb-polymer-write",
                    "SLACK_POLYMER_APP_TOKEN": "xapp-polymer",
                    "SLACK_POLYMER_SIGNING_SECRET": "secret-polymer",
                },
                clear=False,
            ):
                from slack_mirror.cli.main import cmd_tenants_activate

                with redirect_stdout(io.StringIO()) as out:
                    rc = cmd_tenants_activate(args)

            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["tenant"]["enabled"])
            self.assertFalse(payload["live_units_installed"])

    def test_cli_tenants_credentials_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root, include_dotenv=True, create_dotenv=True)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )
            args = SimpleNamespace(
                config=str(cfg),
                name="polymer",
                credential=[
                    "token=xoxb-polymer",
                    "outbound_token=xoxb-polymer-write",
                    "app_token=xapp-polymer",
                    "signing_secret=secret-polymer",
                ],
                credentials_json=None,
                dry_run=False,
                json=True,
            )

            from slack_mirror.cli.main import cmd_tenants_credentials

            with redirect_stdout(io.StringIO()) as out:
                rc = cmd_tenants_credentials(args)

            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["tenant"]["credential_ready"])
            self.assertNotIn("xoxb-polymer", out.getvalue())

    def test_cli_tenants_activate_json_reports_missing_credentials_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = self._write_config(root)
            scaffold_tenant(
                config_path=cfg,
                name="polymer",
                domain="polymerconsul-clo9441",
                manifest_path=root / "polymer.json",
            )
            args = SimpleNamespace(config=str(cfg), name="polymer", dry_run=False, skip_live_units=True, json=True)

            from slack_mirror.cli.main import cmd_tenants_activate

            with redirect_stdout(io.StringIO()) as out:
                rc = cmd_tenants_activate(args)

            self.assertEqual(rc, 1)
            payload = json.loads(out.getvalue())
            self.assertFalse(payload["ok"])
            self.assertIn("missing required credentials", payload["error"]["message"])

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
