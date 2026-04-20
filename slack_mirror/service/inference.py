from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from slack_mirror.core.config import load_config
from slack_mirror.search.embeddings import (
    LocalHashEmbeddingProvider,
    build_embedding_provider,
)
from slack_mirror.search.rerankers import (
    HeuristicRerankerProvider,
    build_reranker_provider,
)

DEFAULT_INFERENCE_BIND = "127.0.0.1"
DEFAULT_INFERENCE_PORT = 8791
LOOPBACK_BINDS = {"127.0.0.1", "localhost", "::1"}


def _provider_type(config: dict[str, Any]) -> str:
    return str(config.get("type") or "").strip().lower()


def build_inference_embedding_provider(config: dict[str, Any] | None = None):
    search_cfg = dict((config or {}).get("search") or {})
    inference_cfg = dict(search_cfg.get("inference") or {})
    provider_cfg = inference_cfg.get("semantic_provider")
    if isinstance(provider_cfg, dict):
        return build_embedding_provider({"search": {"semantic": {"provider": provider_cfg}}})

    semantic_cfg = dict(search_cfg.get("semantic") or {})
    configured_provider = dict(semantic_cfg.get("provider") or {})
    if _provider_type(configured_provider) in {"", "local_hash", "local", "hash"}:
        return LocalHashEmbeddingProvider()
    if _provider_type(configured_provider) in {"http", "command"}:
        configured_provider = {"type": "sentence_transformers"}
    return build_embedding_provider({"search": {"semantic": {"provider": configured_provider}}})


def build_inference_reranker_provider(config: dict[str, Any] | None = None):
    search_cfg = dict((config or {}).get("search") or {})
    inference_cfg = dict(search_cfg.get("inference") or {})
    provider_cfg = inference_cfg.get("rerank_provider")
    if isinstance(provider_cfg, dict):
        return build_reranker_provider({"search": {"rerank": {"provider": provider_cfg}}})

    rerank_cfg = dict(search_cfg.get("rerank") or {})
    configured_provider = dict(rerank_cfg.get("provider") or {}) if isinstance(rerank_cfg.get("provider"), dict) else {}
    if _provider_type(configured_provider) in {"http", "command"}:
        configured_provider = {"type": "sentence_transformers"}
    if not configured_provider:
        return HeuristicRerankerProvider()
    return build_reranker_provider({"search": {"rerank": {"provider": configured_provider}}})


class InferenceService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.embedding_provider = build_inference_embedding_provider(self.config)
        self.reranker_provider = build_inference_reranker_provider(self.config)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "slack-mirror-inference",
            "embedding_provider": getattr(self.embedding_provider, "name", self.embedding_provider.__class__.__name__),
            "reranker_provider": getattr(self.reranker_provider, "name", self.reranker_provider.__class__.__name__),
        }

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        if action == "embed_texts":
            texts = payload.get("texts")
            if not isinstance(texts, list):
                raise ValueError("embed_texts requires a texts array")
            model_id = str(payload.get("model_id") or "local-hash-128")
            vectors = self.embedding_provider.embed_texts([str(text or "") for text in texts], model_id=model_id)
            return {"ok": True, "embeddings": vectors}
        if action == "rerank_score":
            documents = payload.get("documents")
            if not isinstance(documents, list):
                raise ValueError("rerank_score requires a documents array")
            query = str(payload.get("query") or "")
            scores = self.reranker_provider.score(query=query, documents=[str(document or "") for document in documents])
            return {"ok": True, "scores": [float(score) for score in scores]}
        raise ValueError(f"unsupported inference action: {action}")


def make_inference_handler(service: InferenceService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SlackMirrorInference/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - avoid noisy stderr in tests
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in {"", "/health"}:
                self._send_json({"ok": False, "error": "not_found"}, status=404)
                return
            self._send_json(service.health())

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                payload = json.loads(body or "{}")
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                response = service.handle(payload)
                self._send_json(response)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=400)

        def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def run_inference_server(*, bind: str, port: int, config_path: str | None = None) -> None:
    if str(bind).strip().lower() not in LOOPBACK_BINDS:
        raise ValueError("slack-mirror inference service must bind to loopback only")
    config = load_config(config_path).data
    service = InferenceService(config)
    server = ThreadingHTTPServer((bind, int(port)), make_inference_handler(service))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def inference_endpoint_from_config(config: dict[str, Any] | None = None) -> tuple[str, int, str]:
    inference_cfg = dict(((config or {}).get("search") or {}).get("inference") or {})
    bind = str(inference_cfg.get("bind") or DEFAULT_INFERENCE_BIND)
    port = int(inference_cfg.get("port") or DEFAULT_INFERENCE_PORT)
    url = str(inference_cfg.get("url") or f"http://{bind}:{port}/")
    return bind, port, url


def _post_json(url: str, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    req = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")


def probe_inference_server(
    *,
    url: str,
    smoke: bool = False,
    embedding_model: str = "BAAI/bge-m3",
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "available": False,
        "issues": [],
        "runtime": {},
    }
    try:
        with urllib_request.urlopen(url.rstrip("/") + "/health", timeout=timeout_s) as resp:
            health = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        payload["health"] = health
        payload["available"] = bool(health.get("ok"))
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        payload["issues"].append("health_failed")
        payload["runtime"]["health_error"] = str(exc)
        return payload

    if smoke and payload["available"]:
        try:
            embed = _post_json(
                url,
                {
                    "action": "embed_texts",
                    "model_id": embedding_model,
                    "texts": ["semantic search probe", "gateway outage on cooper"],
                },
                timeout_s=timeout_s,
            )
            vectors = embed.get("embeddings") if isinstance(embed, dict) else None
            payload["runtime"]["embedding_smoke"] = {
                "ok": bool(embed.get("ok")) if isinstance(embed, dict) else False,
                "texts": len(vectors) if isinstance(vectors, list) else 0,
                "dimensions": len(vectors[0]) if isinstance(vectors, list) and vectors else 0,
            }
            rerank = _post_json(
                url,
                {
                    "action": "rerank_score",
                    "query": "gateway outage recovery",
                    "documents": ["gateway outage on cooper with recovery notes", "monthly catering invoice"],
                },
                timeout_s=timeout_s,
            )
            scores = rerank.get("scores") if isinstance(rerank, dict) else None
            payload["runtime"]["rerank_smoke"] = {
                "ok": bool(rerank.get("ok")) if isinstance(rerank, dict) else False,
                "documents": len(scores) if isinstance(scores, list) else 0,
                "scores": [round(float(score), 6) for score in scores] if isinstance(scores, list) else [],
            }
        except Exception as exc:  # noqa: BLE001
            payload["available"] = False
            payload["issues"].append("smoke_failed")
            payload["runtime"]["smoke_error"] = str(exc)
    return payload
