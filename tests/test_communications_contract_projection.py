import unittest

from scripts.validate_selected_results_communications_contract import map_selected_results_payload


class CommunicationsContractProjectionTests(unittest.TestCase):
    def test_maps_slack_selected_results_to_provider_neutral_contract(self):
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
                        "kind": "message",
                        "workspace": "default",
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
                        "kind": "message",
                        "workspace": "default",
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
        self.assertEqual(mapped["events"][0]["kind"], "slack_message")
        self.assertNotIn("selected", mapped["events"][0])
        self.assertEqual(mapped["events"][0]["participants"][0]["service_participant_id"], "U1")
        self.assertEqual(mapped["events"][0]["thread"]["type"], "thread")
        self.assertEqual(mapped["events"][0]["action_target"]["service_ids"]["channel_id"], "C123")
        self.assertEqual(
            mapped["extensions"]["slack_selected_results"]["kind"],
            "selected-results",
        )


if __name__ == "__main__":
    unittest.main()
