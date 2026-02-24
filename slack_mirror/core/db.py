import json
import sqlite3
from pathlib import Path
from typing import Any


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    mdir = Path(migrations_dir)
    files = sorted(mdir.glob("*.sql"))
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {r[0] for r in conn.execute("SELECT name FROM _migrations")}
        for f in files:
            if f.name in applied:
                continue
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO _migrations(name) VALUES (?)", (f.name,))


def upsert_workspace(
    conn: sqlite3.Connection,
    *,
    name: str,
    team_id: str | None = None,
    domain: str | None = None,
    config: dict[str, Any] | None = None,
) -> int:
    payload = json.dumps(config or {}, sort_keys=True)
    with conn:
        conn.execute(
            """
            INSERT INTO workspaces(name, team_id, domain, config_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              team_id=excluded.team_id,
              domain=excluded.domain,
              config_json=excluded.config_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (name, team_id, domain, payload),
        )
    row = conn.execute("SELECT id FROM workspaces WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def list_workspaces(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT id, name, team_id, domain, created_at, updated_at FROM workspaces ORDER BY name"
        )
    )
