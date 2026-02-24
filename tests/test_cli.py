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
                "--include-messages",
                "--channel-limit",
                "3",
                "--include-files",
                "--download-content",
                "--cache-root",
                "./cache-test",
            ]
        )
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(args.include_messages)
        self.assertEqual(args.channel_limit, 3)
        self.assertTrue(args.include_files)
        self.assertTrue(args.download_content)
        self.assertEqual(args.cache_root, "./cache-test")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_workspaces_verify(self):
        parser = build_parser()
        args = parser.parse_args(["workspaces", "verify", "--workspace", "default"])
        self.assertEqual(args.command, "workspaces")
        self.assertEqual(args.workspace, "default")
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

    def test_parse_process_events(self):
        parser = build_parser()
        args = parser.parse_args(["mirror", "process-events", "--workspace", "default", "--limit", "10"])
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertEqual(args.limit, 10)
        self.assertTrue(hasattr(args, "func"))


if __name__ == "__main__":
    unittest.main()
