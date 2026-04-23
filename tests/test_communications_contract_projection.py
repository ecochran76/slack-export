from __future__ import annotations

import unittest

from scripts.validate_selected_results_communications_contract import (
    _default_schema_dir,
    map_selected_results_payload,
    validate_contract,
)


class CommunicationsContractProjectionTests(unittest.TestCase):
    def _assert_contract_valid(self, mapped: dict) -> None:
        schema_dir = _default_schema_dir()
        if not schema_dir.exists():
            self.skipTest(f"communications schema directory not present: {schema_dir}")
        try:
            errors = validate_contract(mapped, schema_dir)
        except SystemExit as exc:
            if "Missing jsonschema" in str(exc):
                return
            raise
        self.assertEqual(errors, [])

    def test_maps_slack_message_selected_results_to_provider_neutral_contract(self):
        payload = {
            "schema_version": 1,
            "kind": "selected-results",
            "generated_at": "2026-04-22T15:00:00Z",
            "producer": {"name": "slack-mirror"},
            "export_id": "selected-default-smoke",
            "title": "Smoke Selection",
            "workspace": "default",
            "workspaces": ["default"],
            "source": {
                "targets": [
                    {
                        "version": 1,
                        "kind": "message",
                        "workspace": "default",
                        "workspace_id": 1,
                        "channel_id": "C123",
                        "ts": "11.0",
                        "selection_label": "default:C123:11.0",
                    }
                ],
                "context_policy": {"before": 1, "after": 1, "include_text": True, "max_text_chars": 4000},
            },
            "item_count": 1,
            "resolved_count": 1,
            "unresolved_count": 0,
            "events": [
                {
                    "schema_version": 1,
                    "id": "slack-message|default|C123|11.0|hit|1|1",
                    "platform": "slack",
                    "kind": "message",
                    "relation": "hit",
                    "selected": True,
                    "exact_hit": True,
                    "thread": {
                        "id": "C123:11.0",
                        "root_ts": "11.0",
                        "native": {"thread_ts": None, "ts": "11.0"},
                    },
                    "timestamp": "1970-01-01T00:00:11Z",
                    "participants": [
                        {"role": "sender", "id": "U1", "display_name": "Eric", "native": {"user_id": "U1"}}
                    ],
                    "subject": "#general",
                    "attachments": [],
                    "derived_text_refs": [],
                    "source_refs": {
                        "workspace": "default",
                        "workspace_id": 1,
                        "channel_id": "C123",
                        "channel_name": "general",
                        "ts": "11.0",
                    },
                    "action_target": {
                        "version": 1,
                        "kind": "message",
                        "workspace": "default",
                        "workspace_id": 1,
                        "channel_id": "C123",
                        "ts": "11.0",
                    },
                    "warnings": [],
                    "text": "selected message",
                }
            ],
            "context_pack": {
                "kind": "search_context_pack",
                "context_policy": {"before": 1, "after": 1, "include_text": True, "max_text_chars": 4000},
                "unresolved": [],
            },
        }

        mapped = map_selected_results_payload(payload)

        self.assertEqual(mapped["kind"], "selected_result_export")
        self.assertEqual(mapped["context_policy"]["before_count"], 1)
        self.assertEqual(mapped["selected_targets"][0]["target_kind"], "slack_message")
        self.assertEqual(mapped["selected_targets"][0]["hit_kind"], "slack_message")
        self.assertEqual(mapped["selected_targets"][0]["service_ids"]["workspace_id"], "1")
        self.assertEqual(mapped["events"][0]["kind"], "slack_message")
        self.assertNotIn("selected", mapped["events"][0])
        self.assertEqual(mapped["events"][0]["participants"][0]["service_participant_id"], "U1")
        self.assertEqual(mapped["events"][0]["thread"]["type"], "thread")
        self.assertEqual(mapped["events"][0]["action_target"]["service_ids"]["channel_id"], "C123")
        self.assertEqual(
            mapped["extensions"]["slack_selected_results"]["kind"],
            "selected-results",
        )
        self._assert_contract_valid(mapped)

    def test_maps_slack_derived_text_selected_results_to_provider_neutral_contract(self):
        payload = {
            "schema_version": 1,
            "kind": "selected-results",
            "generated_at": "2026-04-22T15:00:00Z",
            "producer": {"name": "slack-mirror"},
            "export_id": "selected-default-derived",
            "title": "Derived Selection",
            "workspace": "default",
            "workspaces": ["default"],
            "source": {
                "targets": [
                    {
                        "version": 1,
                        "kind": "derived_text",
                        "id": "derived_text|default|file|F1|ocr_text|tesseract|chunk:0",
                        "workspace": "default",
                        "workspace_id": 1,
                        "derived_text_id": 7,
                        "source_kind": "file",
                        "source_id": "F1",
                        "source_label": "scan.pdf",
                        "derivation_kind": "ocr_text",
                        "extractor": "tesseract",
                        "chunk_index": 0,
                        "selection_label": "default:file:F1",
                    }
                ],
                "context_policy": {"before": 1, "after": 1, "include_text": True, "max_text_chars": 4000},
            },
            "item_count": 1,
            "resolved_count": 1,
            "unresolved_count": 0,
            "events": [
                {
                    "schema_version": 1,
                    "id": "slack-derived-text|default|file|F1|chunk:0|hit|1|1",
                    "platform": "slack",
                    "kind": "derived_text_chunk",
                    "relation": "hit",
                    "selected": True,
                    "exact_hit": True,
                    "thread": None,
                    "timestamp": None,
                    "participants": [],
                    "subject": "scan.pdf",
                    "attachments": [
                        {"kind": "slack_file", "id": "F1", "filename": "scan.pdf", "native": {"file_id": "F1"}}
                    ],
                    "derived_text_refs": [
                        {
                            "source_kind": "file",
                            "source_id": "F1",
                            "source_label": "scan.pdf",
                            "derivation_kind": "ocr_text",
                            "extractor": "tesseract",
                            "media_type": "application/pdf",
                            "language_code": "en",
                            "confidence": None,
                            "chunk_index": 0,
                            "start_offset": 0,
                            "end_offset": 20,
                        }
                    ],
                    "source_refs": {
                        "workspace": "default",
                        "workspace_id": 1,
                        "source_kind": "file",
                        "source_id": "F1",
                        "derived_text_id": 7,
                    },
                    "action_target": {
                        "version": 1,
                        "kind": "derived_text",
                        "id": "derived_text|default|file|F1|ocr_text|tesseract|chunk:0",
                        "workspace": "default",
                        "workspace_id": 1,
                        "derived_text_id": 7,
                        "source_kind": "file",
                        "source_id": "F1",
                        "source_label": "scan.pdf",
                        "derivation_kind": "ocr_text",
                        "extractor": "tesseract",
                        "chunk_index": 0,
                    },
                    "warnings": [],
                    "text": "incident review",
                }
            ],
            "context_pack": {
                "kind": "search_context_pack",
                "context_policy": {"before": 1, "after": 1, "include_text": True, "max_text_chars": 4000},
                "unresolved": [],
            },
        }

        mapped = map_selected_results_payload(payload)

        self.assertEqual(mapped["selected_targets"][0]["target_kind"], "derived_text")
        self.assertEqual(mapped["selected_targets"][0]["hit_kind"], "chunk")
        self.assertEqual(mapped["selected_targets"][0]["service_ids"]["derived_text_id"], "7")
        self.assertEqual(mapped["events"][0]["kind"], "derived_text")
        self.assertEqual(mapped["events"][0]["action_target"]["service_ids"]["derived_text_id"], "7")
        self.assertEqual(mapped["events"][0]["derived_text_refs"][0]["chunk_index"], 0)
        self._assert_contract_valid(mapped)


if __name__ == "__main__":
    unittest.main()
