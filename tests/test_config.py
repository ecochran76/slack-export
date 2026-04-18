import os
import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.config import load_config, resolve_config_path


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

    def test_dotenv_path_env_default_is_resolved_before_loading(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            env_file = td_path / "default.env"
            env_file.write_text("SLACK_TEST_TOKEN_FROM_DOTENV=xoxb-default\n", encoding="utf-8")
            os.environ.pop("SLACK_TEST_TOKEN_FROM_DOTENV", None)
            os.environ.pop("SLACK_TEST_DOTENV_PATH", None)

            p = td_path / "config.yaml"
            p.write_text(
                "dotenv: ${SLACK_TEST_DOTENV_PATH:-./default.env}\n"
                "workspaces:\n"
                "  - name: soylei\n"
                "    token: ${SLACK_TEST_TOKEN_FROM_DOTENV:-}\n",
                encoding="utf-8",
            )
            cfg = load_config(p)
            self.assertEqual(cfg.get("workspaces")[0]["token"], "xoxb-default")

    def test_storage_paths_resolve_relative_to_config_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cfg_dir = td_path / "configs"
            cfg_dir.mkdir(parents=True)
            p = cfg_dir / "config.yaml"
            p.write_text(
                "storage:\n  db_path: ./state/test.db\n  cache_root: ./cache\n",
                encoding="utf-8",
            )

            old_cwd = Path.cwd()
            os.chdir("/")
            try:
                cfg = load_config(p)
            finally:
                os.chdir(old_cwd)

            self.assertEqual(cfg.get("storage")["db_path"], str((cfg_dir / "state" / "test.db").resolve()))
            self.assertEqual(cfg.get("storage")["cache_root"], str((cfg_dir / "cache").resolve()))

    def test_config_discovery_prefers_repo_local_then_user_scope(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            repo_cfg = td_path / "config.local.yaml"
            repo_cfg.write_text("version: 1\n", encoding="utf-8")

            old_cwd = Path.cwd()
            env_backup = os.environ.get("SLACK_MIRROR_CONFIG")
            os.environ.pop("SLACK_MIRROR_CONFIG", None)
            os.chdir(td_path)
            try:
                resolved = resolve_config_path(None)
            finally:
                os.chdir(old_cwd)
                if env_backup is None:
                    os.environ.pop("SLACK_MIRROR_CONFIG", None)
                else:
                    os.environ["SLACK_MIRROR_CONFIG"] = env_backup

            self.assertEqual(resolved, repo_cfg.resolve())


if __name__ == "__main__":
    unittest.main()
