import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_derived_text, upsert_message, upsert_user, upsert_workspace
from slack_mirror.search.corpus import search_corpus
from slack_mirror.search.derived_text import search_derived_text, search_derived_text_semantic
from slack_mirror.search.keyword import reindex_messages_fts, search_messages
from slack_mirror.sync.embeddings import process_embedding_jobs


class SearchTests(unittest.TestCase):
    def test_keyword_search_messages(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_user(conn, ws_id, {"id": "U2", "name": "bob", "real_name": "Bob Example", "profile": {"display_name": "bobby"}})
            upsert_message(conn, ws_id, "C1", {"ts": "1.1", "text": "hello deploy world", "user": "U1"})
            upsert_message(
                conn,
                ws_id,
                "C1",
                {"ts": "1.2", "text": "deploy docs https://example.com", "user": "U2", "edited": {"ts": "1.21"}},
            )
            upsert_message(conn, ws_id, "C1", {"ts": "1.3", "text": "something else", "user": "U2"})

            rows = search_messages(conn, workspace_id=ws_id, query="deploy", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy from:U1", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], "U1")

            rows = search_messages(conn, workspace_id=ws_id, query="deploy from:<@U1>", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], "U1")

            rows = search_messages(conn, workspace_id=ws_id, query="deploy from:@alice", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], "U1")

            rows = search_messages(conn, workspace_id=ws_id, query="deploy channel:C1", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy channel:#general", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy in:#general", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy source:gen*", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy -source:gen*", limit=10)
            self.assertEqual(len(rows), 0)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy channel:<#C1>", limit=10)
            self.assertEqual(len(rows), 2)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy has:link is:edited", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], "U2")

            indexed = reindex_messages_fts(conn, workspace_id=ws_id)
            self.assertGreaterEqual(indexed, 3)

            rows = search_messages(conn, workspace_id=ws_id, query="deploy -docs", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], "U1")

            rows = search_messages(conn, workspace_id=ws_id, query="deploy", limit=10, use_fts=True)
            self.assertEqual(len(rows), 2)

            job_result = process_embedding_jobs(conn, workspace_id=ws_id, limit=50)
            self.assertEqual(job_result["errored"], 0)

            sem_rows = search_messages(
                conn,
                workspace_id=ws_id,
                query="deployment docs",
                mode="semantic",
                model_id="local-hash-128",
                limit=10,
            )
            self.assertGreaterEqual(len(sem_rows), 1)

            hyb_rows = search_messages(
                conn,
                workspace_id=ws_id,
                query="deploy docs",
                mode="hybrid",
                model_id="local-hash-128",
                limit=10,
            )
            self.assertGreaterEqual(len(hyb_rows), 1)
            self.assertIn("_hybrid_score", hyb_rows[0])

    def test_search_derived_text_rows(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F1', 'notes.txt', 'Notes', 'text/plain', '/tmp/notes.txt', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="project alpha deployment notes",
                media_type="text/plain",
                local_path="/tmp/notes.txt",
                metadata={"origin": "test"},
            )
            rows = search_derived_text(conn, workspace_id=ws_id, query="deployment", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_kind"], "file")
            self.assertEqual(rows[0]["source_label"], "Notes")

    def test_search_derived_text_returns_deep_matching_chunk(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F2', 'playbook.txt', 'Playbook', 'text/plain', '/tmp/playbook.txt', '{}')
                """,
                (ws_id,),
            )
            long_text = (
                ("intro status update " * 80)
                + "\n\n"
                + ("deployment background " * 80)
                + "\n\n"
                + ("catastrophic rollback signature " * 40)
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F2",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text=long_text,
                media_type="text/plain",
                local_path="/tmp/playbook.txt",
            )
            rows = search_derived_text(conn, workspace_id=ws_id, query="catastrophic rollback", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_label"], "Playbook")
            self.assertIn("catastrophic rollback", str(rows[0]["matched_text"]))
            self.assertGreaterEqual(int(rows[0]["chunk_index"]), 1)

    def test_search_derived_text_semantic_uses_shared_embedding_model(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F3', 'deploy.txt', 'Deploy Notes', 'text/plain', '/tmp/deploy.txt', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F3",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="deployment checklist for cooper gateway outage recovery",
                media_type="text/plain",
                local_path="/tmp/deploy.txt",
            )

            rows = search_derived_text_semantic(conn, workspace_id=ws_id, query="gateway outage recovery", limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_label"], "Deploy Notes")
            self.assertGreater(float(rows[0]["_semantic_score"]), 0.0)

    def test_search_corpus_combines_messages_and_derived_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "10.0", "text": "incident review follow-up", "user": "U1"})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F1', 'scan.pdf', 'Incident PDF', 'application/pdf', '/tmp/scan.pdf', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="ocr_text",
                extractor="tesseract_pdf",
                text="incident review appendix and findings",
                media_type="application/pdf",
                local_path="/tmp/scan.pdf",
                metadata={"origin": "test"},
            )

            rows = search_corpus(conn, workspace_id=ws_id, query="incident review", limit=10, mode="hybrid")
            self.assertGreaterEqual(len(rows), 2)
            kinds = {row["result_kind"] for row in rows}
            self.assertIn("message", kinds)
            self.assertIn("derived_text", kinds)
            self.assertTrue(any("_hybrid_score" in row for row in rows))

    def test_search_corpus_uses_chunk_snippet_for_derived_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F3', 'ocr.pdf', 'OCR Report', 'application/pdf', '/tmp/ocr.pdf', '{}')
                """,
                (ws_id,),
            )
            long_text = ("cover page " * 100) + "\n\n" + ("unusual payment discrepancy " * 50)
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F3",
                derivation_kind="ocr_text",
                extractor="tesseract_pdf",
                text=long_text,
                media_type="application/pdf",
                local_path="/tmp/ocr.pdf",
            )

            rows = search_corpus(conn, workspace_id=ws_id, query="payment discrepancy", limit=5, mode="hybrid")
            derived = next(row for row in rows if row["result_kind"] == "derived_text")
            self.assertIn("payment discrepancy", str(derived["snippet_text"]))

    def test_search_corpus_sets_workspace_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "12.0", "text": "cross workspace metadata check", "user": "U1"})

            rows = search_corpus(conn, workspace_id=ws_id, workspace_name="default", query="metadata check", limit=5, mode="lexical")
            self.assertEqual(rows[0]["workspace"], "default")
            self.assertEqual(rows[0]["workspace_id"], ws_id)


if __name__ == "__main__":
    unittest.main()
