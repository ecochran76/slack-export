import unittest

from slack_mirror.cli.main import build_parser


class CliTests(unittest.TestCase):
    def test_parse_mirror_backfill(self):
        parser = build_parser()
        args = parser.parse_args(["mirror", "backfill", "--workspace", "default"])
        self.assertEqual(args.command, "mirror")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(hasattr(args, "func"))

    def test_parse_workspaces_verify(self):
        parser = build_parser()
        args = parser.parse_args(["workspaces", "verify", "--workspace", "default"])
        self.assertEqual(args.command, "workspaces")
        self.assertEqual(args.workspace, "default")
        self.assertTrue(hasattr(args, "func"))


if __name__ == "__main__":
    unittest.main()
