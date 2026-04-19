from __future__ import annotations

import hashlib

from slack_mirror.core.db import (
    get_message_embedding,
    list_pending_embedding_jobs,
    mark_embedding_job_status,
    upsert_message_embedding,
)
from slack_mirror.search.embeddings import EmbeddingProvider, embed_text


def _content_hash(message_text: str) -> str:
    return hashlib.sha256(message_text.encode("utf-8")).hexdigest()


def _embed_and_store(
    conn,
    *,
    workspace_id: int,
    channel_id: str,
    ts: str,
    text: str,
    model_id: str,
    provider: EmbeddingProvider | None = None,
) -> str:
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

    emb = embed_text(text or "", model_id=model_id, provider=provider)
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
    provider: EmbeddingProvider | None = None,
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
            provider=provider,
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
    provider: EmbeddingProvider | None = None,
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
                provider=provider,
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
