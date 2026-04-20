import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_derived_text, upsert_message, upsert_user, upsert_workspace
from slack_mirror.search.corpus import search_corpus
from slack_mirror.search.derived_text import search_derived_text, search_derived_text_semantic
from slack_mirror.search.keyword import reindex_messages_fts, search_messages
from slack_mirror.search.profiles import config_with_retrieval_profile, list_retrieval_profiles, resolve_retrieval_profile
from slack_mirror.search.rerankers import (
    SentenceTransformersCrossEncoderRerankerProvider,
    build_reranker_provider,
    probe_reranker_provider,
    rerank_rows,
)
from slack_mirror.sync.embeddings import process_embedding_jobs
from slack_mirror.sync.derived_text import backfill_derived_text_chunk_embeddings


class SearchTests(unittest.TestCase):
    def test_retrieval_profiles_resolve_builtin_and_configured_overrides(self):
        baseline = resolve_retrieval_profile({}, "baseline")
        self.assertEqual(baseline.model, "local-hash-128")
        self.assertFalse(baseline.rerank)

        local_bge = resolve_retrieval_profile({}, "local-bge")
        self.assertEqual(local_bge.model, "BAAI/bge-m3")
        self.assertEqual(local_bge.semantic_provider["type"], "sentence_transformers")

        configured = resolve_retrieval_profile(
            {
                "search": {
                    "retrieval_profiles": {
                        "local-bge": {
                            "weights": {"lexical": 0.2, "semantic": 0.8},
                            "semantic_provider": {"type": "sentence_transformers", "device": "cuda"},
                        },
                        "custom": {
                            "mode": "semantic",
                            "model": "custom-model",
                            "semantic_provider": {"type": "command", "command": "embed"},
                        },
                    }
                }
            },
            "local-bge",
        )
        self.assertEqual(configured.lexical_weight, 0.2)
        self.assertEqual(configured.semantic_weight, 0.8)
        self.assertEqual(configured.semantic_provider["device"], "cuda")
        self.assertIn("custom", [profile.name for profile in list_retrieval_profiles({"search": {"retrieval_profiles": {"custom": {"model": "x"}}}})])

        overlay = config_with_retrieval_profile({}, configured)
        self.assertEqual(overlay["search"]["semantic"]["model"], "BAAI/bge-m3")
        self.assertEqual(overlay["search"]["semantic"]["provider"]["device"], "cuda")

    def test_reranker_provider_seam_scores_rows(self):
        class FakeReranker:
            name = "fake_reranker"

            def score(self, *, query, documents):
                return [10.0 if "target" in doc else 0.0 for doc in documents]

        rows = [
            {"text": "ordinary result", "_score": 5.0},
            {"text": "target result", "_score": 1.0},
        ]

        reranked = rerank_rows(rows, query="target", top_n=2, provider=FakeReranker())

        self.assertEqual(reranked[0]["text"], "target result")
        self.assertEqual(reranked[0]["_rerank_provider"], "fake_reranker")
        self.assertGreater(reranked[0]["_rerank_score"], reranked[1]["_rerank_score"])
        self.assertEqual(build_reranker_provider({"search": {"rerank": {"provider": {"type": "none"}}}}).name, "none")

    def test_cross_encoder_reranker_uses_sentence_transformers_provider(self):
        calls = {}

        class FakeCrossEncoder:
            def __init__(self, model_id, **kwargs):
                calls["model_id"] = model_id
                calls["kwargs"] = kwargs

            def predict(self, pairs, *, batch_size, show_progress_bar):
                calls["pairs"] = pairs
                calls["batch_size"] = batch_size
                calls["show_progress_bar"] = show_progress_bar
                return [0.1, 2.5]

        fake_module = types.ModuleType("sentence_transformers")
        fake_module.CrossEncoder = FakeCrossEncoder

        with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            provider = SentenceTransformersCrossEncoderRerankerProvider(
                model_id="BAAI/bge-reranker-v2-m3",
                device="cpu",
                batch_size=2,
            )
            scores = provider.score(query="gateway outage", documents=["ordinary", "gateway outage recovery"])

        self.assertEqual(scores, [0.1, 2.5])
        self.assertEqual(calls["model_id"], "BAAI/bge-reranker-v2-m3")
        self.assertEqual(calls["kwargs"]["device"], "cpu")
        self.assertEqual(calls["batch_size"], 2)
        self.assertEqual(calls["pairs"][1], ("gateway outage", "gateway outage recovery"))

    def test_reranker_provider_probe_reports_smoke_and_unsupported_provider(self):
        smoke = probe_reranker_provider(
            {},
            smoke_query="target",
            smoke_documents=["target result", "ordinary result"],
        )
        self.assertTrue(smoke["available"])
        self.assertEqual(smoke["provider_type"], "heuristic")
        self.assertTrue(smoke["runtime"]["smoke"]["ok"])
        self.assertEqual(smoke["runtime"]["smoke"]["documents"], 2)

        unsupported = probe_reranker_provider({"search": {"rerank": {"provider": {"type": "bogus"}}}})
        self.assertFalse(unsupported["available"])
        self.assertIn("unsupported_provider_type", unsupported["issues"])

    def test_build_reranker_provider_supports_cross_encoder_config(self):
        provider = build_reranker_provider(
            {
                "search": {
                    "rerank": {
                        "provider": {
                            "type": "sentence_transformers",
                            "model": "BAAI/bge-reranker-v2-m3",
                            "device": "cuda",
                            "batch_size": 4,
                        }
                    }
                }
            }
        )

        self.assertIsInstance(provider, SentenceTransformersCrossEncoderRerankerProvider)
        self.assertEqual(provider.model_id, "BAAI/bge-reranker-v2-m3")
        self.assertEqual(provider.device, "cuda")
        self.assertEqual(provider.batch_size, 4)

    def test_search_messages_semantic_uses_provider_routing(self):
        class FakeProvider:
            name = "fake_provider"

            def __init__(self):
                self.mapping = {
                    "gateway outage cooper": [1.0, 0.0],
                    "OpenClaw gateway is down on cooper": [1.0, 0.0],
                    "normal deployment completed successfully": [0.0, 1.0],
                }

            def embed_texts(self, texts, *, model_id):
                return [list(self.mapping.get(text, [0.0, 0.0])) for text in texts]

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "alerts"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "30.0", "text": "OpenClaw gateway is down on cooper", "user": "U1"})
            upsert_message(conn, ws_id, "C1", {"ts": "31.0", "text": "normal deployment completed successfully", "user": "U1"})

            provider = FakeProvider()
            process_embedding_jobs(conn, workspace_id=ws_id, model_id="BAAI/bge-m3", limit=20, provider=provider)
            rows = search_messages(
                conn,
                workspace_id=ws_id,
                query="gateway outage cooper",
                limit=5,
                mode="semantic",
                model_id="BAAI/bge-m3",
                provider=provider,
            )
            self.assertGreaterEqual(len(rows), 1)
            self.assertIn("OpenClaw gateway is down on cooper", rows[0]["text"])

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

    def test_search_messages_rerank_uses_provider(self):
        class FakeReranker:
            name = "fake_reranker"

            def score(self, *, query, documents):
                return [10.0 if "second" in doc else 0.0 for doc in documents]

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "1.0", "text": "deploy first candidate", "user": "U1"})
            upsert_message(conn, ws_id, "C1", {"ts": "2.0", "text": "deploy second candidate", "user": "U1"})

            rows = search_messages(
                conn,
                workspace_id=ws_id,
                query="deploy",
                limit=2,
                rerank=True,
                rerank_top_n=2,
                reranker_provider=FakeReranker(),
            )

            self.assertEqual(rows[0]["text"], "deploy second candidate")
            self.assertEqual(rows[0]["_rerank_provider"], "fake_reranker")

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

    def test_search_derived_text_returns_deep_matching_chunk(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F2', 'playbook.txt', 'Playbook', 'text/plain', '/tmp/playbook.txt', '{}')
                """,
                (ws_id,),
            )
            long_text = (
                ("intro status update " * 80)
                + "\n\n"
                + ("deployment background " * 80)
                + "\n\n"
                + ("catastrophic rollback signature " * 40)
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F2",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text=long_text,
                media_type="text/plain",
                local_path="/tmp/playbook.txt",
            )
            rows = search_derived_text(conn, workspace_id=ws_id, query="catastrophic rollback", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_label"], "Playbook")
            self.assertIn("catastrophic rollback", str(rows[0]["matched_text"]))
            self.assertGreaterEqual(int(rows[0]["chunk_index"]), 1)

    def test_search_derived_text_semantic_uses_shared_embedding_model(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F3', 'deploy.txt', 'Deploy Notes', 'text/plain', '/tmp/deploy.txt', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F3",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="deployment checklist for cooper gateway outage recovery",
                media_type="text/plain",
                local_path="/tmp/deploy.txt",
            )

            class FakeProvider:
                name = "fake_provider"

                def embed_texts(self, texts, *, model_id):
                    out = []
                    for text in texts:
                        normalized = str(text or "").lower()
                        if "gateway outage recovery" in normalized or "deployment checklist for cooper gateway outage recovery" in normalized:
                            out.append([1.0, 0.0])
                        else:
                            out.append([0.0, 1.0])
                    return out

            provider = FakeProvider()
            backfill_derived_text_chunk_embeddings(
                conn,
                workspace_id=ws_id,
                model_id="BAAI/bge-m3",
                limit=50,
                derivation_kind="attachment_text",
                provider=provider,
            )

            rows = search_derived_text_semantic(
                conn,
                workspace_id=ws_id,
                query="gateway outage recovery",
                limit=5,
                model_id="BAAI/bge-m3",
                provider=provider,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_label"], "Deploy Notes")
            self.assertGreater(float(rows[0]["_semantic_score"]), 0.0)

    def test_search_corpus_combines_messages_and_derived_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "10.0", "text": "incident review follow-up", "user": "U1"})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F1', 'scan.pdf', 'Incident PDF', 'application/pdf', '/tmp/scan.pdf', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F1",
                derivation_kind="ocr_text",
                extractor="tesseract_pdf",
                text="incident review appendix and findings",
                media_type="application/pdf",
                local_path="/tmp/scan.pdf",
                metadata={"origin": "test"},
            )

            rows = search_corpus(conn, workspace_id=ws_id, query="incident review", limit=10, mode="hybrid")
            self.assertGreaterEqual(len(rows), 2)
            kinds = {row["result_kind"] for row in rows}
            self.assertIn("message", kinds)
            self.assertIn("derived_text", kinds)
            self.assertTrue(any("_hybrid_score" in row for row in rows))
            self.assertEqual(rows[0]["_explain"]["fusion_method"], "weighted")
            self.assertIn("scores", rows[0]["_explain"])

    def test_search_corpus_supports_rrf_fusion_explain_metadata(self):
        class FakeProvider:
            name = "fake_provider"

            def embed_texts(self, texts, *, model_id):
                vectors = []
                for text in texts:
                    normalized = str(text or "").lower()
                    vectors.append([1.0, 0.0] if "semantic winner" in normalized or normalized == "alpha" else [0.0, 1.0])
                return vectors

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "10.0", "text": "alpha alpha lexical top", "user": "U1"})
            upsert_message(conn, ws_id, "C1", {"ts": "11.0", "text": "semantic winner", "user": "U1"})
            process_embedding_jobs(conn, workspace_id=ws_id, model_id="fake-model", limit=20, provider=FakeProvider())

            rows = search_corpus(
                conn,
                workspace_id=ws_id,
                query="alpha",
                limit=5,
                mode="hybrid",
                model_id="fake-model",
                lexical_weight=0.1,
                semantic_weight=10.0,
                fusion_method="rrf",
                message_embedding_provider=FakeProvider(),
            )

            self.assertEqual(rows[0]["text"], "semantic winner")
            self.assertEqual(rows[0]["_fusion_method"], "rrf")
            self.assertEqual(rows[0]["_semantic_rank"], 1)
            self.assertIsNone(rows[0]["_lexical_rank"])
            self.assertEqual(rows[0]["_explain"]["fusion_method"], "rrf")
            self.assertEqual(rows[0]["_explain"]["ranks"]["semantic"], 1)

    def test_search_corpus_can_rerank_fused_candidates(self):
        class FakeReranker:
            name = "fake_reranker"

            def score(self, *, query, documents):
                return [10.0 if "appendix target" in doc else 0.0 for doc in documents]

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "10.0", "text": "incident ordinary message", "user": "U1"})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F9', 'appendix.txt', 'Appendix', 'text/plain', '/tmp/appendix.txt', '{}')
                """,
                (ws_id,),
            )
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F9",
                derivation_kind="attachment_text",
                extractor="utf8_text",
                text="incident appendix target",
                media_type="text/plain",
                local_path="/tmp/appendix.txt",
            )

            rows = search_corpus(
                conn,
                workspace_id=ws_id,
                query="incident",
                limit=5,
                mode="lexical",
                rerank=True,
                rerank_top_n=5,
                reranker_provider=FakeReranker(),
            )

            self.assertEqual(rows[0]["result_kind"], "derived_text")
            self.assertEqual(rows[0]["source_id"], "F9")
            self.assertEqual(rows[0]["_rerank_provider"], "fake_reranker")
            self.assertIn("_rerank_score", rows[0])

    def test_search_corpus_uses_chunk_snippet_for_derived_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
                VALUES (?, 'F3', 'ocr.pdf', 'OCR Report', 'application/pdf', '/tmp/ocr.pdf', '{}')
                """,
                (ws_id,),
            )
            long_text = ("cover page " * 100) + "\n\n" + ("unusual payment discrepancy " * 50)
            upsert_derived_text(
                conn,
                workspace_id=ws_id,
                source_kind="file",
                source_id="F3",
                derivation_kind="ocr_text",
                extractor="tesseract_pdf",
                text=long_text,
                media_type="application/pdf",
                local_path="/tmp/ocr.pdf",
            )

            rows = search_corpus(conn, workspace_id=ws_id, query="payment discrepancy", limit=5, mode="hybrid")
            derived = next(row for row in rows if row["result_kind"] == "derived_text")
            self.assertIn("payment discrepancy", str(derived["snippet_text"]))

    def test_search_corpus_sets_workspace_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_user(conn, ws_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
            upsert_message(conn, ws_id, "C1", {"ts": "12.0", "text": "cross workspace metadata check", "user": "U1"})

            rows = search_corpus(conn, workspace_id=ws_id, workspace_name="default", query="metadata check", limit=5, mode="lexical")
            self.assertEqual(rows[0]["workspace"], "default")
            self.assertEqual(rows[0]["workspace_id"], ws_id)


if __name__ == "__main__":
    unittest.main()
