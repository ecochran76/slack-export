import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_derived_text,
    get_derived_text_chunks,
    get_message_embedding,
    get_sync_state,
    list_recent_thread_roots,
    list_workspaces,
    remove_channel_member,
    set_sync_state,
    upsert_derived_text,
    upsert_canvas,
    upsert_channel,
    upsert_channel_member,
    upsert_file,
    upsert_message,
    upsert_message_embedding,
    upsert_workspace,
)


class DbTests(unittest.TestCase):
    def test_migrate_and_upsert_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            self.assertTrue(ws_id > 0)

            rows = list_workspaces(conn)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "default")

            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            upsert_message(conn, ws_id, "C123", {"ts": "123.45", "text": "hello", "user": "U1"})
            upsert_message(conn, ws_id, "C123", {"ts": "200.00", "thread_ts": "200.00", "text": "root", "user": "U1"})
            count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            self.assertEqual(count, 2)

            roots = list_recent_thread_roots(conn, ws_id, "C123", min_ts="150")
            self.assertEqual(roots, ["200.00"])

            pending_jobs = conn.execute("SELECT COUNT(*) AS c FROM embedding_jobs WHERE status='pending'").fetchone()["c"]
            self.assertEqual(pending_jobs, 2)

            upsert_message(conn, ws_id, "C123", {"ts": "123.45", "text": "hello", "user": "U1"})
            pending_jobs = conn.execute("SELECT COUNT(*) AS c FROM embedding_jobs WHERE status='pending'").fetchone()["c"]
            self.assertEqual(pending_jobs, 2)

            upsert_message_embedding(
                conn,
                workspace_id=ws_id,
                channel_id="C123",
                ts="123.45",
                model_id="test-embed-v1",
                embedding=[0.1, 0.2, 0.3],
                content_hash="h1",
            )
            emb = get_message_embedding(
                conn,
                workspace_id=ws_id,
                channel_id="C123",
                ts="123.45",
                model_id="test-embed-v1",
            )
            self.assertIsNotNone(emb)
            self.assertEqual(emb["dim"], 3)
            self.assertEqual(emb["content_hash"], "h1")
            self.assertEqual([round(x, 5) for x in emb["embedding"]], [0.1, 0.2, 0.3])

            upsert_message_embedding(
                conn,
                workspace_id=ws_id,
                channel_id="C123",
                ts="123.45",
                model_id="test-embed-v1",
                embedding=[0.9, 0.8, 0.7, 0.6],
                content_hash="h2",
            )
            emb = get_message_embedding(
                conn,
                workspace_id=ws_id,
                channel_id="C123",
                ts="123.45",
                model_id="test-embed-v1",
            )
            self.assertIsNotNone(emb)
            self.assertEqual(emb["dim"], 4)
            self.assertEqual(emb["content_hash"], "h2")
            self.assertEqual([round(x, 5) for x in emb["embedding"]], [0.9, 0.8, 0.7, 0.6])

            fts_count = conn.execute(
                "SELECT COUNT(*) AS c FROM messages_fts WHERE workspace_id = ? AND channel_id = ? AND ts = ?",
                (ws_id, "C123", "123.45"),
            ).fetchone()["c"]
            self.assertEqual(fts_count, 1)

            upsert_channel_member(conn, ws_id, "C123", "U1")
            member_count = conn.execute("SELECT COUNT(*) AS c FROM channel_members").fetchone()["c"]
            self.assertEqual(member_count, 1)
            remove_channel_member(conn, ws_id, "C123", "U1")
            member_count = conn.execute("SELECT COUNT(*) AS c FROM channel_members").fetchone()["c"]
            self.assertEqual(member_count, 0)

            upsert_message(conn, ws_id, "C123", {"ts": "123.45", "text": "hello", "user": "U1", "subtype": "message_deleted"})
            fts_count = conn.execute(
                "SELECT COUNT(*) AS c FROM messages_fts WHERE workspace_id = ? AND channel_id = ? AND ts = ?",
                (ws_id, "C123", "123.45"),
            ).fetchone()["c"]
            self.assertEqual(fts_count, 0)

            set_sync_state(conn, ws_id, "messages.oldest.C123", "123.45")
            state = get_sync_state(conn, ws_id, "messages.oldest.C123")
            self.assertEqual(state, "123.45")

            upsert_file(conn, ws_id, {"id": "F1", "name": "a.txt", "title": "A"}, local_path="cache/files/F1/a.txt")
            upsert_canvas(conn, ws_id, {"id": "CV1", "title": "Canvas 1"}, local_path="cache/canvases/CV1.html")
            file_count = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]
            canvas_count = conn.execute("SELECT COUNT(*) AS c FROM canvases").fetchone()["c"]
            self.assertEqual(file_count, 1)
            self.assertEqual(canvas_count, 1)

            derived_job_count = conn.execute("SELECT COUNT(*) AS c FROM derived_text_jobs WHERE status='pending'").fetchone()["c"]
            self.assertEqual(derived_job_count, 2)

            upsert_file(
                conn,
                ws_id,
                {"id": "F2", "name": "scan.png", "title": "Scan", "mimetype": "image/png"},
                local_path="cache/files/F2/scan.png",
            )
            ocr_job_count = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM derived_text_jobs
                WHERE source_kind = 'file' AND source_id = 'F2' AND derivation_kind = 'ocr_text' AND status = 'pending'
                """
            ).fetchone()["c"]
            self.assertEqual(ocr_job_count, 1)

            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="alpha bravo charlie",
                media_type="text/plain",
                local_path="cache/files/F1/a.txt",
                metadata={"origin": "test"},
            )
            derived = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
            )
            self.assertIsNotNone(derived)
            self.assertEqual(derived["extractor"], "utf8_text")
            self.assertEqual(derived["metadata"]["origin"], "test")
            derived_fts_count = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM derived_text_fts
                WHERE workspace_id = ? AND source_kind = 'file' AND source_id = 'F1'
                """,
                (ws_id,),
            ).fetchone()["c"]
            self.assertEqual(derived_fts_count, 1)
            chunks = get_derived_text_chunks(conn, derived_text_id=int(derived["id"]))
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0]["chunk_index"], 0)

    def test_upsert_derived_text_rebuilds_chunks_for_long_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            long_text = ("alpha " * 120) + "\n\n" + ("bravo " * 120) + "\n\n" + ("charlie " * 120)
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F9",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text=long_text,
            )
            derived = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F9",
                derivation_kind="attachment_text",
            )
            self.assertIsNotNone(derived)
            chunks = get_derived_text_chunks(conn, derived_text_id=int(derived["id"]))
            self.assertGreater(len(chunks), 1)

            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F9",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="short replacement text",
            )
            refreshed = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F9",
                derivation_kind="attachment_text",
            )
            refreshed_chunks = get_derived_text_chunks(conn, derived_text_id=int(refreshed["id"]))
            self.assertEqual(len(refreshed_chunks), 1)
            self.assertEqual(refreshed_chunks[0]["text"], "short replacement text")


if __name__ == "__main__":
    unittest.main()
