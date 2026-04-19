from array import array
import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_message, upsert_workspace
from slack_mirror.search.embeddings import build_embedding_provider, embed_text, resolve_embedding_model
from slack_mirror.sync.embeddings import backfill_message_embeddings, process_embedding_jobs


class EmbeddingSyncTests(unittest.TestCase):
    def test_build_embedding_provider_supports_sentence_transformers_config(self):
        provider = build_embedding_provider(
            {
                "search": {
                    "semantic": {
                        "provider": {
                            "type": "sentence_transformers",
                            "batch_size": 8,
                            "normalize_embeddings": True,
                        }
                    }
                }
            }
        )
        self.assertEqual(provider.name, "sentence_transformers")

    def test_embedding_model_resolution_supports_local_hash_ids(self):
        default_spec = resolve_embedding_model(None)
        self.assertEqual(default_spec.model_id, "local-hash-128")
        self.assertEqual(default_spec.dimensions, 128)

        alt_spec = resolve_embedding_model("local-hash-64")
        self.assertEqual(alt_spec.provider_id, "local_hash")
        self.assertEqual(alt_spec.dimensions, 64)

        vec = embed_text("deploy pipeline failed", model_id="local-hash-64")
        self.assertEqual(len(vec), 64)

    def test_backfill_and_process_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            upsert_message(conn, ws_id, "C123", {"ts": "1.1", "text": "deploy pipeline failed", "user": "U1"})
            upsert_message(conn, ws_id, "C123", {"ts": "1.2", "text": "fixed deploy workflow", "user": "U2"})

            jobs = process_embedding_jobs(conn, workspace_id=ws_id, limit=20)
            self.assertEqual(jobs["jobs"], 2)
            self.assertEqual(jobs["errored"], 0)

            emb_count = conn.execute("SELECT COUNT(*) AS c FROM message_embeddings").fetchone()["c"]
            self.assertEqual(emb_count, 2)

            bf = backfill_message_embeddings(conn, workspace_id=ws_id, limit=10)
            self.assertEqual(bf["scanned"], 2)
            self.assertEqual(bf["embedded"], 0)
            self.assertEqual(bf["skipped"], 2)

    def test_process_embedding_jobs_uses_configured_provider(self):
        class FakeProvider:
            name = "fake_provider"

            def embed_texts(self, texts, *, model_id):
                return [[1.0, 0.0] for _ in texts]

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            upsert_message(conn, ws_id, "C123", {"ts": "1.1", "text": "deploy pipeline failed", "user": "U1"})

            jobs = process_embedding_jobs(conn, workspace_id=ws_id, model_id="BAAI/bge-m3", limit=20, provider=FakeProvider())
            self.assertEqual(jobs["jobs"], 1)
            row = conn.execute(
                "SELECT embedding_blob FROM message_embeddings WHERE workspace_id = ? AND channel_id = ? AND ts = ? AND model_id = ?",
                (ws_id, "C123", "1.1", "BAAI/bge-m3"),
            ).fetchone()
            self.assertIsNotNone(row)
            vec = array("f")
            vec.frombytes(row["embedding_blob"])
            self.assertEqual(vec.tolist(), [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
