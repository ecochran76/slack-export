import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from slack_mirror.core.db import apply_migrations, connect, enqueue_derived_text_job, get_derived_text, upsert_canvas, upsert_file, upsert_workspace
from slack_mirror.search.derived_text import search_derived_text
from slack_mirror.sync.derived_text import CommandDerivedTextProvider, FallbackDerivedTextProvider, HttpDerivedTextProvider, build_derived_text_provider, process_derived_text_jobs


class DerivedTextTests(unittest.TestCase):
    def test_process_jobs_extracts_docx_story_parts_and_visible_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            cache = root / "cache"
            docx_path = cache / "files" / "DOCX2" / "rich.docx"
            docx_path.parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(docx_path, "w") as zf:
                zf.writestr(
                    'word/document.xml',
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Body line</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>tabbed value</w:t></w:r><w:r><w:br/></w:r><w:r><w:t>continued text</w:t></w:r></w:p></w:body></w:document>'
                )
                zf.writestr(
                    'word/header1.xml',
                    '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Header note</w:t></w:r></w:p></w:hdr>'
                )
                zf.writestr(
                    'word/footer1.xml',
                    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Footer summary</w:t></w:r></w:p></w:ftr>'
                )
                zf.writestr(
                    'word/footnotes.xml',
                    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:footnote w:id="2"><w:p><w:r><w:t>Footnote detail</w:t></w:r></w:p></w:footnote></w:footnotes>'
                )
                zf.writestr(
                    'word/endnotes.xml',
                    '<w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:endnote w:id="3"><w:p><w:r><w:t>Endnote appendix</w:t></w:r></w:p></w:endnote></w:endnotes>'
                )

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(conn, ws_id, {"id": "DOCX2", "name": "rich.docx", "title": "Rich", "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, local_path=str(docx_path))

            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="attachment_text", limit=10)
            self.assertEqual(result["errored"], 0)
            self.assertEqual(result["processed"], 1)

            row = get_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="DOCX2",
                derivation_kind="attachment_text",
                extractor="ooxml_docx",
            )
            self.assertIsNotNone(row)
            text_value = row["text"]
            self.assertIn("Body line", text_value)
            self.assertIn("tabbed value", text_value)
            self.assertIn("continued text", text_value)
            self.assertIn("Header note", text_value)
            self.assertIn("Footer summary", text_value)
            self.assertIn("Footnote detail", text_value)
            self.assertIn("Endnote appendix", text_value)

    def test_process_jobs_extracts_opendocument_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            cache = root / "cache"
            odt_path = cache / "files" / "ODT1" / "brief.odt"
            odp_path = cache / "files" / "ODP1" / "slides.odp"
            ods_path = cache / "files" / "ODS1" / "sheet.ods"
            for p in (odt_path, odp_path, ods_path):
                p.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(p, "w") as zf:
                    zf.writestr('content.xml', '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>%s</text:p></office:text></office:body></office:document-content>' % ({
                        odt_path: 'OpenDocument board brief',
                        odp_path: 'OpenDocument launch deck',
                        ods_path: 'OpenDocument revenue sheet',
                    }[p]))

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(conn, ws_id, {"id": "ODT1", "name": "brief.odt", "title": "Brief", "mimetype": "application/vnd.oasis.opendocument.text"}, local_path=str(odt_path))
            upsert_file(conn, ws_id, {"id": "ODP1", "name": "slides.odp", "title": "Slides", "mimetype": "application/vnd.oasis.opendocument.presentation"}, local_path=str(odp_path))
            upsert_file(conn, ws_id, {"id": "ODS1", "name": "sheet.ods", "title": "Sheet", "mimetype": "application/vnd.oasis.opendocument.spreadsheet"}, local_path=str(ods_path))

            result = process_derived_text_jobs(conn, workspace_id=ws_id, derivation_kind="attachment_text", limit=10)
            self.assertEqual(result["errored"], 0)
            self.assertEqual(result["processed"], 3)

            rows = search_derived_text(conn, workspace_id=ws_id, query="board brief", limit=10)
            self.assertEqual(rows[0]["extractor"], "odf_odt")
            rows = search_derived_text(conn, workspace_id=ws_id, query="launch deck", limit=10)
            self.assertEqual(rows[0]["extractor"], "odf_odp")
            rows = search_derived_text(conn, workspace_id=ws_id, query="revenue sheet", limit=10)
            self.assertEqual(rows[0]["extractor"], "odf_ods")

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

    def test_http_provider_invokes_json_protocol(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F2" / "scan.pdf"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"%PDF-1.4 fake")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "F2", "name": "scan.pdf", "title": "Scan", "mimetype": "application/pdf"},
                local_path=str(file_path),
            )

            provider = HttpDerivedTextProvider("https://extractor.example/v1/extract", headers={"X-Provider": "test"}, timeout_s=12.0)

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps({
                        "ok": True,
                        "text": "remote http attachment text",
                        "extractor": "remote_http",
                        "details": {"route": "http"},
                    }).encode("utf-8")

            def fake_urlopen(req, timeout):
                self.assertEqual(timeout, 12.0)
                self.assertEqual(req.full_url, "https://extractor.example/v1/extract")
                self.assertEqual(req.get_method(), "POST")
                self.assertEqual(req.headers.get("Content-type"), "application/json")
                self.assertEqual(req.headers.get("X-provider"), "test")
                payload = json.loads(req.data.decode("utf-8"))
                self.assertEqual(payload["action"], "attachment_text")
                self.assertEqual(payload["workspace_id"], ws_id)
                self.assertEqual(payload["source_kind"], "file")
                self.assertEqual(payload["source_id"], "F2")
                self.assertEqual(payload["local_path"], str(file_path))
                return FakeResponse()

            with patch("slack_mirror.sync.derived_text.urllib_request.urlopen", side_effect=fake_urlopen):
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
                source_id="F2",
                derivation_kind="attachment_text",
                extractor="remote_http",
            )
            self.assertEqual(row["metadata"]["provider"], "http:extractor.example")
            self.assertEqual(row["metadata"]["route"], "http")

    def test_http_provider_reports_auth_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F3" / "scan.pdf"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"%PDF-1.4 fake")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "F3", "name": "scan.pdf", "title": "Scan", "mimetype": "application/pdf"},
                local_path=str(file_path),
            )

            provider = HttpDerivedTextProvider("https://extractor.example/v1/extract", bearer_token_env="SLACK_MIRROR_TEST_TOKEN")
            with patch.dict("os.environ", {}, clear=False):
                result = process_derived_text_jobs(
                    conn,
                    workspace_id=ws_id,
                    derivation_kind="attachment_text",
                    limit=10,
                    provider=provider,
                )

            self.assertEqual(result["processed"], 0)
            self.assertEqual(result["skipped"], 1)
            row = conn.execute("SELECT status, error FROM derived_text_jobs WHERE source_id = 'F3'").fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["error"], "provider_auth_missing")

    def test_http_provider_reports_http_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F4" / "scan.pdf"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"%PDF-1.4 fake")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "F4", "name": "scan.pdf", "title": "Scan", "mimetype": "application/pdf"},
                local_path=str(file_path),
            )

            provider = HttpDerivedTextProvider("https://extractor.example/v1/extract")

            def fake_urlopen(req, timeout):
                raise HTTPError(req.full_url, 502, "Bad Gateway", hdrs=None, fp=io.BytesIO(b"upstream unavailable"))

            with patch("slack_mirror.sync.derived_text.urllib_request.urlopen", side_effect=fake_urlopen):
                result = process_derived_text_jobs(
                    conn,
                    workspace_id=ws_id,
                    derivation_kind="attachment_text",
                    limit=10,
                    provider=provider,
                )

            self.assertEqual(result["processed"], 0)
            self.assertEqual(result["skipped"], 1)
            row = conn.execute("SELECT status, error FROM derived_text_jobs WHERE source_id = 'F4'").fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["error"], "provider_http_error")


    def test_build_provider_from_config_returns_http_provider(self):
        provider = build_derived_text_provider(
            {
                "search": {
                    "derived_text": {
                        "provider": {
                            "type": "http",
                            "url": "https://extractor.example/v1/extract",
                            "headers": {"X-Provider": "test"},
                            "bearer_token_env": "SLACK_MIRROR_EXTRACT_TOKEN",
                            "timeout_s": 30,
                        }
                    }
                }
            }
        )
        self.assertIsInstance(provider, FallbackDerivedTextProvider)
        self.assertIsInstance(provider.primary, HttpDerivedTextProvider)
        self.assertEqual(provider.primary.url, "https://extractor.example/v1/extract")
        self.assertEqual(provider.primary.headers, {"X-Provider": "test"})
        self.assertEqual(provider.primary.bearer_token_env, "SLACK_MIRROR_EXTRACT_TOKEN")
        self.assertEqual(provider.primary.timeout_s, 30.0)
        self.assertEqual(provider.primary.name, "http:extractor.example")
        self.assertEqual(provider.fallback.name, "local_host_tools")


    def test_http_provider_can_fallback_to_local_extractor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mirror.db"
            file_path = root / "cache" / "files" / "F5" / "notes.txt"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("fallback local extraction text", encoding="utf-8")

            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_file(
                conn,
                ws_id,
                {"id": "F5", "name": "notes.txt", "title": "Notes", "mimetype": "text/plain"},
                local_path=str(file_path),
            )

            provider = build_derived_text_provider(
                {
                    "search": {
                        "derived_text": {
                            "provider": {
                                "type": "http",
                                "url": "https://extractor.example/v1/extract",
                                "fallback_to_local": True,
                            }
                        }
                    }
                }
            )

            def fake_urlopen(req, timeout):
                raise HTTPError(req.full_url, 502, "Bad Gateway", hdrs=None, fp=io.BytesIO(b"upstream unavailable"))

            with patch("slack_mirror.sync.derived_text.urllib_request.urlopen", side_effect=fake_urlopen):
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
                source_id="F5",
                derivation_kind="attachment_text",
                extractor="utf8_text",
            )
            self.assertEqual(row["metadata"]["provider"], "local_host_tools")
            self.assertEqual(row["metadata"]["fallback_from"], "http:extractor.example")
            self.assertEqual(row["metadata"]["fallback_error"], "provider_http_error")

    def test_build_provider_from_config_wraps_http_provider_with_local_fallback(self):
        provider = build_derived_text_provider(
            {
                "search": {
                    "derived_text": {
                        "provider": {
                            "type": "http",
                            "url": "https://extractor.example/v1/extract",
                            "fallback_to_local": True,
                        }
                    }
                }
            }
        )
        self.assertIsInstance(provider, FallbackDerivedTextProvider)
        self.assertEqual(provider.primary.name, "http:extractor.example")
        self.assertEqual(provider.fallback.name, "local_host_tools")

    def test_build_provider_from_config_can_disable_http_local_fallback(self):
        provider = build_derived_text_provider(
            {
                "search": {
                    "derived_text": {
                        "provider": {
                            "type": "http",
                            "url": "https://extractor.example/v1/extract",
                            "fallback_to_local": False,
                        }
                    }
                }
            }
        )
        self.assertIsInstance(provider, HttpDerivedTextProvider)


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
        self.assertIsInstance(provider, FallbackDerivedTextProvider)
        self.assertIsInstance(provider.primary, CommandDerivedTextProvider)
        self.assertEqual(provider.primary.command, ["/usr/local/bin/extractor", "--json"])
        self.assertEqual(provider.primary.name, "command:extractor")
        self.assertEqual(provider.fallback.name, "local_host_tools")

