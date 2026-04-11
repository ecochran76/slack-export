import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from slack_mirror.core.db import apply_migrations, connect, enqueue_derived_text_job, get_derived_text, upsert_canvas, upsert_file, upsert_workspace
from slack_mirror.search.derived_text import search_derived_text
from slack_mirror.sync.derived_text import CommandDerivedTextProvider, build_derived_text_provider, process_derived_text_jobs


class DerivedTextTests(unittest.TestCase):
    def test_process_jobs_extracts_ooxml_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            cache = root / "cache"
            docx_path = cache / "files" / "DOC1" / "brief.docx"
            pptx_path = cache / "files" / "PPT1" / "slides.pptx"
            xlsx_path = cache / "files" / "XLS1" / "sheet.xlsx"
            for p in (docx_path, pptx_path, xlsx_path):
                p.parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(docx_path, "w") as zf:
                zf.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Quarterly board brief</w:t></w:r></w:p></w:body></w:document>')
            with zipfile.ZipFile(pptx_path, "w") as zf:
                zf.writestr('ppt/slides/slide1.xml', '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><a:t xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">Launch roadmap</a:t></p:spTree></p:cSld></p:sld>')
            with zipfile.ZipFile(xlsx_path, "w") as zf:
                zf.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Revenue plan</t></si></sst>')
                zf.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>')

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(conn, ws_id, {"id": "DOC1", "name": "brief.docx", "title": "Brief", "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, local_path=str(docx_path))
            upsert_file(conn, ws_id, {"id": "PPT1", "name": "slides.pptx", "title": "Slides", "mimetype": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}, local_path=str(pptx_path))
            upsert_file(conn, ws_id, {"id": "XLS1", "name": "sheet.xlsx", "title": "Sheet", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}, local_path=str(xlsx_path))

            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="attachment_text", limit=10)
            self.assertEqual(result["errored"], 0)
            self.assertEqual(result["processed"], 3)

            rows = search_derived_text(conn, workspace_id=ws_id, query="quarterly board", limit=10)
            self.assertEqual(rows[0]["extractor"], "ooxml_docx")
            rows = search_derived_text(conn, workspace_id=ws_id, query="launch roadmap", limit=10)
            self.assertEqual(rows[0]["extractor"], "ooxml_pptx")
            rows = search_derived_text(conn, workspace_id=ws_id, query="revenue plan", limit=10)
            self.assertEqual(rows[0]["extractor"], "ooxml_xlsx")

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

    def test_process_ocr_jobs_extracts_image_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            image_path = root / "cache" / "files" / "IMG1" / "scan.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"fake-png")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "IMG1", "name": "scan.png", "title": "Scan", "mimetype": "image/png"},
                local_path=str(image_path),
            )

            def fake_which(name: str) -> str | None:
                if name == "tesseract":
                    return f"/usr/bin/{name}"
                return None

            def fake_run(args, check, capture_output, text):
                self.assertEqual(args[0], "/usr/bin/tesseract")
                self.assertEqual(args[2], "stdout")

                class Result:
                    returncode = 0
                    stdout = "diagram heading and labels"

                return Result()

            with patch("slack_mirror.sync.derived_text.shutil.which", side_effect=fake_which), patch(
                "slack_mirror.sync.derived_text.subprocess.run", side_effect=fake_run
            ):
                result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="ocr_text", limit=10)

            self.assertEqual(result["processed"], 1)
            rows = search_derived_text(conn, workspace_id=ws_id, query="heading", limit=10, derivation_kind="ocr_text")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["extractor"], "tesseract_image")

    def test_process_ocr_jobs_extracts_scanned_pdf_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            pdf_path = root / "cache" / "files" / "PDF1" / "scan.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 fake")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "PDF1", "name": "scan.pdf", "title": "Scan PDF", "mimetype": "application/pdf"},
                local_path=str(pdf_path),
            )

            def fake_which(name: str) -> str | None:
                if name in {"pdftotext", "pdftoppm", "tesseract"}:
                    return f"/usr/bin/{name}"
                return None

            def fake_run(args, check, capture_output, text):
                class Result:
                    def __init__(self, returncode, stdout=""):
                        self.returncode = returncode
                        self.stdout = stdout

                if args[0] == "/usr/bin/pdftotext":
                    return Result(0, "")
                if args[0] == "/usr/bin/pdftoppm":
                    Path(f"{args[-1]}-1.png").write_bytes(b"png")
                    return Result(0, "")
                if args[0] == "/usr/bin/tesseract":
                    return Result(0, "scanned invoice total")
                raise AssertionError(args)

            with patch("slack_mirror.sync.derived_text.shutil.which", side_effect=fake_which), patch(
                "slack_mirror.sync.derived_text.subprocess.run", side_effect=fake_run
            ):
                result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="ocr_text", limit=10)

            self.assertEqual(result["processed"], 1)
            rows = search_derived_text(conn, workspace_id=ws_id, query="invoice", limit=10, derivation_kind="ocr_text")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["extractor"], "tesseract_pdf")

    def test_pdf_with_text_layer_skips_ocr(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            pdf_path = root / "cache" / "files" / "PDF2" / "text.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 fake")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "PDF2", "name": "text.pdf", "title": "Text PDF", "mimetype": "application/pdf"},
                local_path=str(pdf_path),
            )

            def fake_which(name: str) -> str | None:
                if name == "pdftotext":
                    return f"/usr/bin/{name}"
                return None

            def fake_run(args, check, capture_output, text):
                class Result:
                    returncode = 0
                    stdout = "already searchable"

                self.assertEqual(args[0], "/usr/bin/pdftotext")
                return Result()

            with patch("slack_mirror.sync.derived_text.shutil.which", side_effect=fake_which), patch(
                "slack_mirror.sync.derived_text.subprocess.run", side_effect=fake_run
            ):
                result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="ocr_text", limit=10)

            self.assertEqual(result["processed"], 0)
            self.assertEqual(result["skipped"], 1)
            row = conn.execute(
                "SELECT status, error FROM derived_text_jobs WHERE source_id = 'PDF2' AND derivation_kind = 'ocr_text'"
            ).fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["error"], "pdf_has_text_layer")

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
                derivation_kind="thumbnail_text",
                reason="test",
            )
            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="thumbnail_text", limit=10)
            self.assertEqual(result["processed"], 0)
            self.assertEqual(result["skipped"], 1)
            row = conn.execute("SELECT status, error FROM derived_text_jobs").fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["error"], "unsupported_derivation_kind")

    def test_process_jobs_accepts_custom_provider(self):
        class FakeProvider:
            name = "fake_remote"

            def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str):
                return "remote extracted brief", {
                    "extractor": "remote_attachment",
                    "media_type": "text/plain",
                    "local_path": "/virtual/remote.txt",
                    "route": "remote",
                }

            def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str):
                raise AssertionError("unexpected ocr path")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F1" / "notes.txt"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("ignored local text", encoding="utf-8")

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

            result = process_derived_text_jobs(
                conn,
                workspace_id=ws_id,
                derivation_kind="attachment_text",
                limit=10,
                provider=FakeProvider(),
            )

            self.assertEqual(result["processed"], 1)
            row = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
                extractor="remote_attachment",
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["text"], "remote extracted brief")
            self.assertEqual(row["metadata"]["provider"], "fake_remote")
            self.assertEqual(row["metadata"]["route"], "remote")

    def test_local_provider_metadata_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            cache = root / "cache"
            file_path = cache / "files" / "F1" / "notes.txt"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("deployment notes and timeline", encoding="utf-8")

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

            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="attachment_text", limit=10)

            self.assertEqual(result["processed"], 1)
            row = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
                extractor="utf8_text",
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["metadata"]["provider"], "local_host_tools")

    def test_command_provider_invokes_json_protocol(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F1" / "notes.txt"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("ignored local text", encoding="utf-8")

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

            provider = CommandDerivedTextProvider(["/usr/local/bin/extractor", "--json"])

            def fake_run(args, check, capture_output, text, input):
                self.assertEqual(args, ["/usr/local/bin/extractor", "--json"])
                payload = json.loads(input)
                self.assertEqual(payload["action"], "attachment_text")
                self.assertEqual(payload["workspace_id"], ws_id)
                self.assertEqual(payload["source_kind"], "file")
                self.assertEqual(payload["source_id"], "F1")
                self.assertEqual(payload["local_path"], str(file_path))

                class Result:
                    returncode = 0
                    stdout = json.dumps(
                        {
                            "ok": True,
                            "text": "remote attachment text",
                            "extractor": "remote_command",
                            "details": {"route": "command"},
                        }
                    )
                    stderr = ""

                return Result()

            with patch("slack_mirror.sync.derived_text.subprocess.run", side_effect=fake_run):
                result = process_derived_text_jobs(
                    conn,
                    workspace_id=ws_id,
                    derivation_kind="attachment_text",
                    limit=10,
                    provider=provider,
                )

            self.assertEqual(result["processed"], 1)
            row = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="attachment_text",
                extractor="remote_command",
            )
            self.assertEqual(row["metadata"]["provider"], "command:extractor")
            self.assertEqual(row["metadata"]["route"], "command")

    def test_build_provider_from_config_returns_command_provider(self):
        provider = build_derived_text_provider(
            {
                "search": {
                    "derived_text": {
                        "provider": {
                            "type": "command",
                            "command": "/usr/local/bin/extractor --json",
                        }
                    }
                }
            }
        )
        self.assertIsInstance(provider, CommandDerivedTextProvider)
        self.assertEqual(provider.command, ["/usr/local/bin/extractor", "--json"])
        self.assertEqual(provider.name, "command:extractor")

