import tempfile
import unittest
from pathlib import Path

from slack_mirror.service.app import get_app_service


class FrontendAuthTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.config_path = self.root / "config.yaml"
        self.db_path = self.root / "data" / "mirror.db"
        self.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {self.db_path}",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure: false",
                    "    session_days: 30",
                    "workspaces:",
                    "  - name: default",
                    "    team_id: T123",
                    "    token: xoxb-test-token",
                    "    user_token: xoxp-test-token",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.service = get_app_service(str(self.config_path))
        self.conn = self.service.connect()

    def test_register_login_resolve_and_logout_frontend_auth(self):
        status = self.service.frontend_auth_status(self.conn)
        self.assertTrue(status["enabled"])
        self.assertTrue(status["registration_open"])
        self.assertEqual(status["user_count"], 0)

        issued = self.service.register_frontend_user(
            self.conn,
            username="Eric",
            password="correct-horse-123",
            display_name="Eric",
        )
        self.assertTrue(issued.payload.authenticated)
        self.assertEqual(issued.payload.username, "eric")

        resolved = self.service.frontend_auth_session(self.conn, session_token=issued.session_token)
        self.assertTrue(resolved.authenticated)
        self.assertEqual(resolved.username, "eric")
        self.assertEqual(resolved.display_name, "Eric")

        self.service.logout_frontend_user(self.conn, session_token=issued.session_token)
        revoked = self.service.frontend_auth_session(self.conn, session_token=issued.session_token)
        self.assertFalse(revoked.authenticated)

        relogin = self.service.login_frontend_user(
            self.conn,
            username="eric",
            password="correct-horse-123",
        )
        self.assertTrue(relogin.payload.authenticated)
        self.assertEqual(relogin.payload.username, "eric")

    def test_login_rejects_bad_password(self):
        self.service.register_frontend_user(
            self.conn,
            username="Eric",
            password="correct-horse-123",
            display_name="Eric",
        )
        with self.assertRaisesRegex(ValueError, "invalid username or password"):
            self.service.login_frontend_user(
                self.conn,
                username="eric",
                password="wrong-horse-123",
            )

    def test_provision_frontend_user_creates_user_without_registration_flow(self):
        provisioned = self.service.provision_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="correct-horse-123",
            display_name="Eric Cochran",
        )
        self.assertTrue(provisioned.created)
        self.assertTrue(provisioned.password_updated)
        self.assertEqual(provisioned.username, "ecochran76@gmail.com")
        login = self.service.login_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="correct-horse-123",
        )
        self.assertTrue(login.payload.authenticated)
        self.assertEqual(login.payload.display_name, "Eric Cochran")

    def test_provision_frontend_user_requires_reset_for_existing_user(self):
        self.service.provision_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="correct-horse-123",
            display_name="Eric Cochran",
        )
        with self.assertRaisesRegex(ValueError, "reset_password"):
            self.service.provision_frontend_user(
                self.conn,
                username="ecochran76@gmail.com",
                password="new-password-123",
            )

    def test_provision_frontend_user_can_reset_existing_password(self):
        self.service.provision_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="correct-horse-123",
            display_name="Eric Cochran",
        )
        provisioned = self.service.provision_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="new-password-123",
            display_name="E. Cochran",
            reset_password=True,
        )
        self.assertFalse(provisioned.created)
        self.assertTrue(provisioned.password_updated)
        self.assertEqual(provisioned.display_name, "E. Cochran")
        with self.assertRaisesRegex(ValueError, "invalid username or password"):
            self.service.login_frontend_user(
                self.conn,
                username="ecochran76@gmail.com",
                password="correct-horse-123",
            )
        login = self.service.login_frontend_user(
            self.conn,
            username="ecochran76@gmail.com",
            password="new-password-123",
        )
        self.assertTrue(login.payload.authenticated)
        self.assertEqual(login.payload.display_name, "E. Cochran")


if __name__ == "__main__":
    unittest.main()
