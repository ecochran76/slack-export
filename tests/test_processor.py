import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, insert_event, upsert_workspace
from slack_mirror.service.processor import process_pending_events, run_processor_loop


class ProcessorTests(unittest.TestCase):
    def test_process_pending_message_event(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            payload = {
                "event_id": "E1",
                "event_time": 123,
                "event": {"type": "message", "channel": "C1", "ts": "1.1", "text": "hello", "user": "U1"},
            }
            insert_event(conn, ws_id, "E1", "123", "message", payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 1)
            msg_count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            self.assertEqual(msg_count, 1)
            journal = conn.execute("SELECT event_type, actor_user_id, channel_id FROM child_event_journal").fetchone()
            self.assertEqual(journal["event_type"], "slack.message.created")
            self.assertEqual(journal["actor_user_id"], "U1")
            self.assertEqual(journal["channel_id"], "C1")

    def test_process_message_changed_and_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            changed_payload = {
                "event_id": "E2",
                "event_time": 124,
                "event": {
                    "type": "message",
                    "subtype": "message_changed",
                    "channel": "C1",
                    "message": {"ts": "2.2", "text": "edited", "user": "U1"},
                },
            }
            deleted_payload = {
                "event_id": "E3",
                "event_time": 125,
                "event": {
                    "type": "message",
                    "subtype": "message_deleted",
                    "channel": "C1",
                    "deleted_ts": "2.2",
                },
            }
            insert_event(conn, ws_id, "E2", "124", "message", changed_payload)
            insert_event(conn, ws_id, "E3", "125", "message", deleted_payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 2)

            deleted_flag = conn.execute(
                "SELECT deleted FROM messages WHERE workspace_id = ? AND channel_id = ? AND ts = ?",
                (ws_id, "C1", "2.2"),
            ).fetchone()["deleted"]
            self.assertEqual(deleted_flag, 1)
            journal_types = [
                row["event_type"]
                for row in conn.execute("SELECT event_type FROM child_event_journal ORDER BY event_type").fetchall()
            ]
            self.assertEqual(journal_types, ["slack.message.changed", "slack.message.deleted"])

    def test_process_member_join_leave(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            join_payload = {
                "event_id": "E5",
                "event_time": 127,
                "event": {"type": "member_joined_channel", "channel": "C2", "user": "U2"},
            }
            leave_payload = {
                "event_id": "E6",
                "event_time": 128,
                "event": {"type": "member_left_channel", "channel": "C2", "user": "U2"},
            }
            insert_event(conn, ws_id, "E5", "127", "member_joined_channel", join_payload)
            insert_event(conn, ws_id, "E6", "128", "member_left_channel", leave_payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 2)

            member_count = conn.execute("SELECT COUNT(*) AS c FROM channel_members").fetchone()["c"]
            self.assertEqual(member_count, 0)
            journal_types = [
                row["event_type"]
                for row in conn.execute("SELECT event_type FROM child_event_journal ORDER BY event_type").fetchall()
            ]
            self.assertEqual(journal_types, ["slack.channel.member_joined", "slack.channel.member_left"])

    def test_process_reaction_and_user_profile_events_into_child_journal(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            reaction_payload = {
                "event_id": "E7",
                "event_time": 129,
                "event": {
                    "type": "reaction_added",
                    "user": "U3",
                    "reaction": "eyes",
                    "item": {"type": "message", "channel": "C3", "ts": "3.3"},
                },
            }
            profile_payload = {
                "event_id": "E8",
                "event_time": 130,
                "event": {
                    "type": "user_change",
                    "user": {
                        "id": "U4",
                        "name": "baker",
                        "profile": {"display_name": "Baker", "status_text": "in the lab"},
                    },
                },
            }
            insert_event(conn, ws_id, "E7", "129", "reaction_added", reaction_payload)
            insert_event(conn, ws_id, "E8", "130", "user_change", profile_payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 2)
            rows = conn.execute(
                "SELECT event_type, actor_user_id, subject_id, payload_json FROM child_event_journal ORDER BY event_type"
            ).fetchall()
            self.assertEqual([row["event_type"] for row in rows], ["slack.reaction.added", "slack.user.profile.changed"])
            self.assertEqual(rows[0]["actor_user_id"], "U3")
            self.assertEqual(rows[0]["subject_id"], "message|default|C3|3.3")
            self.assertIn('"reaction": "eyes"', rows[0]["payload_json"])
            self.assertEqual(rows[1]["actor_user_id"], "U4")
            self.assertIn('"statusText": "in the lab"', rows[1]["payload_json"])

    def test_run_processor_loop(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            payload = {
                "event_id": "E4",
                "event_time": 126,
                "event": {"type": "message", "channel": "C9", "ts": "9.9", "text": "loop", "user": "U9"},
            }
            insert_event(conn, ws_id, "E4", "126", "message", payload)

            result = run_processor_loop(conn, ws_id, limit=10, interval_seconds=0.01, max_cycles=2)
            self.assertGreaterEqual(result["cycles"], 2)
            self.assertEqual(result["processed"], 1)


if __name__ == "__main__":
    unittest.main()
