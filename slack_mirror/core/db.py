import json
import sqlite3
from array import array
from hashlib import sha256
from pathlib import Path
from typing import Any


def connect(
    db_path: str,
    *,
    check_same_thread: bool = True,
    timeout_seconds: float = 10.0,
) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=timeout_seconds)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={int(timeout_seconds * 1000)}")
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


def upsert_channel_member(conn: sqlite3.Connection, workspace_id: int, channel_id: str, user_id: str) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO channel_members(workspace_id, channel_id, user_id)
            VALUES (?, ?, ?)
            ON CONFLICT(workspace_id, channel_id, user_id) DO UPDATE SET
              updated_at=CURRENT_TIMESTAMP
            """,
            (workspace_id, channel_id, user_id),
        )


def remove_channel_member(conn: sqlite3.Connection, workspace_id: int, channel_id: str, user_id: str) -> None:
    with conn:
        conn.execute(
            """
            DELETE FROM channel_members
            WHERE workspace_id = ? AND channel_id = ? AND user_id = ?
            """,
            (workspace_id, channel_id, user_id),
        )


def list_channel_ids(conn: sqlite3.Connection, workspace_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT channel_id FROM channels WHERE workspace_id = ? ORDER BY channel_id",
        (workspace_id,),
    )
    return [r["channel_id"] for r in rows]


def list_recent_thread_roots(
    conn: sqlite3.Connection,
    workspace_id: int,
    channel_id: str,
    *,
    min_ts: str,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT ts
        FROM messages
        WHERE workspace_id = ?
          AND channel_id = ?
          AND thread_ts = ts
          AND deleted = 0
          AND CAST(ts AS REAL) >= CAST(? AS REAL)
        ORDER BY CAST(ts AS REAL) DESC
        """,
        (workspace_id, channel_id, min_ts),
    )
    return [str(r["ts"]) for r in rows]


def enqueue_embedding_job(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    channel_id: str,
    ts: str,
    reason: str = "upsert",
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO embedding_jobs(workspace_id, channel_id, ts, reason, status)
            VALUES (?, ?, ?, ?, 'pending')
            ON CONFLICT(workspace_id, channel_id, ts) DO UPDATE SET
              reason=excluded.reason,
              status='pending',
              error=NULL,
              updated_at=CURRENT_TIMESTAMP
            """,
            (workspace_id, channel_id, ts, reason),
        )


def list_pending_embedding_jobs(conn: sqlite3.Connection, workspace_id: int, limit: int = 100) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, workspace_id, channel_id, ts, reason, status, error, created_at, updated_at
            FROM embedding_jobs
            WHERE workspace_id = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (workspace_id, limit),
        )
    )


def mark_embedding_job_status(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    status: str,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE embedding_jobs
            SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error, job_id),
        )


def enqueue_derived_text_job(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    source_kind: str,
    source_id: str,
    derivation_kind: str = "attachment_text",
    reason: str = "upsert",
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO derived_text_jobs(workspace_id, source_kind, source_id, derivation_kind, reason, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(workspace_id, source_kind, source_id, derivation_kind) DO UPDATE SET
              reason=excluded.reason,
              status='pending',
              error=NULL,
              updated_at=CURRENT_TIMESTAMP
            """,
            (workspace_id, source_kind, source_id, derivation_kind, reason),
        )


def list_pending_derived_text_jobs(
    conn: sqlite3.Connection,
    workspace_id: int,
    *,
    derivation_kind: str = "attachment_text",
    limit: int = 100,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, workspace_id, source_kind, source_id, derivation_kind, reason, status, error, created_at, updated_at
            FROM derived_text_jobs
            WHERE workspace_id = ? AND derivation_kind = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (workspace_id, derivation_kind, limit),
        )
    )


def mark_derived_text_job_status(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    status: str,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE derived_text_jobs
            SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error, job_id),
        )


def upsert_derived_text(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    source_kind: str,
    source_id: str,
    derivation_kind: str,
    extractor: str,
    text: str,
    media_type: str | None = None,
    local_path: str | None = None,
    language_code: str | None = None,
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    normalized_text = (text or "").strip()
    if not normalized_text:
        raise ValueError("derived text must not be empty")
    content_hash = sha256(normalized_text.encode("utf-8")).hexdigest()
    payload = json.dumps(metadata or {}, sort_keys=True)

    with conn:
        conn.execute(
            """
            INSERT INTO derived_text(
              workspace_id, source_kind, source_id, derivation_kind, extractor, text, content_hash,
              media_type, local_path, language_code, confidence, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, source_kind, source_id, derivation_kind, extractor) DO UPDATE SET
              text=excluded.text,
              content_hash=excluded.content_hash,
              media_type=excluded.media_type,
              local_path=excluded.local_path,
              language_code=excluded.language_code,
              confidence=excluded.confidence,
              metadata_json=excluded.metadata_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                source_kind,
                source_id,
                derivation_kind,
                extractor,
                normalized_text,
                content_hash,
                media_type,
                local_path,
                language_code,
                confidence,
                payload,
            ),
        )
        conn.execute(
            """
            DELETE FROM derived_text_fts
            WHERE workspace_id = ?
              AND source_kind = ?
              AND source_id = ?
              AND derivation_kind = ?
              AND extractor = ?
            """,
            (workspace_id, source_kind, source_id, derivation_kind, extractor),
        )
        conn.execute(
            """
            INSERT INTO derived_text_fts(workspace_id, source_kind, source_id, derivation_kind, extractor, text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workspace_id, source_kind, source_id, derivation_kind, extractor, normalized_text),
        )


def get_derived_text(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    source_kind: str,
    source_id: str,
    derivation_kind: str,
    extractor: str | None = None,
) -> dict[str, Any] | None:
    sql = """
        SELECT
          id, workspace_id, source_kind, source_id, derivation_kind, extractor, text, content_hash,
          media_type, local_path, language_code, confidence, metadata_json, created_at, updated_at
        FROM derived_text
        WHERE workspace_id = ? AND source_kind = ? AND source_id = ? AND derivation_kind = ?
    """
    params: list[Any] = [workspace_id, source_kind, source_id, derivation_kind]
    if extractor is not None:
        sql += " AND extractor = ?"
        params.append(extractor)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    out = dict(row)
    out["metadata"] = json.loads(out.get("metadata_json") or "{}")
    return out


def upsert_message(conn: sqlite3.Connection, workspace_id: int, channel_id: str, message: dict[str, Any]) -> None:
    ts = message.get("ts")
    if not ts:
        return
    user_id = message.get("user") or message.get("bot_id") or ""
    text = message.get("text") or ""
    edited_ts = ((message.get("edited") or {}).get("ts"))
    deleted = 1 if message.get("subtype") == "message_deleted" else 0
    raw_json = json.dumps(message, sort_keys=True)
    existing = conn.execute(
        """
        SELECT user_id, text, subtype, thread_ts, edited_ts, deleted
        FROM messages
        WHERE workspace_id = ? AND channel_id = ? AND ts = ?
        """,
        (workspace_id, channel_id, ts),
    ).fetchone()
    unchanged = bool(
        existing
        and (existing["user_id"] or "") == user_id
        and (existing["text"] or "") == text
        and existing["subtype"] == message.get("subtype")
        and existing["thread_ts"] == message.get("thread_ts")
        and existing["edited_ts"] == edited_ts
        and int(existing["deleted"] or 0) == deleted
    )

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
                user_id,
                text,
                message.get("subtype"),
                message.get("thread_ts"),
                edited_ts,
                deleted,
                raw_json,
            ),
        )

        if unchanged:
            return

        # Incremental FTS maintenance for keyword search speed.
        conn.execute(
            """
            DELETE FROM messages_fts
            WHERE workspace_id = ? AND channel_id = ? AND ts = ?
            """,
            (workspace_id, channel_id, ts),
        )
        if not deleted:
            conn.execute(
                """
                INSERT INTO messages_fts(workspace_id, channel_id, user_id, ts, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, channel_id, user_id, ts, text),
            )
            conn.execute(
                """
                INSERT INTO embedding_jobs(workspace_id, channel_id, ts, reason, status)
                VALUES (?, ?, ?, 'upsert', 'pending')
                ON CONFLICT(workspace_id, channel_id, ts) DO UPDATE SET
                  reason='upsert',
                  status='pending',
                  error=NULL,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (workspace_id, channel_id, ts),
            )
        else:
            conn.execute(
                """
                UPDATE embedding_jobs
                SET status='skipped', error='message_deleted', updated_at=CURRENT_TIMESTAMP
                WHERE workspace_id = ? AND channel_id = ? AND ts = ?
                """,
                (workspace_id, channel_id, ts),
            )


def upsert_message_embedding(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    channel_id: str,
    ts: str,
    model_id: str,
    embedding: list[float],
    content_hash: str,
) -> None:
    if not embedding:
        raise ValueError("embedding must not be empty")
    vec = array("f", embedding)
    dim = len(vec)
    payload = vec.tobytes()

    with conn:
        conn.execute(
            """
            INSERT INTO message_embeddings(
              workspace_id, channel_id, ts, model_id, dim, embedding_blob, content_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, channel_id, ts, model_id) DO UPDATE SET
              dim=excluded.dim,
              embedding_blob=excluded.embedding_blob,
              content_hash=excluded.content_hash,
              embedded_at=CURRENT_TIMESTAMP
            """,
            (workspace_id, channel_id, ts, model_id, dim, payload, content_hash),
        )


def get_message_embedding(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    channel_id: str,
    ts: str,
    model_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT workspace_id, channel_id, ts, model_id, dim, embedding_blob, content_hash, embedded_at
        FROM message_embeddings
        WHERE workspace_id = ? AND channel_id = ? AND ts = ? AND model_id = ?
        """,
        (workspace_id, channel_id, ts, model_id),
    ).fetchone()
    if not row:
        return None

    out = dict(row)
    vec = array("f")
    vec.frombytes(out["embedding_blob"])
    out["embedding"] = vec.tolist()
    return out


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
    if local_path:
        enqueue_derived_text_job(
            conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id=str(file_obj.get("id") or ""),
            derivation_kind="attachment_text",
            reason="file_upsert",
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
    if local_path:
        enqueue_derived_text_job(
            conn,
            workspace_id=workspace_id,
            source_kind="canvas",
            source_id=str(canvas_obj.get("id") or ""),
            derivation_kind="attachment_text",
            reason="canvas_upsert",
        )


def update_file_download(
    conn: sqlite3.Connection, workspace_id: int, file_id: str, local_path: str, checksum: str
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE files
            SET local_path = ?, checksum = ?, updated_at = CURRENT_TIMESTAMP
            WHERE workspace_id = ? AND file_id = ?
            """,
            (local_path, checksum, workspace_id, file_id),
        )
    enqueue_derived_text_job(
        conn,
        workspace_id=workspace_id,
        source_kind="file",
        source_id=file_id,
        derivation_kind="attachment_text",
        reason="file_download",
    )


def insert_event(
    conn: sqlite3.Connection,
    workspace_id: int,
    event_id: str,
    event_ts: str | None,
    event_type: str | None,
    payload: dict[str, Any],
    status: str = "pending",
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO events(workspace_id, event_id, event_ts, type, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, event_id) DO UPDATE SET
              event_ts=excluded.event_ts,
              type=excluded.type,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                workspace_id,
                event_id,
                event_ts,
                event_type,
                status,
                json.dumps(payload, sort_keys=True),
            ),
        )


def mark_event_status(
    conn: sqlite3.Connection,
    workspace_id: int,
    event_id: str,
    status: str,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE events
            SET status = ?, error = ?, processed_at = CURRENT_TIMESTAMP
            WHERE workspace_id = ? AND event_id = ?
            """,
            (status, error, workspace_id, event_id),
        )
