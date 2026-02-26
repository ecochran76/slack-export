import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        raise FileNotFoundError(f"dotenv file not found: {dotenv_path}")

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key:
            os.environ[key] = value


@dataclass
class Config:
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            var = match.group(1)
            fallback = match.group(2)
            return os.getenv(var, fallback if fallback is not None else "")

        return _ENV_PATTERN.sub(repl, value)
    return value


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    dotenv = raw.get("dotenv")
    if dotenv:
        dotenv_path = Path(str(dotenv)).expanduser()
        if not dotenv_path.is_absolute():
            dotenv_path = (path.parent / dotenv_path).resolve()
        _load_dotenv(dotenv_path)

    return Config(data=_expand_env(raw))
