from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "export_channel_day_docx.py"
VALIDATOR_PATH = Path(__file__).resolve().parent.parent / "scripts" / "validate_export_docx.py"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_channel_day_docx", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_export_docx", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _rewrite_docx_part(docx_path: Path, part_name: str, payload: bytes) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rewritten = Path(tmpdir) / "rewritten.docx"
        with zipfile.ZipFile(docx_path, "r") as src, zipfile.ZipFile(
            rewritten, "w", compression=zipfile.ZIP_DEFLATED
        ) as dst:
            for info in src.infolist():
                if info.filename == part_name:
                    continue
                dst.writestr(info, src.read(info.filename))
            dst.writestr(part_name, payload)
        docx_path.write_bytes(rewritten.read_bytes())


class ExportDocxTests(unittest.TestCase):
    def _write_sample_json(self, path: Path, *, day: str, channel: str, channel_id: str, attachment_local: str | None = None) -> None:
        payload = {
            "workspace": "default",
            "channel": channel,
            "channel_id": channel_id,
            "day": day,
            "tz": "America/Chicago",
            "messages": [
                {
                    "ts": "10.0",
                    "human_ts": f"{day} 10:00:00 CDT",
                    "user_id": "U1",
                    "user_label": "Eric (U1)",
                    "text": "Launch roadmap\nQ4 milestone",
                    "thread_ts": None,
                    "deleted": False,
                    "attachments": [
                        {
                            "name": "incident.png",
                            "mimetype": "image/png",
                            "local_path": attachment_local,
                            "permalink": None,
                        }
                    ] if attachment_local else [],
                },
                {
                    "ts": "10.1",
                    "human_ts": f"{day} 10:05:00 CDT",
                    "user_id": "U2",
                    "user_label": "Alicia (U2)",
                    "text": "Reply detail",
                    "thread_ts": "10.0",
                    "deleted": False,
                    "attachments": [],
                },
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_render_channel_day_docx_writes_expected_package_and_content(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_json = tmp / "sample.json"
            output_docx = tmp / "sample.docx"
            attachment_path = tmp / "incident.png"
            attachment_path.write_bytes(b"png")
            self._write_sample_json(
                input_json,
                day="2026-04-11",
                channel="general",
                channel_id="C1",
                attachment_local=str(attachment_path),
            )

            module.render_channel_day_docx(input_json, output_docx)

            self.assertTrue(output_docx.exists())
            with zipfile.ZipFile(output_docx, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("_rels/.rels", names)
                self.assertIn("word/document.xml", names)
                self.assertIn("word/_rels/document.xml.rels", names)
                self.assertIn("word/styles.xml", names)
                self.assertIn("word/fontTable.xml", names)
                self.assertIn("word/settings.xml", names)
                self.assertIn("word/theme/theme1.xml", names)

                document = ET.fromstring(zf.read("word/document.xml"))
                rels = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                styles = ET.fromstring(zf.read("word/styles.xml"))

            text_values = [elem.text or "" for elem in document.findall(f".//{{{W_NS}}}t")]
            joined = "\n".join(text_values)
            self.assertIn("default / #general", joined)
            self.assertIn("Launch roadmap", joined)
            self.assertIn("Q4 milestone", joined)
            self.assertIn("[THREAD REPLY] ", joined)
            self.assertIn("Reply detail", joined)
            self.assertIn("incident.png", joined)
            self.assertIn("type: PNG image", joined)
            self.assertIn("source: local file", joined)
            self.assertNotIn("thread=10.0", joined)

            paragraph_styles = [
                style.get(f"{{{W_NS}}}val")
                for style in document.findall(f".//{{{W_NS}}}pPr/{{{W_NS}}}pStyle")
            ]
            self.assertIn("ReplyMeta", paragraph_styles)
            self.assertIn("ReplyBody", paragraph_styles)
            self.assertIn("AttachmentItem", paragraph_styles)
            self.assertIn("AttachmentMeta", paragraph_styles)

            style_ids = {style.attrib.get(f"{{{W_NS}}}styleId") for style in styles.findall(f".//{{{W_NS}}}style")}
            self.assertIn("Meta", style_ids)
            self.assertIn("ReplyMeta", style_ids)
            self.assertIn("MessageBody", style_ids)
            self.assertIn("ReplyBody", style_ids)
            self.assertIn("AttachmentItem", style_ids)
            self.assertIn("AttachmentItemReply", style_ids)
            self.assertIn("AttachmentMeta", style_ids)
            self.assertIn("AttachmentMetaReply", style_ids)

            hyperlink_rels = [
                rel
                for rel in rels.findall(f".//{{{PKG_REL_NS}}}Relationship")
                if rel.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
            ]
            self.assertEqual(len(hyperlink_rels), 1)
            self.assertTrue(hyperlink_rels[0].attrib.get("Target", "").startswith("file://"))

    def test_render_multi_day_docx_combines_json_exports_with_page_breaks(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            first_json = tmp / "day1.json"
            second_json = tmp / "day2.json"
            output_docx = tmp / "combined.docx"
            self._write_sample_json(first_json, day="2026-04-11", channel="general", channel_id="C1")
            self._write_sample_json(second_json, day="2026-04-12", channel="alerts", channel_id="C2")

            module.render_multi_day_docx([first_json, second_json], output_docx, package_title="Slack Export DOCX Package")

            self.assertTrue(output_docx.exists())
            with zipfile.ZipFile(output_docx, "r") as zf:
                document = ET.fromstring(zf.read("word/document.xml"))

            text_values = [elem.text or "" for elem in document.findall(f".//{{{W_NS}}}t")]
            joined = "\n".join(text_values)
            self.assertIn("Slack Export DOCX Package", joined)
            self.assertIn("default / #general", joined)
            self.assertIn("default / #alerts", joined)
            self.assertIn("2026-04-11", joined)
            self.assertIn("2026-04-12", joined)

            page_breaks = [
                br for br in document.findall(f".//{{{W_NS}}}br")
                if br.get(f"{{{W_NS}}}type") == "page"
            ]
            self.assertEqual(len(page_breaks), 1)

    def test_validate_export_docx_reports_expected_summary(self) -> None:
        module = _load_module()
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_json = tmp / "sample.json"
            output_docx = tmp / "sample.docx"
            attachment_path = tmp / "incident.png"
            attachment_path.write_bytes(b"png")
            self._write_sample_json(
                input_json,
                day="2026-04-11",
                channel="general",
                channel_id="C1",
                attachment_local=str(attachment_path),
            )
            module.render_channel_day_docx(input_json, output_docx)

            summary = validator.inspect_docx(output_docx)

            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["issues"], [])
            self.assertEqual(summary["page_break_count"], 0)
            self.assertEqual(summary["hyperlink_count"], 1)
            self.assertTrue(summary["contains_reply_badge"])
            self.assertTrue(summary["contains_local_source_note"])
            self.assertIn("ReplyMeta", summary["style_ids"])

    def test_validate_export_docx_flags_missing_parts(self) -> None:
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_docx = Path(tmpdir) / "broken.docx"
            with zipfile.ZipFile(broken_docx, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", b"test")

            summary = validator.inspect_docx(broken_docx)

            self.assertEqual(summary["status"], "invalid")
            self.assertTrue(any(issue.startswith("missing_part:word/document.xml") for issue in summary["issues"]))

    def test_validate_export_docx_flags_broken_internal_relationship_target(self) -> None:
        module = _load_module()
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_json = tmp / "sample.json"
            output_docx = tmp / "sample.docx"
            self._write_sample_json(input_json, day="2026-04-11", channel="general", channel_id="C1")
            module.render_channel_day_docx(input_json, output_docx)

            with zipfile.ZipFile(output_docx, "r") as zf:
                rels = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
            first_rel = rels.find(f".//{{{PKG_REL_NS}}}Relationship")
            assert first_rel is not None
            first_rel.set("TargetMode", "Internal")
            first_rel.set("Target", "media/missing.png")
            _rewrite_docx_part(
                output_docx,
                "word/_rels/document.xml.rels",
                ET.tostring(rels, encoding="utf-8", xml_declaration=True),
            )

            summary = validator.inspect_docx(output_docx)

            self.assertEqual(summary["status"], "invalid")
            self.assertIn(
                "relationship_missing_target_part:word/_rels/document.xml.rels:word/media/missing.png",
                summary["issues"],
            )

    def test_validate_export_docx_flags_broken_content_type_override(self) -> None:
        module = _load_module()
        validator = _load_validator_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_json = tmp / "sample.json"
            output_docx = tmp / "sample.docx"
            self._write_sample_json(input_json, day="2026-04-11", channel="general", channel_id="C1")
            module.render_channel_day_docx(input_json, output_docx)

            with zipfile.ZipFile(output_docx, "r") as zf:
                content_types = ET.fromstring(zf.read("[Content_Types].xml"))
            ET.SubElement(
                content_types,
                "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                {
                    "PartName": "/word/missing-part.xml",
                    "ContentType": "application/xml",
                },
            )
            _rewrite_docx_part(
                output_docx,
                "[Content_Types].xml",
                ET.tostring(content_types, encoding="utf-8", xml_declaration=True),
            )

            summary = validator.inspect_docx(output_docx)

            self.assertEqual(summary["status"], "invalid")
            self.assertIn("content_type_override_missing_part:word/missing-part.xml", summary["issues"])


if __name__ == "__main__":
    unittest.main()
