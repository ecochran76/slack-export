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
    channel_ids: list[str] | None = None,
    oldest: str | None = None,
    latest: str | None = None,
    order: str = "latest",
    provider: EmbeddingProvider | None = None,
) -> dict[str, int]:
    clauses = ["m.workspace_id = ?", "m.deleted = 0"]
    params: list[object] = [workspace_id]

    normalized_channels = [str(value).strip() for value in (channel_ids or []) if str(value).strip()]
    if normalized_channels:
        placeholders = ",".join("?" for _ in normalized_channels)
        clauses.append(f"m.channel_id IN ({placeholders})")
        params.extend(normalized_channels)
    if oldest is not None:
        clauses.append("CAST(m.ts AS REAL) >= CAST(? AS REAL)")
        params.append(str(oldest))
    if latest is not None:
        clauses.append("CAST(m.ts AS REAL) <= CAST(? AS REAL)")
        params.append(str(latest))

    normalized_order = str(order or "latest").strip().lower()
    if normalized_order not in {"latest", "oldest"}:
        raise ValueError(f"Unsupported embeddings backfill order: {order}")
    order_sql = "DESC" if normalized_order == "latest" else "ASC"

    rows = list(
        conn.execute(
            f"""
            SELECT m.channel_id, m.ts, COALESCE(m.text, '') AS text
            FROM messages m
            WHERE {" AND ".join(clauses)}
            ORDER BY CAST(m.ts AS REAL) {order_sql}
            LIMIT ?
            """,
            (*params, limit),
        )
    )

    embedded = 0
    skipped = 0
    seen_channels: set[str] = set()
    for r in rows:
        seen_channels.add(str(r["channel_id"]))
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

    return {"scanned": len(rows), "embedded": embedded, "skipped": skipped, "channels": len(seen_channels)}


def backfill_message_embeddings_for_targets(
    conn,
    *,
    workspace_id: int,
    targets: list[dict[str, str]],
    model_id: str = "local-hash-128",
    provider: EmbeddingProvider | None = None,
) -> dict[str, int]:
    embedded = 0
    skipped = 0
    missing = 0
    seen: set[tuple[str, str]] = set()
    seen_channels: set[str] = set()

    for target in targets:
        channel_id = str(target.get("channel_id") or "").strip()
        ts = str(target.get("ts") or "").strip()
        if not channel_id or not ts:
            missing += 1
            continue
        key = (channel_id, ts)
        if key in seen:
            continue
        seen.add(key)
        seen_channels.add(channel_id)
        row = conn.execute(
            """
            SELECT COALESCE(text, '') AS text, deleted
            FROM messages
            WHERE workspace_id = ? AND channel_id = ? AND ts = ?
            """,
            (workspace_id, channel_id, ts),
        ).fetchone()
        if not row or int(row["deleted"]):
            missing += 1
            continue
        status = _embed_and_store(
            conn,
            workspace_id=workspace_id,
            channel_id=channel_id,
            ts=ts,
            text=row["text"],
            model_id=model_id,
            provider=provider,
        )
        if status == "embedded":
            embedded += 1
        else:
            skipped += 1

    return {
        "scanned": len(seen),
        "embedded": embedded,
        "skipped": skipped,
        "missing": missing,
        "channels": len(seen_channels),
    }


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
