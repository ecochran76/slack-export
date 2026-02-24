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


def get_workspace_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, team_id, domain, config_json FROM workspaces WHERE name = ?",
        (name,),
    ).fetchone()


def upsert_user(conn: sqlite3.Connection, workspace_id: int, user: dict[str, Any]) -> None:
    profile = user.get("profile") or {}
    with conn:
        conn.execute(
            """
            INSERT INTO users(workspace_id, user_id, username, display_name, real_name, email, is_bot, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, user_id) DO UPDATE SET
              username=excluded.username,
              display_name=excluded.display_name,
              real_name=excluded.real_name,
              email=excluded.email,
              is_bot=excluded.is_bot,
              raw_json=excluded.raw_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                user.get("id"),
                user.get("name"),
                profile.get("display_name") or user.get("real_name"),
                user.get("real_name"),
                profile.get("email"),
                1 if user.get("is_bot") else 0,
                json.dumps(user, sort_keys=True),
            ),
        )


def upsert_channel(conn: sqlite3.Connection, workspace_id: int, channel: dict[str, Any]) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, channel_id) DO UPDATE SET
              name=excluded.name,
              is_private=excluded.is_private,
              is_im=excluded.is_im,
              is_mpim=excluded.is_mpim,
              topic=excluded.topic,
              purpose=excluded.purpose,
              raw_json=excluded.raw_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                channel.get("id"),
                channel.get("name") or channel.get("user") or channel.get("id"),
                1 if channel.get("is_private") else 0,
                1 if channel.get("is_im") else 0,
                1 if channel.get("is_mpim") else 0,
                (channel.get("topic") or {}).get("value"),
                (channel.get("purpose") or {}).get("value"),
                json.dumps(channel, sort_keys=True),
            ),
        )


def list_channel_ids(conn: sqlite3.Connection, workspace_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT channel_id FROM channels WHERE workspace_id = ? ORDER BY channel_id",
        (workspace_id,),
    )
    return [r["channel_id"] for r in rows]


def upsert_message(conn: sqlite3.Connection, workspace_id: int, channel_id: str, message: dict[str, Any]) -> None:
    ts = message.get("ts")
    if not ts:
        return
    edited_ts = ((message.get("edited") or {}).get("ts"))
    with conn:
        conn.execute(
            """
            INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, channel_id, ts) DO UPDATE SET
              user_id=excluded.user_id,
              text=excluded.text,
              subtype=excluded.subtype,
              thread_ts=excluded.thread_ts,
              edited_ts=excluded.edited_ts,
              deleted=excluded.deleted,
              raw_json=excluded.raw_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                channel_id,
                ts,
                message.get("user") or message.get("bot_id"),
                message.get("text"),
                message.get("subtype"),
                message.get("thread_ts"),
                edited_ts,
                1 if message.get("subtype") == "message_deleted" else 0,
                json.dumps(message, sort_keys=True),
            ),
        )


def set_sync_state(conn: sqlite3.Connection, workspace_id: int, key: str, value: str) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO sync_state(workspace_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(workspace_id, key) DO UPDATE SET
              value=excluded.value,
              updated_at=CURRENT_TIMESTAMP
            """,
            (workspace_id, key, value),
        )


def get_sync_state(conn: sqlite3.Connection, workspace_id: int, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM sync_state WHERE workspace_id = ? AND key = ?",
        (workspace_id, key),
    ).fetchone()
    return row["value"] if row else None


def upsert_file(conn: sqlite3.Connection, workspace_id: int, file_obj: dict[str, Any], local_path: str | None = None) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO files(workspace_id, file_id, name, title, mimetype, size, local_path, checksum, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, file_id) DO UPDATE SET
              name=excluded.name,
              title=excluded.title,
              mimetype=excluded.mimetype,
              size=excluded.size,
              local_path=excluded.local_path,
              checksum=excluded.checksum,
              raw_json=excluded.raw_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                file_obj.get("id"),
                file_obj.get("name"),
                file_obj.get("title"),
                file_obj.get("mimetype"),
                file_obj.get("size"),
                local_path,
                None,
                json.dumps(file_obj, sort_keys=True),
            ),
        )


def upsert_canvas(
    conn: sqlite3.Connection, workspace_id: int, canvas_obj: dict[str, Any], local_path: str | None = None
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO canvases(workspace_id, canvas_id, title, local_path, raw_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, canvas_id) DO UPDATE SET
              title=excluded.title,
              local_path=excluded.local_path,
              raw_json=excluded.raw_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                canvas_obj.get("id"),
                canvas_obj.get("title"),
                local_path,
                json.dumps(canvas_obj, sort_keys=True),
            ),
        )
