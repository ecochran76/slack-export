import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, enqueue_derived_text_job, upsert_canvas, upsert_file, upsert_workspace
from slack_mirror.search.derived_text import search_derived_text
from slack_mirror.sync.derived_text import process_derived_text_jobs


class DerivedTextTests(unittest.TestCase):
    def test_process_jobs_extracts_canvas_and_text_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            cache = root / "cache"
            file_path = cache / "files" / "F1" / "notes.txt"
            canvas_path = cache / "canvases" / "CV1.html"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            canvas_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("deployment notes and timeline", encoding="utf-8")
            canvas_path.write_text("<html><body><h1>Canvas Plan</h1><p>incident review</p></body></html>", encoding="utf-8")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "F1", "name": "notes.txt", "title": "Notes", "mimetype": "text/plain"},
                local_path=str(file_path),
            )
            upsert_canvas(conn, ws_id, {"id": "CV1", "title": "Canvas 1"}, local_path=str(canvas_path))

            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="attachment_text", limit=10)
            self.assertEqual(result["errored"], 0)
            self.assertEqual(result["processed"], 2)

            rows = search_derived_text(conn, workspace_id=ws_id, query="incident", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_kind"], "canvas")
            self.assertEqual(rows[0]["extractor"], "canvas_html")

            rows = search_derived_text(conn, workspace_id=ws_id, query="deployment", limit=10, source_kind="file")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["extractor"], "utf8_text")

    def test_unsupported_derivation_kind_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            enqueue_derived_text_job(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="ocr_text",
                reason="test",
            )
            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="ocr_text", limit=10)
            self.assertEqual(result["processed"], 0)
            self.assertEqual(result["skipped"], 1)
            row = conn.execute("SELECT status, error FROM derived_text_jobs").fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["error"], "unsupported_derivation_kind")
