from __future__ import annotations

import importlib.util
import shlex
import time
from typing import Any, Protocol

from slack_mirror.search.embeddings import _nvidia_smi_probe

DEFAULT_RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
DEFAULT_RERANKER_PROVIDER_TYPE = "heuristic"


class RerankerProvider(Protocol):
    name: str

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        """Return one relevance score per document."""


class NoopRerankerProvider:
    name = "none"

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        return [0.0 for _ in documents]


class HeuristicRerankerProvider:
    name = "heuristic"

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        q_terms = [t.lower() for t in shlex.split(query or "") if t and ":" not in t and not t.startswith("-")]
        if not q_terms:
            return [0.0 for _ in documents]

        scores: list[float] = []
        unique_terms = set(q_terms)
        for doc in documents:
            text = (doc or "").lower()
            term_presence = sum(1 for term in unique_terms if term in text)
            density = term_presence / max(1, len(text.split()))
            proximity = 0.0
            for term in unique_terms:
                index = text.find(term)
                if index >= 0:
                    proximity += 1.0 / (1.0 + index)
            scores.append((term_presence * 0.15) + (density * 5.0) + proximity)
        return scores


class SentenceTransformersCrossEncoderRerankerProvider:
    name = "sentence_transformers_cross_encoder"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_RERANKER_MODEL_ID,
        device: str | None = None,
        batch_size: int = 16,
        trust_remote_code: bool = False,
        cache_folder: str | None = None,
    ):
        self.model_id = str(model_id or DEFAULT_RERANKER_MODEL_ID)
        self.device = None if device is None else (str(device).strip() or None)
        self.batch_size = int(batch_size)
        self.trust_remote_code = bool(trust_remote_code)
        self.cache_folder = None if cache_folder is None else (str(cache_folder).strip() or None)
        self._loaded_model: Any = None

    def _load_model(self):
        if self._loaded_model is not None:
            return self._loaded_model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - dependency-optional
            raise RuntimeError(
                "sentence_transformers reranker provider requires the 'sentence-transformers' package and a compatible local torch install"
            ) from exc
        kwargs: dict[str, Any] = {"trust_remote_code": self.trust_remote_code}
        if self.device:
            kwargs["device"] = self.device
        if self.cache_folder:
            kwargs["cache_folder"] = self.cache_folder
        self._loaded_model = CrossEncoder(self.model_id, **kwargs)
        return self._loaded_model

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        model = self._load_model()
        pairs = [(str(query or ""), str(document or "")) for document in documents]
        raw_scores = model.predict(
            pairs,
            batch_size=max(1, self.batch_size),
            show_progress_bar=False,
        )
        values = raw_scores.tolist() if hasattr(raw_scores, "tolist") else raw_scores
        return [float(value) for value in values]


def build_reranker_provider(config: dict[str, Any] | None = None) -> RerankerProvider:
    rerank_cfg = dict(((config or {}).get("search") or {}).get("rerank") or {})
    provider_cfg = rerank_cfg.get("provider")
    if isinstance(provider_cfg, dict):
        provider_type = str(provider_cfg.get("type") or rerank_cfg.get("type") or DEFAULT_RERANKER_PROVIDER_TYPE).strip().lower()
    else:
        provider_cfg = {}
        provider_type = str(rerank_cfg.get("type") or DEFAULT_RERANKER_PROVIDER_TYPE).strip().lower()

    if provider_type in {"", "none", "disabled"}:
        return NoopRerankerProvider()
    if provider_type == "heuristic":
        return HeuristicRerankerProvider()
    if provider_type in {"sentence_transformers", "sentence-transformer", "cross_encoder", "cross-encoder", "sentence_transformers_cross_encoder"}:
        return SentenceTransformersCrossEncoderRerankerProvider(
            model_id=str(provider_cfg.get("model") or provider_cfg.get("model_id") or rerank_cfg.get("model") or DEFAULT_RERANKER_MODEL_ID),
            device=provider_cfg.get("device"),
            batch_size=int(provider_cfg.get("batch_size") or 16),
            trust_remote_code=_config_bool(provider_cfg.get("trust_remote_code"), default=False),
            cache_folder=provider_cfg.get("cache_folder"),
        )
    raise ValueError(f"Unsupported reranker provider type: {provider_type}")


def probe_reranker_provider(
    config: dict[str, Any] | None = None,
    *,
    model_id: str | None = None,
    smoke_query: str | None = None,
    smoke_documents: list[str] | None = None,
) -> dict[str, Any]:
    rerank_cfg = dict(((config or {}).get("search") or {}).get("rerank") or {})
    provider_cfg_raw = rerank_cfg.get("provider")
    provider_cfg = dict(provider_cfg_raw or {}) if isinstance(provider_cfg_raw, dict) else {}
    provider_type = str(provider_cfg.get("type") or rerank_cfg.get("type") or DEFAULT_RERANKER_PROVIDER_TYPE).strip().lower() or DEFAULT_RERANKER_PROVIDER_TYPE
    resolved_model = str(model_id or provider_cfg.get("model") or provider_cfg.get("model_id") or rerank_cfg.get("model") or DEFAULT_RERANKER_MODEL_ID)
    probe: dict[str, Any] = {
        "provider_type": provider_type,
        "model": resolved_model,
        "available": True,
        "issues": [],
        "runtime": {},
    }

    if provider_type in {"", "none", "disabled", "heuristic"}:
        pass
    elif provider_type in {"sentence_transformers", "sentence-transformer", "cross_encoder", "cross-encoder", "sentence_transformers_cross_encoder"}:
        st_available = importlib.util.find_spec("sentence_transformers") is not None
        torch_available = importlib.util.find_spec("torch") is not None
        probe["runtime"]["sentence_transformers_installed"] = st_available
        probe["runtime"]["torch_installed"] = torch_available
        device = provider_cfg.get("device")
        if device is not None and str(device).strip():
            probe["runtime"]["configured_device"] = str(device).strip()
        if not st_available:
            probe["available"] = False
            probe["issues"].append("sentence_transformers_not_installed")
        if not torch_available:
            probe["available"] = False
            probe["issues"].append("torch_not_installed")
        if torch_available:
            try:
                import torch  # type: ignore

                cuda_available = bool(torch.cuda.is_available())
                device_count = int(torch.cuda.device_count()) if cuda_available else 0
                probe["runtime"]["cuda_available"] = cuda_available
                probe["runtime"]["cuda_device_count"] = device_count
                if cuda_available and device_count > 0:
                    probe["runtime"]["cuda_devices"] = [
                        str(torch.cuda.get_device_name(idx)) for idx in range(device_count)
                    ]
                configured_device = str(device or "").strip().lower()
                if configured_device.startswith("cuda") and not cuda_available:
                    probe["available"] = False
                    probe["issues"].append("configured_cuda_unavailable")
            except Exception as exc:  # pragma: no cover
                probe["available"] = False
                probe["issues"].append("torch_probe_failed")
                probe["runtime"]["torch_probe_error"] = str(exc)
        nvidia = _nvidia_smi_probe()
        if nvidia is not None:
            probe["runtime"]["nvidia_smi"] = nvidia
    else:
        probe["available"] = False
        probe["issues"].append("unsupported_provider_type")

    if smoke_query is not None and smoke_documents and probe["available"]:
        try:
            provider = build_reranker_provider(config)
            if isinstance(provider, SentenceTransformersCrossEncoderRerankerProvider):
                provider.model_id = resolved_model
            t0 = time.perf_counter()
            scores = provider.score(query=smoke_query, documents=[str(doc or "") for doc in smoke_documents])
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            probe["runtime"]["smoke"] = {
                "ok": True,
                "documents": len(smoke_documents),
                "scores": [round(float(score), 6) for score in scores],
                "latency_ms": round(elapsed_ms, 3),
            }
        except Exception as exc:
            probe["available"] = False
            probe["issues"].append("smoke_failed")
            probe["runtime"]["smoke"] = {
                "ok": False,
                "error": str(exc),
            }

    return probe


def provider_name(provider: RerankerProvider | None) -> str:
    return str(getattr(provider, "name", "heuristic" if provider is None else provider.__class__.__name__))


def default_row_text(row: dict[str, Any]) -> str:
    return str(row.get("snippet_text") or row.get("matched_text") or row.get("text") or "")


def base_retrieval_score(row: dict[str, Any]) -> float:
    return float(
        row.get("_hybrid_score")
        or row.get("_score")
        or row.get("_semantic_score")
        or row.get("_lexical_score")
        or 0.0
    )


def rerank_rows(
    rows: list[dict[str, Any]],
    *,
    query: str,
    top_n: int,
    provider: RerankerProvider | None = None,
) -> list[dict[str, Any]]:
    if not rows or top_n <= 0:
        return rows

    active_provider = provider or HeuristicRerankerProvider()
    head = rows[:top_n]
    tail = rows[top_n:]
    documents = [default_row_text(row) for row in head]
    scores = active_provider.score(query=query, documents=documents)
    if len(scores) != len(head):
        raise ValueError("reranker provider returned a score count that does not match document count")

    rescored: list[dict[str, Any]] = []
    for row, score in zip(head, scores, strict=True):
        base = base_retrieval_score(row)
        rerank_score = base + float(score)
        rescored.append(
            {
                **row,
                "_rerank_score": round(rerank_score, 6),
                "_rerank_provider": provider_name(active_provider),
            }
        )

    rescored.sort(key=lambda row: float(row.get("_rerank_score") or 0.0), reverse=True)
    return rescored + tail


def _config_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default
