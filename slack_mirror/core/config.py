import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")
_DEFAULT_CONFIG_CANDIDATES = (
    Path("config.local.yaml"),
    Path("config.yaml"),
    Path("~/.config/slack-mirror/config.yaml").expanduser(),
)


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
    path: Path

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def default_config_candidates(cwd: Path | None = None) -> list[Path]:
    base = cwd or Path.cwd()
    out: list[Path] = []
    for candidate in _DEFAULT_CONFIG_CANDIDATES:
        p = candidate.expanduser()
        if not p.is_absolute():
            p = (base / p).resolve()
        out.append(p)
    return out


def resolve_config_path(path: str | Path | None = None, *, cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()

    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = (base / candidate).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Config not found: {candidate}")
        return candidate.resolve()

    env_path = os.getenv("SLACK_MIRROR_CONFIG", "").strip()
    if env_path:
        return resolve_config_path(env_path, cwd=base)

    candidates = default_config_candidates(base)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    looked = "\n  - ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        "Config not found. Provide --config, set SLACK_MIRROR_CONFIG, or create one of:\n"
        f"  - {looked}"
    )


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


def _resolve_pathish(value: Any, *, base_dir: Path) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return str(p)


def _normalize_paths(raw: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    data = dict(raw)
    base_dir = config_path.parent.resolve()

    if isinstance(data.get("dotenv"), str):
        data["dotenv"] = _resolve_pathish(data["dotenv"], base_dir=base_dir)

    storage = data.get("storage")
    if isinstance(storage, dict):
        storage = dict(storage)
        for key in ("db_path", "cache_root"):
            if key in storage:
                storage[key] = _resolve_pathish(storage.get(key), base_dir=base_dir)
        data["storage"] = storage

    return data


def _resolve_dotenv_path(dotenv: Any, *, config_path: Path) -> Path | None:
    if not dotenv:
        return None
    expanded = _expand_env(dotenv)
    dotenv_path = Path(str(expanded)).expanduser()
    if not dotenv_path.is_absolute():
        dotenv_path = (config_path.parent / dotenv_path).resolve()
    return dotenv_path


def load_config(path: str | Path | None = None) -> Config:
    resolved_path = resolve_config_path(path)
    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}

    dotenv_path = _resolve_dotenv_path(raw.get("dotenv"), config_path=resolved_path)
    if dotenv_path is not None:
        _load_dotenv(dotenv_path)

    expanded = _expand_env(raw)
    normalized = _normalize_paths(expanded, config_path=resolved_path)
    return Config(data=normalized, path=resolved_path)
