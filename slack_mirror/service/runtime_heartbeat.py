from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slack_mirror.core.config import load_config


def _db_path_from_config(config_path: str | None) -> Path:
    cfg = load_config(config_path)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    return Path(str(db_path)).expanduser()


def heartbeat_dir_for_config(config_path: str | None) -> Path:
    db_path = _db_path_from_config(config_path)
    return db_path.parent / "runtime-heartbeats"


def heartbeat_path_for_config(config_path: str | None, *, workspace: str, kind: str) -> Path:
    return heartbeat_dir_for_config(config_path) / f"{kind}-{workspace}.json"


def write_heartbeat(
    config_path: str | None,
    *,
    workspace: str,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = heartbeat_path_for_config(config_path, workspace=workspace, kind=kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload: dict[str, Any] = {
        "workspace": workspace,
        "kind": kind,
        "ts": now,
        "iso_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
