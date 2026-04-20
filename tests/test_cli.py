import unittest
from unittest.mock import patch

from slack_mirror import __version__
from slack_mirror.cli.main import (
    build_parser,
    cmd_mirror_backfill,
    cmd_mirror_reconcile_files,
    cmd_release_check,
    cmd_serve_api,
    cmd_serve_mcp,
    cmd_user_env_check_live,
    cmd_user_env_install,
    cmd_user_env_provision_frontend_user,
    cmd_user_env_rollback,
    cmd_user_env_recover_live,
    cmd_user_env_snapshot_report,
    cmd_user_env_status,
    cmd_user_env_uninstall,
    cmd_user_env_update,
    cmd_user_env_validate_live,
)


class CliTests(unittest.TestCase):
    def test_parse_mirror_backfill(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "backfill",
                "--workspace",
                "default",
                "--auth-mode",
                "user",
                "--include-messages",
                "--messages-only",
                "--channels",
                "C123,C456",
                "--channel-limit",
                "3",
                "--oldest",
                "1700000000.000000",
                "--latest",
                "1800000000.000000",
                "--include-files",
                "--file-types",
                "all",
                "--download-content",
                "--cache-root",
                "./cache-test",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.auth_mode, "user")
        self.assertTrue(args.include_messages)
        self.assertTrue(args.messages_only)
        self.assertEqual(args.channels, "C123,C456")
        self.assertEqual(args.channel_limit, 3)
        self.assertEqual(args.oldest, "1700000000.000000")
        self.assertEqual(args.latest, "1800000000.000000")
        self.assertTrue(args.include_files)
        self.assertEqual(args.file_types, "all")
        self.assertTrue(args.download_content)
        self.assertEqual(args.cache_root, "./cache-test")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_workspaces_verify(self):
        parser = build_parser()
        args = parser.parse_args(["workspaces", "verify", "--workspace", "default"])
        self.assertEqual(args.command, "workspaces")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_oauth_callback(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "oauth-callback",
                "--workspace",
                "default",
                "--cert-file",
                "./localhost+2.pem",
                "--key-file",
                "./localhost+2-key.pem",
                "--scopes",
                "chat:write,channels:history",
                "--user-scopes",
                "channels:history",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.cert_file, "./localhost+2.pem")
        self.assertEqual(args.key_file, "./localhost+2-key.pem")
        self.assertEqual(args.bind, "localhost")
        self.assertEqual(args.port, 3000)
        self.assertEqual(args.callback_path, "/slack/oauth/callback")
        self.assertEqual(args.scopes, "chat:write,channels:history")
        self.assertEqual(args.user_scopes, "channels:history")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_serve_webhooks(self):
        parser = build_parser()
        args = parser.parse_args(
            ["mirror", "serve-webhooks", "--workspace", "default", "--bind", "0.0.0.0", "--port", "8787"]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.bind, "0.0.0.0")
        self.assertEqual(args.port, 8787)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_embeddings_backfill(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "embeddings-backfill",
                "--workspace",
                "default",
                "--retrieval-profile",
                "local-bge",
                "--model",
                "BAAI/bge-m3",
                "--limit",
                "50",
                "--channels",
                "C123,C456",
                "--oldest",
                "1700000000.000000",
                "--latest",
                "1800000000.000000",
                "--order",
                "oldest",
                "--json",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.retrieval_profile, "local-bge")
        self.assertEqual(args.model, "BAAI/bge-m3")
        self.assertEqual(args.limit, 50)
        self.assertEqual(args.channels, "C123,C456")
        self.assertEqual(args.oldest, "1700000000.000000")
        self.assertEqual(args.latest, "1800000000.000000")
        self.assertEqual(args.order, "oldest")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_process_embedding_jobs(self):
        parser = build_parser()
        args = parser.parse_args(
            ["mirror", "process-embedding-jobs", "--workspace", "default", "--model", "local-hash-128", "--limit", "20"]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.model, "local-hash-128")
        self.assertEqual(args.limit, 20)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_process_derived_text_jobs(self):
        parser = build_parser()
        args = parser.parse_args(
            ["mirror", "process-derived-text-jobs", "--workspace", "default", "--kind", "attachment_text", "--limit", "15"]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.kind, "attachment_text")
        self.assertEqual(args.limit, 15)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_derived_text_embeddings_backfill(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "derived-text-embeddings-backfill",
                "--workspace",
                "default",
                "--retrieval-profile",
                "local-bge",
                "--model",
                "BAAI/bge-m3",
                "--limit",
                "40",
                "--kind",
                "attachment_text",
                "--source-kind",
                "file",
                "--order",
                "oldest",
                "--json",
            ]
        )
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.retrieval_profile, "local-bge")
        self.assertEqual(args.model, "BAAI/bge-m3")
        self.assertEqual(args.limit, 40)
        self.assertEqual(args.kind, "attachment_text")
        self.assertEqual(args.source_kind, "file")
        self.assertEqual(args.order, "oldest")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_mirror_rollout_plan(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "rollout-plan",
                "--workspace",
                "default",
                "--retrieval-profile",
                "local-bge",
                "--limit",
                "25",
                "--channels",
                "C123",
                "--kind",
                "attachment_text",
                "--source-kind",
                "file",
                "--json",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.retrieval_profile, "local-bge")
        self.assertEqual(args.limit, 25)
        self.assertEqual(args.channels, "C123")
        self.assertEqual(args.kind, "attachment_text")
        self.assertEqual(args.source_kind, "file")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_mirror_reconcile_files(self):
        parser = build_parser()
        args = parser.parse_args(
            ["mirror", "reconcile-files", "--workspace", "default", "--auth-mode", "user", "--limit", "25", "--cache-root", "./cache", "--json"]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.auth_mode, "user")
        self.assertEqual(args.limit, 25)
        self.assertEqual(args.cache_root, "./cache")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_cmd_mirror_backfill_persists_reconcile_state(self):
        args = type(
            "Args",
            (),
            {
                "config": "/tmp/config.yaml",
                "workspace": "pcg",
                "auth_mode": "user",
                "include_messages": True,
                "messages_only": False,
                "channels": "",
                "channel_limit": 10,
                "oldest": None,
                "latest": None,
                "include_files": False,
                "file_types": "images",
                "download_content": False,
                "cache_root": None,
            },
        )()
        with patch("slack_mirror.cli.main._db_path_from_config", return_value="/tmp/mirror.db"), patch(
            "slack_mirror.cli.main.connect"
        ) as mock_connect, patch(
            "slack_mirror.cli.main.apply_migrations"
        ), patch(
            "slack_mirror.cli.main._workspace_config_by_name",
            return_value={"name": "pcg", "team_id": "TPCG", "user_token": "xoxp-test-token"},
        ), patch(
            "slack_mirror.cli.main.upsert_workspace",
            return_value=9,
        ), patch(
            "slack_mirror.cli.main.get_workspace_by_name",
            return_value={"id": 9},
        ), patch(
            "slack_mirror.sync.backfill.backfill_users_and_channels",
            return_value={"users": 35, "channels": 139},
        ), patch(
            "slack_mirror.sync.backfill.backfill_messages",
            return_value={"channels": 10, "messages": 9, "skipped": 0},
        ), patch(
            "slack_mirror.service.runtime_heartbeat.write_reconcile_state",
        ) as mock_write_state, patch("builtins.print") as mock_print:
            rc = cmd_mirror_backfill(args)

        self.assertEqual(rc, 0)
        mock_write_state.assert_called_once_with(
            "/tmp/config.yaml",
            workspace="pcg",
            auth_mode="user",
            result={
                "attempted": 10,
                "downloaded": 183,
                "warnings": 0,
                "failed": 0,
                "backfill_users": 35,
                "backfill_channels": 139,
                "backfill_message_channels": 10,
                "backfill_messages": 9,
                "backfill_skipped_channels": 0,
                "backfill_files": 0,
                "backfill_canvases": 0,
                "backfill_files_downloaded": 0,
                "backfill_canvases_downloaded": 0,
            },
        )
        self.assertEqual(
            mock_print.call_args[0][0],
            "Backfill complete workspace=pcg users=35 channels=139 message_channels=10 messages=9 skipped_channels=0 files=0 canvases=0 files_downloaded=0 canvases_downloaded=0",
        )

    def test_parse_user_env_snapshot_report(self):
        parser = build_parser()
        args = parser.parse_args(
            ["user-env", "snapshot-report", "--base-url", "http://slack.localhost", "--name", "ops", "--timeout", "9", "--json"]
        )
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "snapshot-report")
        self.assertEqual(args.base_url, "http://slack.localhost")
        self.assertEqual(args.name, "ops")
        self.assertEqual(args.timeout, 9.0)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_provision_frontend_user(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "user-env",
                "provision-frontend-user",
                "--username",
                "ecochran76@gmail.com",
                "--display-name",
                "Eric Cochran",
                "--password-env",
                "SLACK_MIRROR_BOOTSTRAP_PASSWORD",
                "--reset-password",
                "--json",
            ]
        )
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "provision-frontend-user")
        self.assertEqual(args.username, "ecochran76@gmail.com")
        self.assertEqual(args.display_name, "Eric Cochran")
        self.assertEqual(args.password_env, "SLACK_MIRROR_BOOTSTRAP_PASSWORD")
        self.assertTrue(args.reset_password)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_process_events(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "mirror",
                "process-events",
                "--workspace",
                "default",
                "--limit",
                "10",
                "--loop",
                "--interval",
                "0.5",
                "--max-cycles",
                "3",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.limit, 10)
        self.assertTrue(args.loop)
        self.assertEqual(args.interval, 0.5)
        self.assertEqual(args.max_cycles, 3)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_docs_generate(self):
        parser = build_parser()
        args = parser.parse_args(["docs", "generate", "--format", "man", "--output", "/tmp/slack-mirror.1"])
        self.assertEqual(args.command, "docs")
        self.assertEqual(args.format, "man")
        self.assertEqual(args.output, "/tmp/slack-mirror.1")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_api_serve_defaults_to_config_backed_values(self):
        parser = build_parser()
        args = parser.parse_args(["api", "serve"])
        self.assertEqual(args.command, "api")
        self.assertIsNone(args.bind)
        self.assertIsNone(args.port)
        self.assertTrue(hasattr(args, "func"))

    def test_cmd_serve_api_uses_config_bind_and_port_when_omitted(self):
        args = type("Args", (), {"bind": None, "port": None, "config": "/tmp/config.yaml"})
        with patch("slack_mirror.core.config.load_config") as mock_load_config, patch(
            "slack_mirror.service.api.run_api_server"
        ) as mock_run_api:
            mock_load_config.return_value = type(
                "Config",
                (),
                {"get": staticmethod(lambda key, default=None: {"service": {"bind": "127.0.0.1", "port": 8787}}.get(key, default))},
            )()

            rc = cmd_serve_api(args)

        self.assertEqual(rc, 0)
        mock_run_api.assert_called_once_with(bind="127.0.0.1", port=8787, config_path="/tmp/config.yaml")

    def test_cmd_mirror_reconcile_files_uses_user_token_and_reports_counts(self):
        args = type(
            "Args",
            (),
            {
                "config": "/tmp/config.yaml",
                "workspace": "default",
                "auth_mode": "user",
                "limit": 25,
                "cache_root": "./cache-test",
                "json": False,
            },
        )()
        with patch("slack_mirror.cli.main._db_path_from_config", return_value="/tmp/mirror.db"), patch(
            "slack_mirror.cli.main.connect"
        ) as mock_connect, patch(
            "slack_mirror.cli.main.apply_migrations"
        ), patch(
            "slack_mirror.cli.main._workspace_config_by_name",
            return_value={"name": "default", "team_id": "T123", "user_token": "xoxp-test-token"},
        ), patch(
            "slack_mirror.cli.main.upsert_workspace",
            return_value=7,
        ), patch(
            "slack_mirror.service.runtime_heartbeat.load_reconcile_state",
            return_value={
                "iso_utc": "2026-04-12T00:00:00+00:00",
                "downloaded": 18,
                "warnings": 1,
                "failed": 6,
                "attempted": 25,
                "downloaded_binary": 13,
                "materialized_email_containers": 5,
                "materialized_email_containers_with_asset_failures": 1,
            },
        ) as mock_load_state, patch(
            "slack_mirror.service.runtime_heartbeat.write_reconcile_state",
            return_value="/tmp/reconcile-files-default-user.json",
        ), patch(
            "slack_mirror.sync.backfill.reconcile_file_downloads",
            return_value={
                "scanned": 100,
                "attempted": 25,
                "downloaded": 20,
                "downloaded_binary": 14,
                "materialized_email_containers": 6,
                "materialized_email_containers_with_asset_failures": 2,
                "skipped": 70,
                "warnings": 2,
                "warning_reasons": {"email_container_inline_assets_partial": 2},
                "warning_hints": {"email_container_inline_assets_partial": "The email body was repaired but some inline assets were not downloadable; inspect the warning file rows and decide whether partial HTML is acceptable."},
                "warning_files": [],
                "failed": 5,
                "failure_hints": {},
            },
        ) as mock_reconcile, patch("builtins.print") as mock_print:
            rc = cmd_mirror_reconcile_files(args)

        self.assertEqual(rc, 0)
        mock_load_state.assert_called_once_with("/tmp/config.yaml", workspace="default", auth_mode="user")
        mock_reconcile.assert_called_once_with(
            token="xoxp-test-token",
            workspace_id=7,
            conn=mock_connect.return_value,
            cache_root="./cache-test",
            limit=25,
        )
        self.assertEqual(
            mock_print.call_args_list[0].args[0],
            "Reconcile complete workspace=default scanned=100 attempted=25 downloaded=20 downloaded_binary=14 materialized_email_containers=6 materialized_email_containers_with_asset_failures=2 warnings=2 skipped=70 failed=5",
        )
        self.assertEqual(
            mock_print.call_args_list[1].args[0],
            "Previous run: at=2026-04-12T00:00:00+00:00 downloaded=18 warnings=1 failed=6 delta_downloaded=+2 delta_warnings=+1 delta_failed=-1",
        )
        self.assertEqual(
            mock_print.call_args_list[2].args[0],
            "Warning reasons: email_container_inline_assets_partial=2",
        )
        self.assertIn("Warning hints: email_container_inline_assets_partial:", mock_print.call_args_list[3].args[0])

    def test_cmd_mirror_reconcile_files_json_reports_failure_reasons(self):
        args = type(
            "Args",
            (),
            {
                "config": "/tmp/config.yaml",
                "workspace": "default",
                "auth_mode": "user",
                "limit": 25,
                "cache_root": "./cache-test",
                "json": True,
            },
        )()
        with patch("slack_mirror.cli.main._db_path_from_config", return_value="/tmp/mirror.db"), patch(
            "slack_mirror.cli.main.connect"
        ) as mock_connect, patch(
            "slack_mirror.cli.main.apply_migrations"
        ), patch(
            "slack_mirror.cli.main._workspace_config_by_name",
            return_value={"name": "default", "team_id": "T123", "user_token": "xoxp-test-token"},
        ), patch(
            "slack_mirror.cli.main.upsert_workspace",
            return_value=7,
        ), patch(
            "slack_mirror.service.runtime_heartbeat.load_reconcile_state",
            return_value={
                "iso_utc": "2026-04-12T00:00:00+00:00",
                "downloaded": 18,
                "warnings": 1,
                "failed": 6,
                "attempted": 25,
                "downloaded_binary": 13,
                "materialized_email_containers": 5,
                "materialized_email_containers_with_asset_failures": 1,
            },
        ), patch(
            "slack_mirror.service.runtime_heartbeat.write_reconcile_state",
            return_value="/tmp/reconcile-files-default-user.json",
        ), patch(
            "slack_mirror.sync.backfill.reconcile_file_downloads",
            return_value={
                "scanned": 100,
                "attempted": 25,
                "downloaded": 20,
                "downloaded_binary": 14,
                "materialized_email_containers": 6,
                "materialized_email_containers_with_asset_failures": 2,
                "skipped": 70,
                "warnings": 2,
                "warning_reasons": {"email_container_inline_assets_partial": 2},
                "warning_hints": {"email_container_inline_assets_partial": "The email body was repaired but some inline assets were not downloadable; inspect the warning file rows and decide whether partial HTML is acceptable."},
                "warning_files": [{"file_id": "F2", "reason": "email_container_inline_assets_partial", "asset_total": 2, "asset_downloaded": 1, "asset_failed": 1}],
                "failed": 5,
                "failure_reasons": {"html_interstitial": 3, "not_found": 2},
                "failure_hints": {"html_interstitial": "Slack returned HTML instead of file bytes; verify token scopes and whether the file is actually downloadable via API."},
                "failed_files": [{"file_id": "F1", "reason": "html_interstitial", "error": "bad"}],
            },
        ), patch("builtins.print") as mock_print:
            rc = cmd_mirror_reconcile_files(args)

        self.assertEqual(rc, 0)
        printed = mock_print.call_args[0][0]
        self.assertIn('"workspace": "default"', printed)
        self.assertIn('"auth_mode": "user"', printed)
        self.assertIn('"state_path": "/tmp/reconcile-files-default-user.json"', printed)
        self.assertIn('"previous_run"', printed)
        self.assertIn('"delta_from_previous"', printed)
        self.assertIn('"warning_reasons"', printed)
        self.assertIn('"warning_hints"', printed)
        self.assertIn('"email_container_inline_assets_partial": 2', printed)
        self.assertIn('"failure_reasons"', printed)
        self.assertIn('"failure_hints"', printed)
        self.assertIn('"html_interstitial": 3', printed)

    def test_parse_search_keyword(self):
        parser = build_parser()
        args = parser.parse_args(
            ["search", "keyword", "--workspace", "default", "--query", "deploy", "--limit", "5", "--no-fts"]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.query, "deploy")
        self.assertEqual(args.limit, 5)
        self.assertTrue(args.no_fts)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_keyword_mode_semantic(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "keyword",
                "--workspace",
                "default",
                "--query",
                "deploy incident",
                "--mode",
                "semantic",
                "--model",
                "local-hash-128",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.mode, "semantic")
        self.assertEqual(args.model, "local-hash-128")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_keyword_ranking_weights(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "keyword",
                "--workspace",
                "default",
                "--query",
                "deploy",
                "--profile",
                "nylon-research",
                "--rank-term-weight",
                "6.0",
                "--rank-link-weight",
                "2.0",
                "--rank-thread-weight",
                "1.5",
                "--rank-recency-weight",
                "3.0",
                "--rerank",
                "--rerank-top-n",
                "25",
            ]
        )
        self.assertEqual(args.profile, "nylon-research")
        self.assertEqual(args.rank_term_weight, 6.0)
        self.assertEqual(args.rank_link_weight, 2.0)
        self.assertEqual(args.rank_thread_weight, 1.5)
        self.assertEqual(args.rank_recency_weight, 3.0)
        self.assertTrue(args.rerank)
        self.assertEqual(args.rerank_top_n, 25)

    def test_parse_search_semantic_alias(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "semantic",
                "--workspace",
                "default",
                "--query",
                "deploy incidents",
                "--group-by-thread",
                "--dedupe",
                "--snippet-chars",
                "200",
                "--explain",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.query, "deploy incidents")
        self.assertTrue(args.group_by_thread)
        self.assertTrue(args.dedupe)
        self.assertEqual(args.snippet_chars, 200)
        self.assertTrue(args.explain)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_query_dir(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "query-dir",
                "--path",
                "docs",
                "--query",
                "semantic search",
                "--mode",
                "hybrid",
                "--glob",
                "**/*.md",
                "--limit",
                "5",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.path, "docs")
        self.assertEqual(args.query, "semantic search")
        self.assertEqual(args.mode, "hybrid")
        self.assertEqual(args.glob, "**/*.md")
        self.assertEqual(args.limit, 5)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_derived_text(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "derived-text",
                "--workspace",
                "default",
                "--query",
                "incident review",
                "--mode",
                "semantic",
                "--model",
                "BAAI/bge-m3",
                "--kind",
                "attachment_text",
                "--source-kind",
                "canvas",
                "--limit",
                "7",
                "--json",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.query, "incident review")
        self.assertEqual(args.mode, "semantic")
        self.assertEqual(args.model, "BAAI/bge-m3")
        self.assertEqual(args.kind, "attachment_text")
        self.assertEqual(args.source_kind, "canvas")
        self.assertEqual(args.limit, 7)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_corpus(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "corpus",
                "--workspace",
                "default",
                "--query",
                "incident review",
                "--retrieval-profile",
                "local-bge-rerank",
                "--mode",
                "hybrid",
                "--kind",
                "ocr_text",
                "--source-kind",
                "file",
                "--rerank",
                "--rerank-top-n",
                "25",
                "--fusion",
                "rrf",
                "--limit",
                "8",
                "--explain",
                "--json",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.query, "incident review")
        self.assertEqual(args.retrieval_profile, "local-bge-rerank")
        self.assertEqual(args.mode, "hybrid")
        self.assertEqual(args.kind, "ocr_text")
        self.assertEqual(args.source_kind, "file")
        self.assertTrue(args.rerank)
        self.assertEqual(args.rerank_top_n, 25)
        self.assertEqual(args.fusion, "rrf")
        self.assertEqual(args.limit, 8)
        self.assertTrue(args.explain)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_corpus_all_workspaces(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "corpus",
                "--all-workspaces",
                "--query",
                "incident review",
                "--mode",
                "hybrid",
            ]
        )
        self.assertTrue(args.all_workspaces)
        self.assertIsNone(args.workspace)
        self.assertEqual(args.query, "incident review")
        self.assertEqual(args.mode, "hybrid")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_health(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "health",
                "--workspace",
                "default",
                "--dataset",
                "docs/dev/benchmarks/slack_corpus_smoke.jsonl",
                "--target",
                "derived_text",
                "--retrieval-profile",
                "local-bge",
                "--mode",
                "semantic",
                "--limit",
                "12",
                "--min-hit-at-3",
                "0.6",
                "--min-hit-at-10",
                "0.85",
                "--min-ndcg-at-k",
                "0.7",
                "--max-latency-p95-ms",
                "700",
                "--json",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.dataset, "docs/dev/benchmarks/slack_corpus_smoke.jsonl")
        self.assertEqual(args.target, "derived_text")
        self.assertEqual(args.retrieval_profile, "local-bge")
        self.assertEqual(args.mode, "semantic")
        self.assertEqual(args.limit, 12)
        self.assertEqual(args.min_hit_at_3, 0.6)
        self.assertEqual(args.min_hit_at_10, 0.85)
        self.assertEqual(args.min_ndcg_at_k, 0.7)
        self.assertEqual(args.max_latency_p95_ms, 700.0)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_profiles(self):
        parser = build_parser()
        args = parser.parse_args(["search", "profiles", "--json"])
        self.assertEqual(args.command, "search")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_semantic_readiness(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "semantic-readiness",
                "--workspace",
                "default",
                "--profiles",
                "baseline,local-bge",
                "--include-commands",
                "--command-limit",
                "25",
                "--json",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.profiles, "baseline,local-bge")
        self.assertTrue(args.include_commands)
        self.assertEqual(args.command_limit, 25)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_scale_review(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "search",
                "scale-review",
                "--workspace",
                "default",
                "--query",
                "incident review",
                "--query",
                "contract renewal",
                "--profiles",
                "baseline,local-bge",
                "--repeats",
                "2",
                "--limit",
                "5",
                "--fusion",
                "rrf",
                "--json",
            ]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.query, ["incident review", "contract renewal"])
        self.assertEqual(args.profiles, "baseline,local-bge")
        self.assertEqual(args.repeats, 2)
        self.assertEqual(args.limit, 5)
        self.assertEqual(args.fusion, "rrf")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_provider_probe(self):
        parser = build_parser()
        args = parser.parse_args(["search", "provider-probe", "--retrieval-profile", "local-bge", "--model", "BAAI/bge-m3", "--smoke", "--json"])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.retrieval_profile, "local-bge")
        self.assertEqual(args.model, "BAAI/bge-m3")
        self.assertTrue(args.smoke)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_reranker_probe(self):
        parser = build_parser()
        args = parser.parse_args(
            ["search", "reranker-probe", "--retrieval-profile", "local-bge-rerank", "--model", "BAAI/bge-reranker-v2-m3", "--smoke", "--json"]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.retrieval_profile, "local-bge-rerank")
        self.assertEqual(args.model, "BAAI/bge-reranker-v2-m3")
        self.assertTrue(args.smoke)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_search_inference_probe(self):
        parser = build_parser()
        args = parser.parse_args(
            ["search", "inference-probe", "--url", "http://127.0.0.1:8791/", "--model", "local-hash-128", "--timeout", "5", "--smoke", "--json"]
        )
        self.assertEqual(args.command, "search")
        self.assertEqual(args.url, "http://127.0.0.1:8791/")
        self.assertEqual(args.model, "local-hash-128")
        self.assertEqual(args.timeout, 5.0)
        self.assertTrue(args.smoke)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_install(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "install", "--extra", "local-semantic"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "install")
        self.assertEqual(args.extra, ["local-semantic"])
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_uninstall(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "uninstall", "--purge-data"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "uninstall")
        self.assertTrue(args.purge_data)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_rollback(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "rollback"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "rollback")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_validate_live(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "validate-live"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "validate-live")
        self.assertFalse(args.json)

    def test_parse_user_env_status_json(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "status", "--json"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "status")
        self.assertTrue(args.json)

    def test_parse_user_env_validate_live_json(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "validate-live", "--json"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "validate-live")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_version_command(self):
        parser = build_parser()
        args = parser.parse_args(["version"])
        self.assertEqual(args.command, "version")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_release_check(self):
        parser = build_parser()
        args = parser.parse_args(
            ["release", "check", "--json", "--require-clean", "--require-release-version", "--require-managed-runtime"]
        )
        self.assertEqual(args.command, "release")
        self.assertEqual(args.release_cmd, "check")
        self.assertTrue(args.json)
        self.assertTrue(args.require_clean)
        self.assertTrue(args.require_release_version)
        self.assertTrue(args.require_managed_runtime)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_api_serve(self):
        parser = build_parser()
        args = parser.parse_args(["api", "serve", "--bind", "0.0.0.0", "--port", "8788"])
        self.assertEqual(args.command, "api")
        self.assertEqual(args.api_cmd, "serve")
        self.assertEqual(args.bind, "0.0.0.0")
        self.assertEqual(args.port, 8788)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_mcp_serve(self):
        parser = build_parser()
        args = parser.parse_args(["mcp", "serve"])
        self.assertEqual(args.command, "mcp")
        self.assertEqual(args.mcp_cmd, "serve")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_check_live_json(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "check-live", "--json"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "check-live")
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_recover_live_apply_json(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "recover-live", "--apply", "--json"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "recover-live")
        self.assertTrue(args.apply)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_runtime_version_matches_pyproject_source(self):
        self.assertEqual(__version__, "0.2.0-dev")

    @patch("slack_mirror.service.user_env.install_user_env", return_value=0)
    def test_user_env_install_dispatches_to_service(self, mock_install):
        parser = build_parser()
        args = parser.parse_args(["user-env", "install", "--extra", "local-semantic"])
        self.assertEqual(cmd_user_env_install(args), 0)
        mock_install.assert_called_once_with(extras=["local-semantic"])

    @patch("slack_mirror.service.user_env.update_user_env", return_value=0)
    def test_user_env_update_dispatches_to_service(self, mock_update):
        parser = build_parser()
        args = parser.parse_args(["user-env", "update", "--extra", "local-semantic"])
        self.assertEqual(cmd_user_env_update(args), 0)
        mock_update.assert_called_once_with(extras=["local-semantic"])

    @patch("slack_mirror.service.user_env.rollback_user_env", return_value=0)
    def test_user_env_rollback_dispatches_to_service(self, mock_rollback):
        parser = build_parser()
        args = parser.parse_args(["user-env", "rollback"])
        self.assertEqual(cmd_user_env_rollback(args), 0)
        mock_rollback.assert_called_once_with()

    @patch("slack_mirror.service.user_env.uninstall_user_env", return_value=0)
    def test_user_env_uninstall_dispatches_to_service(self, mock_uninstall):
        parser = build_parser()
        args = parser.parse_args(["user-env", "uninstall", "--purge-data"])
        self.assertEqual(cmd_user_env_uninstall(args), 0)
        mock_uninstall.assert_called_once_with(purge_data=True)

    @patch("slack_mirror.service.user_env.status_user_env", return_value=0)
    def test_user_env_status_dispatches_to_service(self, mock_status):
        parser = build_parser()
        args = parser.parse_args(["user-env", "status"])
        self.assertEqual(cmd_user_env_status(args), 0)
        mock_status.assert_called_once_with(json_output=False)

    @patch("slack_mirror.service.user_env.validate_live_user_env", return_value=0)
    def test_user_env_validate_live_dispatches_to_service(self, mock_validate):
        parser = build_parser()
        args = parser.parse_args(["user-env", "validate-live"])
        self.assertEqual(cmd_user_env_validate_live(args), 0)
        mock_validate.assert_called_once_with(json_output=False)

    @patch("slack_mirror.service.user_env.status_user_env", return_value=0)
    def test_user_env_status_json_dispatches_to_service(self, mock_status):
        parser = build_parser()
        args = parser.parse_args(["user-env", "status", "--json"])
        self.assertEqual(cmd_user_env_status(args), 0)
        mock_status.assert_called_once_with(json_output=True)

    @patch("slack_mirror.service.user_env.validate_live_user_env", return_value=0)
    def test_user_env_validate_live_json_dispatches_to_service(self, mock_validate):
        parser = build_parser()
        args = parser.parse_args(["user-env", "validate-live", "--json"])
        self.assertEqual(cmd_user_env_validate_live(args), 0)
        mock_validate.assert_called_once_with(json_output=True)

    @patch("slack_mirror.service.user_env.check_live_user_env", return_value=0)
    def test_user_env_check_live_json_dispatches_to_service(self, mock_check):
        parser = build_parser()
        args = parser.parse_args(["user-env", "check-live", "--json"])
        self.assertEqual(cmd_user_env_check_live(args), 0)
        mock_check.assert_called_once_with(json_output=True)

    @patch("slack_mirror.service.user_env.recover_live_user_env", return_value=0)
    def test_user_env_recover_live_apply_json_dispatches_to_service(self, mock_recover):
        parser = build_parser()
        args = parser.parse_args(["user-env", "recover-live", "--apply", "--json"])
        self.assertEqual(cmd_user_env_recover_live(args), 0)
        mock_recover.assert_called_once_with(apply=True, json_output=True)

    @patch("slack_mirror.service.runtime_report_user_env.snapshot_runtime_report_user_env", return_value=0)
    def test_user_env_snapshot_report_dispatches_to_service(self, mock_snapshot):
        parser = build_parser()
        args = parser.parse_args(["user-env", "snapshot-report", "--base-url", "http://slack.localhost", "--name", "ops", "--timeout", "7.5", "--json"])
        self.assertEqual(cmd_user_env_snapshot_report(args), 0)
        mock_snapshot.assert_called_once_with(
            base_url="http://slack.localhost",
            name="ops",
            timeout=7.5,
            json_output=True,
        )

    @patch("slack_mirror.service.user_env.provision_frontend_user_user_env", return_value=0)
    def test_user_env_provision_frontend_user_dispatches_to_service(self, mock_provision):
        parser = build_parser()
        args = parser.parse_args(
            [
                "user-env",
                "provision-frontend-user",
                "--username",
                "ecochran76@gmail.com",
                "--display-name",
                "Eric Cochran",
                "--password-env",
                "SLACK_MIRROR_BOOTSTRAP_PASSWORD",
                "--reset-password",
                "--json",
            ]
        )
        self.assertEqual(cmd_user_env_provision_frontend_user(args), 0)
        mock_provision.assert_called_once_with(
            username="ecochran76@gmail.com",
            display_name="Eric Cochran",
            password=None,
            password_env="SLACK_MIRROR_BOOTSTRAP_PASSWORD",
            reset_password=True,
            json_output=True,
        )

    @patch("slack_mirror.service.release.release_check", return_value=0)
    def test_release_check_dispatches_to_service(self, mock_release_check):
        parser = build_parser()
        args = parser.parse_args(
            ["release", "check", "--json", "--require-clean", "--require-release-version", "--require-managed-runtime"]
        )
        self.assertEqual(cmd_release_check(args), 0)
        mock_release_check.assert_called_once_with(
            json_output=True,
            require_clean=True,
            require_release_version=True,
            require_managed_runtime=True,
        )

    @patch("slack_mirror.service.mcp.run_mcp_stdio", return_value=None)
    def test_mcp_serve_dispatches_to_service(self, mock_run):
        parser = build_parser()
        args = parser.parse_args(["mcp", "serve"])
        self.assertEqual(cmd_serve_mcp(args), 0)
        mock_run.assert_called_once_with(config_path=None)

    def test_parse_search_reindex_keyword(self):
        parser = build_parser()
        args = parser.parse_args(["search", "reindex-keyword", "--workspace", "default"])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(hasattr(args, "func"))


if __name__ == "__main__":
    unittest.main()
