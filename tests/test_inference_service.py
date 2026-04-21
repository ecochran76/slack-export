from __future__ import annotations

from http.server import ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from slack_mirror.search.embeddings import build_embedding_provider
from slack_mirror.search.rerankers import build_reranker_provider
from slack_mirror.service.inference import InferenceService, make_inference_handler, probe_inference_server, run_inference_server


class InferenceServiceTests(unittest.TestCase):
    def _server(self):
        config = {
            "search": {
                "inference": {
                    "semantic_provider": {"type": "local_hash"},
                    "rerank_provider": {"type": "heuristic"},
                }
            }
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_inference_handler(InferenceService(config)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2.0)
        return f"http://{host}:{port}/"

    def test_http_embedding_provider_uses_inference_server(self):
        url = self._server()
        provider = build_embedding_provider({"search": {"semantic": {"provider": {"type": "http", "url": url}}}})

        vectors = provider.embed_texts(["gateway outage", "catering invoice"], model_id="local-hash-128")

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 128)
        self.assertNotEqual(vectors[0], vectors[1])

    def test_http_reranker_provider_uses_inference_server(self):
        url = self._server()
        provider = build_reranker_provider({"search": {"rerank": {"provider": {"type": "http", "url": url}}}})

        scores = provider.score(
            query="gateway outage recovery",
            documents=["gateway outage with recovery notes", "monthly catering invoice"],
        )

        self.assertEqual(len(scores), 2)
        self.assertGreater(scores[0], scores[1])

    def test_probe_inference_server_smoke_checks_embeddings_and_rerank(self):
        url = self._server()

        probe = probe_inference_server(url=url, smoke=True, embedding_model="local-hash-128")

        self.assertTrue(probe["available"])
        self.assertEqual(probe["health"]["service"], "slack-mirror-inference")
        self.assertEqual(probe["runtime"]["embedding_smoke"]["dimensions"], 128)
        self.assertEqual(probe["runtime"]["rerank_smoke"]["documents"], 2)

    def test_bge_model_request_falls_back_to_sentence_transformers_provider(self):
        class FakeSentenceProvider:
            name = "fake_sentence_transformers"

            def embed_texts(self, texts, *, model_id):
                self.model_id = model_id
                return [[float(index), 1.0] for index, _ in enumerate(texts)]

        with patch("slack_mirror.service.inference.SentenceTransformersEmbeddingProvider", FakeSentenceProvider):
            service = InferenceService({"search": {"semantic": {"provider": {"type": "local_hash"}}}})
            response = service.handle(
                {
                    "action": "embed_texts",
                    "model_id": "BAAI/bge-m3",
                    "texts": ["gateway outage", "catering invoice"],
                }
            )

        self.assertTrue(response["ok"])
        self.assertEqual(response["embeddings"], [[0.0, 1.0], [1.0, 1.0]])

    def test_inference_server_rejects_non_loopback_bind(self):
        with self.assertRaisesRegex(ValueError, "loopback only"):
            run_inference_server(bind="0.0.0.0", port=0, config_path=None)


if __name__ == "__main__":
    unittest.main()
