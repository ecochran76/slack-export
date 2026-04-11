import unittest
from unittest.mock import patch

from slack_mirror import __version__
from slack_mirror.cli.main import (
    build_parser,
    cmd_release_check,
    cmd_serve_mcp,
    cmd_user_env_check_live,
    cmd_user_env_install,
    cmd_user_env_rollback,
    cmd_user_env_recover_live,
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
            ["mirror", "embeddings-backfill", "--workspace", "default", "--model", "local-hash-128", "--limit", "50"]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.model, "local-hash-128")
        self.assertEqual(args.limit, 50)
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
        self.assertEqual(args.kind, "attachment_text")
        self.assertEqual(args.source_kind, "canvas")
        self.assertEqual(args.limit, 7)
        self.assertTrue(args.json)
        self.assertTrue(hasattr(args, "func"))

    def test_parse_user_env_install(self):
        parser = build_parser()
        args = parser.parse_args(["user-env", "install"])
        self.assertEqual(args.command, "user-env")
        self.assertEqual(args.user_env_cmd, "install")
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
        args = parser.parse_args(["release", "check", "--json", "--require-clean", "--require-release-version"])
        self.assertEqual(args.command, "release")
        self.assertEqual(args.release_cmd, "check")
        self.assertTrue(args.json)
        self.assertTrue(args.require_clean)
        self.assertTrue(args.require_release_version)
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
        args = parser.parse_args(["user-env", "install"])
        self.assertEqual(cmd_user_env_install(args), 0)
        mock_install.assert_called_once_with()

    @patch("slack_mirror.service.user_env.update_user_env", return_value=0)
    def test_user_env_update_dispatches_to_service(self, mock_update):
        parser = build_parser()
        args = parser.parse_args(["user-env", "update"])
        self.assertEqual(cmd_user_env_update(args), 0)
        mock_update.assert_called_once_with()

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

    @patch("slack_mirror.service.release.release_check", return_value=0)
    def test_release_check_dispatches_to_service(self, mock_release_check):
        parser = build_parser()
        args = parser.parse_args(["release", "check", "--json", "--require-clean", "--require-release-version"])
        self.assertEqual(cmd_release_check(args), 0)
        mock_release_check.assert_called_once_with(
            json_output=True,
            require_clean=True,
            require_release_version=True,
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
