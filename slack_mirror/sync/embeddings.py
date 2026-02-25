from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from slack_mirror.core.db import (
    get_message_embedding,
    list_pending_embedding_jobs,
    mark_embedding_job_status,
    upsert_message_embedding,
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _content_hash(message_text: str) -> str:
    return hashlib.sha256(message_text.encode("utf-8")).hexdigest()


def _embed_text_local(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        slot = int.from_bytes(digest, "little") % dim
        vec[slot] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _embed_and_store(conn, *, workspace_id: int, channel_id: str, ts: str, text: str, model_id: str) -> str:
    h = _content_hash(text or "")
    existing = get_message_embedding(
        conn,
        workspace_id=workspace_id,
        channel_id=channel_id,
        ts=ts,
        model_id=model_id,
    )
    if existing and existing.get("content_hash") == h:
        return "skipped"

    emb = _embed_text_local(text or "")
    upsert_message_embedding(
        conn,
        workspace_id=workspace_id,
        channel_id=channel_id,
        ts=ts,
        model_id=model_id,
        embedding=emb,
        content_hash=h,
    )
    return "embedded"


def backfill_message_embeddings(
    conn,
    *,
    workspace_id: int,
    model_id: str = "local-hash-128",
    limit: int = 1000,
) -> dict[str, int]:
    rows = list(
        conn.execute(
            """
            SELECT m.channel_id, m.ts, COALESCE(m.text, '') AS text
            FROM messages m
            WHERE m.workspace_id = ? AND m.deleted = 0
            ORDER BY m.updated_at DESC
            LIMIT ?
            """,
            (workspace_id, limit),
        )
    )

    embedded = 0
    skipped = 0
    for r in rows:
        status = _embed_and_store(
            conn,
            workspace_id=workspace_id,
            channel_id=r["channel_id"],
            ts=r["ts"],
            text=r["text"],
            model_id=model_id,
        )
        if status == "embedded":
            embedded += 1
        else:
            skipped += 1

    return {"scanned": len(rows), "embedded": embedded, "skipped": skipped}


def process_embedding_jobs(
    conn,
    *,
    workspace_id: int,
    model_id: str = "local-hash-128",
    limit: int = 200,
) -> dict[str, int]:
    jobs = list_pending_embedding_jobs(conn, workspace_id, limit=limit)

    processed = 0
    skipped = 0
    errored = 0
    for job in jobs:
        try:
            row = conn.execute(
                """
                SELECT COALESCE(text, '') AS text, deleted
                FROM messages
                WHERE workspace_id = ? AND channel_id = ? AND ts = ?
                """,
                (workspace_id, job["channel_id"], job["ts"]),
            ).fetchone()
            if not row or int(row["deleted"]):
                mark_embedding_job_status(conn, job_id=int(job["id"]), status="skipped", error="message_missing_or_deleted")
                skipped += 1
                continue

            status = _embed_and_store(
                conn,
                workspace_id=workspace_id,
                channel_id=job["channel_id"],
                ts=job["ts"],
                text=row["text"],
                model_id=model_id,
            )
            mark_embedding_job_status(conn, job_id=int(job["id"]), status="done")
            if status == "embedded":
                processed += 1
            else:
                skipped += 1
        except Exception as exc:  # pragma: no cover - defensive
            mark_embedding_job_status(conn, job_id=int(job["id"]), status="error", error=str(exc))
            errored += 1

    return {"jobs": len(jobs), "processed": processed, "skipped": skipped, "errored": errored}
