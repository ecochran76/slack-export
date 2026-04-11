from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "export_channel_day_docx.py"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_channel_day_docx", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ExportDocxTests(unittest.TestCase):
    def test_render_channel_day_docx_writes_expected_package_and_content(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_json = tmp / "sample.json"
            output_docx = tmp / "sample.docx"
            attachment_path = tmp / "incident.png"
            attachment_path.write_bytes(b"png")
            payload = {
                "workspace": "default",
                "channel": "general",
                "channel_id": "C1",
                "day": "2026-04-11",
                "tz": "America/Chicago",
                "messages": [
                    {
                        "ts": "10.0",
                        "human_ts": "2026-04-11 10:00:00 CDT",
                        "user_id": "U1",
                        "user_label": "Eric (U1)",
                        "text": "Launch roadmap\nQ4 milestone",
                        "thread_ts": None,
                        "deleted": False,
                        "attachments": [
                            {
                                "name": "incident.png",
                                "mimetype": "image/png",
                                "local_path": str(attachment_path),
                                "permalink": None,
                            }
                        ],
                    },
                    {
                        "ts": "10.1",
                        "human_ts": "2026-04-11 10:05:00 CDT",
                        "user_id": "U2",
                        "user_label": "Alicia (U2)",
                        "text": "Reply detail",
                        "thread_ts": "10.0",
                        "deleted": False,
                        "attachments": [],
                    },
                ],
            }
            input_json.write_text(json.dumps(payload), encoding="utf-8")

            module.render_channel_day_docx(input_json, output_docx)

            self.assertTrue(output_docx.exists())
            with zipfile.ZipFile(output_docx, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("_rels/.rels", names)
                self.assertIn("word/document.xml", names)
                self.assertIn("word/_rels/document.xml.rels", names)
                self.assertIn("word/styles.xml", names)

                document = ET.fromstring(zf.read("word/document.xml"))
                rels = ET.fromstring(zf.read("word/_rels/document.xml.rels"))

            text_values = [elem.text or "" for elem in document.findall(f".//{{{W_NS}}}t")]
            joined = "\n".join(text_values)
            self.assertIn("default / #general", joined)
            self.assertIn("Launch roadmap", joined)
            self.assertIn("Q4 milestone", joined)
            self.assertIn("[THREAD REPLY] ", joined)
            self.assertIn("Reply detail", joined)
            self.assertIn("incident.png (image/png)", joined)

            indents = document.findall(f".//{{{W_NS}}}pPr/{{{W_NS}}}ind")
            self.assertTrue(any(ind.get(f"{{{W_NS}}}left") == "720" for ind in indents))

            hyperlink_rels = [
                rel
                for rel in rels.findall(f".//{{{PKG_REL_NS}}}Relationship")
                if rel.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
            ]
            self.assertEqual(len(hyperlink_rels), 1)
            self.assertTrue(hyperlink_rels[0].attrib.get("Target", "").startswith("file://"))


if __name__ == "__main__":
    unittest.main()
