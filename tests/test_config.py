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


if __name__ == "__main__":
    unittest.main()
