import os
import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.config import load_config


class ConfigTests(unittest.TestCase):
    def test_env_interpolation_with_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.yaml"
            p.write_text("value: ${MISSING_VAR:-fallback}\n", encoding="utf-8")
            cfg = load_config(p)
            self.assertEqual(cfg.get("value"), "fallback")

    def test_env_interpolation_with_real_env(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.yaml"
            p.write_text("value: ${REAL_VAR}\n", encoding="utf-8")
            os.environ["REAL_VAR"] = "hello"
            cfg = load_config(p)
            self.assertEqual(cfg.get("value"), "hello")

    def test_dotenv_is_loaded_before_interpolation(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            env_file = td_path / "test.env"
            env_file.write_text("SLACK_TEST_TOKEN_FROM_DOTENV=xoxb-test\n", encoding="utf-8")
            os.environ.pop("SLACK_TEST_TOKEN_FROM_DOTENV", None)

            p = td_path / "config.yaml"
            p.write_text(
                "dotenv: ./test.env\nworkspaces:\n  - name: soylei\n    token: ${SLACK_TEST_TOKEN_FROM_DOTENV:-}\n",
                encoding="utf-8",
            )
            cfg = load_config(p)
            self.assertEqual(cfg.get("workspaces")[0]["token"], "xoxb-test")


if __name__ == "__main__":
    unittest.main()
