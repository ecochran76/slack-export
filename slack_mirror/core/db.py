import json
import sqlite3
from array import array
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

_OCR_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

_DERIVED_TEXT_CHUNK_TARGET_CHARS = 900
_DERIVED_TEXT_CHUNK_OVERLAP_CHARS = 120


def _split_long_segment(segment: str, *, start_offset: int, max_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    seg = segment.strip()
    if not seg:
        return parts

    cursor = 0
    while cursor < len(seg):
        remaining = seg[cursor:]
        if len(remaining) <= max_chars:
            chunk_text = remaining.strip()
            if chunk_text:
                local_start = remaining.find(chunk_text)
                chunk_start = start_offset + cursor + max(local_start, 0)
                parts.append(
                    {
                        "start_offset": chunk_start,
                        "end_offset": chunk_start + len(chunk_text),
                        "text": chunk_text,
                    }
                )
            break

        window = remaining[:max_chars]
        cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("! "), window.rfind("? "), window.rfind(" "))
        if cut < max_chars // 2:
            cut = max_chars
        chunk_text = remaining[:cut].strip()
        if not chunk_text:
            break
        local_start = remaining.find(chunk_text)
        chunk_start = start_offset + cursor + max(local_start, 0)
        parts.append(
            {
                "start_offset": chunk_start,
                "end_offset": chunk_start + len(chunk_text),
                "text": chunk_text,
            }
        )
        advance = max(len(chunk_text) - overlap_chars, 1)
        cursor += advance
    return parts


def _chunk_derived_text(
    text: str,
    *,
    max_chars: int = _DERIVED_TEXT_CHUNK_TARGET_CHARS,
    overlap_chars: int = _DERIVED_TEXT_CHUNK_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [
            {
                "start_offset": 0,
                "end_offset": len(normalized),
                "text": normalized,
                "content_hash": sha256(normalized.encode("utf-8")).hexdigest(),
            }
        ]

    chunks: list[dict[str, Any]] = []
    matches = list(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|$)", normalized, flags=re.DOTALL))
    if matches:
        current = ""
        current_start = 0
        for match in matches:
            segment = match.group(0).strip()
            if not segment:
                continue
            segment_start = match.start()
            candidate = segment if not current else f"{current}\n\n{segment}"
            if current and len(candidate) > max_chars:
                chunks.extend(
                    _split_long_segment(
                        current,
                        start_offset=current_start,
                        max_chars=max_chars,
                        overlap_chars=overlap_chars,
                    )
                )
                current = segment
                current_start = segment_start
            elif len(segment) > max_chars:
                if current:
                    chunks.extend(
                        _split_long_segment(
                            current,
                            start_offset=current_start,
                            max_chars=max_chars,
                            overlap_chars=overlap_chars,
                        )
                    )
                    current = ""
                chunks.extend(
                    _split_long_segment(
                        segment,
                        start_offset=segment_start,
                        max_chars=max_chars,
                        overlap_chars=overlap_chars,
                    )
                )
            else:
                if not current:
                    current_start = segment_start
                current = candidate
        if current:
            chunks.extend(
                _split_long_segment(
                    current,
                    start_offset=current_start,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
    else:
        chunks.extend(
            _split_long_segment(
                normalized,
                start_offset=0,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
        )

    out: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_text = str(chunk.get("text") or "").strip()
        if not chunk_text:
            continue
        out.append(
            {
                "start_offset": int(chunk["start_offset"]),
                "end_offset": int(chunk["end_offset"]),
                "text": chunk_text,
                "content_hash": sha256(chunk_text.encode("utf-8")).hexdigest(),
            }
        )
    return out or [{"start_offset": 0, "end_offset": len(normalized), "text": normalized, "content_hash": sha256(normalized.encode("utf-8")).hexdigest()}]


def _should_enqueue_file_ocr(*, mimetype: str | None, local_path: str | None) -> bool:
    media_type = str(mimetype or "").strip().lower()
    suffix = Path(str(local_path or "")).suffix.lower()
    return media_type.startswith("image/") or media_type == "application/pdf" or suffix in _OCR_IMAGE_SUFFIXES or suffix == ".pdf"


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


def normalize_auth_username(username: str) -> str:
    normalized = re.sub(r"[^a-z0-9@._+-]+", "-", str(username or "").strip().casefold()).strip("-.@+")
    return normalized


def count_auth_users(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM auth_users").fetchone()
    return int(row["count"]) if row else 0


def get_auth_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    normalized = normalize_auth_username(username)
    return conn.execute(
        """
        SELECT id, username, display_name, created_at, updated_at
        FROM auth_users
        WHERE username = ?
        """,
        (normalized,),
    ).fetchone()


def get_auth_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, username, display_name, created_at, updated_at
        FROM auth_users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def create_auth_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    display_name: str | None = None,
) -> sqlite3.Row:
    normalized = normalize_auth_username(username)
    if not normalized:
        raise ValueError("username is required")
    with conn:
        conn.execute(
            """
            INSERT INTO auth_users(username, display_name)
            VALUES (?, ?)
            """,
            (normalized, (display_name or "").strip() or None),
        )
    row = get_auth_user_by_username(conn, normalized)
    if row is None:
        raise RuntimeError("failed to create auth user")
    return row


def update_auth_user_display_name(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    display_name: str | None,
) -> sqlite3.Row | None:
    cleaned_display_name = (display_name or "").strip() or None
    with conn:
        conn.execute(
            """
            UPDATE auth_users
            SET display_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (cleaned_display_name, int(user_id)),
        )
    return get_auth_user_by_id(conn, int(user_id))


def get_auth_local_credential(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT user_id, password_hash, password_salt, password_iterations, created_at, updated_at
        FROM auth_local_credentials
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()


def upsert_auth_local_credential(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    password_hash: str,
    password_salt: str,
    password_iterations: int,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO auth_local_credentials(user_id, password_hash, password_salt, password_iterations)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              password_hash=excluded.password_hash,
              password_salt=excluded.password_salt,
              password_iterations=excluded.password_iterations,
              updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, password_hash, password_salt, int(password_iterations)),
        )


def create_auth_session(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    token_hash: str,
    auth_source: str,
    expires_at: str,
) -> sqlite3.Row:
    with conn:
        conn.execute(
            """
            INSERT INTO auth_sessions(user_id, token_hash, auth_source, last_seen_at, expires_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (user_id, token_hash, auth_source, expires_at),
        )
    row = conn.execute(
        """
        SELECT id, user_id, token_hash, auth_source, created_at, last_seen_at, expires_at, revoked_at
        FROM auth_sessions
        WHERE token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to create auth session")
    return row


def get_auth_session_by_token_hash(conn: sqlite3.Connection, token_hash: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
          s.id,
          s.user_id,
          s.token_hash,
          s.auth_source,
          s.created_at,
          s.last_seen_at,
          s.expires_at,
          s.revoked_at,
          u.username,
          u.display_name
        FROM auth_sessions s
        JOIN auth_users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()


def touch_auth_session(conn: sqlite3.Connection, *, token_hash: str) -> None:
    with conn:
        conn.execute(
            """
            UPDATE auth_sessions
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (token_hash,),
        )


def revoke_auth_session(conn: sqlite3.Connection, *, token_hash: str) -> None:
    with conn:
        conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (token_hash,),
        )


def list_auth_sessions_for_user(conn: sqlite3.Connection, *, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          id,
          user_id,
          auth_source,
          created_at,
          last_seen_at,
          expires_at,
          revoked_at
        FROM auth_sessions
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()


def revoke_auth_session_by_id_for_user(conn: sqlite3.Connection, *, user_id: int, session_id: int) -> bool:
    with conn:
        cursor = conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND id = ? AND revoked_at IS NULL
            """,
            (user_id, session_id),
        )
    return int(cursor.rowcount or 0) > 0


def record_auth_login_attempt(
    conn: sqlite3.Connection,
    *,
    username: str,
    success: bool,
    remote_addr: str | None = None,
) -> None:
    normalized = normalize_auth_username(username)
    if not normalized:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO auth_login_attempts(username, remote_addr, success)
            VALUES (?, ?, ?)
            """,
            (normalized, (remote_addr or "").strip() or None, 1 if success else 0),
        )


def count_recent_failed_auth_login_attempts(
    conn: sqlite3.Connection,
    *,
    username: str,
    since_iso: str,
) -> int:
    normalized = normalize_auth_username(username)
    if not normalized:
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM auth_login_attempts
        WHERE username = ?
          AND success = 0
          AND attempted_at >= ?
        """,
        (normalized, since_iso),
    ).fetchone()
    return int(row["count"]) if row else 0


def oldest_recent_failed_auth_login_attempt(
    conn: sqlite3.Connection,
    *,
    username: str,
    since_iso: str,
) -> sqlite3.Row | None:
    normalized = normalize_auth_username(username)
    if not normalized:
        return None
    return conn.execute(
        """
        SELECT id, username, remote_addr, success, attempted_at
        FROM auth_login_attempts
        WHERE username = ?
          AND success = 0
          AND attempted_at >= ?
        ORDER BY attempted_at ASC, id ASC
        LIMIT 1
        """,
        (normalized, since_iso),
    ).fetchone()


def clear_auth_login_attempts(conn: sqlite3.Connection, *, username: str) -> None:
    normalized = normalize_auth_username(username)
    if not normalized:
        return
    with conn:
        conn.execute("DELETE FROM auth_login_attempts WHERE username = ?", (normalized,))


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
    chunks = _chunk_derived_text(normalized_text)

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
        row = conn.execute(
            """
            SELECT id
            FROM derived_text
            WHERE workspace_id = ? AND source_kind = ? AND source_id = ? AND derivation_kind = ? AND extractor = ?
            """,
            (workspace_id, source_kind, source_id, derivation_kind, extractor),
        ).fetchone()
        derived_text_id = int(row["id"])
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
        conn.execute(
            "DELETE FROM derived_text_chunks WHERE derived_text_id = ?",
            (derived_text_id,),
        )
        conn.execute(
            "DELETE FROM derived_text_chunks_fts WHERE derived_text_id = ?",
            (derived_text_id,),
        )
        for index, chunk in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO derived_text_chunks(
                  derived_text_id, workspace_id, chunk_index, start_offset, end_offset, text, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    derived_text_id,
                    workspace_id,
                    index,
                    int(chunk["start_offset"]),
                    int(chunk["end_offset"]),
                    chunk["text"],
                    chunk["content_hash"],
                ),
            )
            conn.execute(
                """
                INSERT INTO derived_text_chunks_fts(workspace_id, derived_text_id, chunk_index, text)
                VALUES (?, ?, ?, ?)
                """,
                (workspace_id, derived_text_id, index, chunk["text"]),
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


def get_derived_text_chunks(
    conn: sqlite3.Connection,
    *,
    derived_text_id: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, derived_text_id, workspace_id, chunk_index, start_offset, end_offset, text, content_hash, created_at
        FROM derived_text_chunks
        WHERE derived_text_id = ?
        ORDER BY chunk_index ASC
        """,
        (derived_text_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_derived_text_chunk_embedding(
    conn: sqlite3.Connection,
    *,
    derived_text_chunk_id: int,
    workspace_id: int,
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
            INSERT INTO derived_text_chunk_embeddings(
              derived_text_chunk_id, workspace_id, model_id, dim, embedding_blob, content_hash
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(derived_text_chunk_id, model_id) DO UPDATE SET
              dim=excluded.dim,
              embedding_blob=excluded.embedding_blob,
              content_hash=excluded.content_hash,
              embedded_at=CURRENT_TIMESTAMP
            """,
            (derived_text_chunk_id, workspace_id, model_id, dim, payload, content_hash),
        )


def get_derived_text_chunk_embedding(
    conn: sqlite3.Connection,
    *,
    derived_text_chunk_id: int,
    model_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT derived_text_chunk_id, workspace_id, model_id, dim, embedding_blob, content_hash, embedded_at
        FROM derived_text_chunk_embeddings
        WHERE derived_text_chunk_id = ? AND model_id = ?
        """,
        (derived_text_chunk_id, model_id),
    ).fetchone()
    if not row:
        return None

    out = dict(row)
    vec = array("f")
    vec.frombytes(out["embedding_blob"])
    out["embedding"] = vec.tolist()
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

    for file_obj in message.get("files", []) or []:
        if not isinstance(file_obj, dict) or not file_obj.get("id"):
            continue
        upsert_file(conn, workspace_id, file_obj, local_path=None)

    if unchanged:
        return

    with conn:
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
              local_path=coalesce(excluded.local_path, files.local_path),
              checksum=coalesce(excluded.checksum, files.checksum),
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
        if _should_enqueue_file_ocr(mimetype=str(file_obj.get("mimetype") or ""), local_path=local_path):
            enqueue_derived_text_job(
                conn,
                workspace_id=workspace_id,
                source_kind="file",
                source_id=str(file_obj.get("id") or ""),
                derivation_kind="ocr_text",
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
        row = conn.execute(
            "SELECT mimetype FROM files WHERE workspace_id = ? AND file_id = ?",
            (workspace_id, file_id),
        ).fetchone()
    enqueue_derived_text_job(
        conn,
        workspace_id=workspace_id,
        source_kind="file",
        source_id=file_id,
        derivation_kind="attachment_text",
        reason="file_download",
    )
    if _should_enqueue_file_ocr(mimetype=str(row["mimetype"] or "") if row else None, local_path=local_path):
        enqueue_derived_text_job(
            conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id=file_id,
            derivation_kind="ocr_text",
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
