import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_derived_text, upsert_message, upsert_user, upsert_workspace
from slack_mirror.search.derived_text import search_derived_text
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


if __name__ == "__main__":
    unittest.main()
