import unittest
from urllib.parse import parse_qs, urlparse

from slack_mirror.service.oauth import build_install_url


class OAuthTests(unittest.TestCase):
    def test_build_install_url_includes_redirect_and_state(self):
        url = build_install_url(
            client_id="123.456",
            redirect_uri="https://localhost:3000/slack/oauth/callback",
            scopes=["chat:write", "channels:history"],
            user_scopes=["channels:history"],
            state="abc123",
        )
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "slack.com")
        self.assertEqual(parsed.path, "/oauth/v2/authorize")

        q = parse_qs(parsed.query)
        self.assertEqual(q.get("client_id", [""])[0], "123.456")
        self.assertEqual(
            q.get("redirect_uri", [""])[0],
            "https://localhost:3000/slack/oauth/callback",
        )
        self.assertEqual(q.get("scope", [""])[0], "chat:write,channels:history")
        self.assertEqual(q.get("user_scope", [""])[0], "channels:history")
        self.assertEqual(q.get("state", [""])[0], "abc123")


if __name__ == "__main__":
    unittest.main()
