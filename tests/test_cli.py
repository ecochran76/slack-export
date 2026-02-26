import unittest

from slack_mirror.cli.main import build_parser


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

    def test_parse_search_reindex_keyword(self):
        parser = build_parser()
        args = parser.parse_args(["search", "reindex-keyword", "--workspace", "default"])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(hasattr(args, "func"))


if __name__ == "__main__":
    unittest.main()
