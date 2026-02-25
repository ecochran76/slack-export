import unittest

from slack_mirror.cli.main import _detect_token_mode, _enforce_auth_mode


class AuthModeGuardrailTests(unittest.TestCase):
    def test_detect_token_mode(self):
        self.assertEqual(_detect_token_mode("xoxb-abc"), "bot")
        self.assertEqual(_detect_token_mode("xoxp-abc"), "user")
        self.assertEqual(_detect_token_mode("xapp-abc"), "unknown")

    def test_enforce_bot_mode_rejects_user_token(self):
        with self.assertRaises(ValueError):
            _enforce_auth_mode("xoxp-abc", "bot", command_name="mirror backfill")

    def test_enforce_user_mode_rejects_bot_token(self):
        with self.assertRaises(ValueError):
            _enforce_auth_mode("xoxb-abc", "user", command_name="mirror backfill")

    def test_enforce_matching_modes(self):
        _enforce_auth_mode("xoxb-abc", "bot", command_name="mirror backfill")
        _enforce_auth_mode("xoxp-abc", "user", command_name="mirror backfill")


if __name__ == "__main__":
    unittest.main()
