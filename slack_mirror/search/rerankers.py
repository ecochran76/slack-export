from __future__ import annotations

import shlex
from typing import Any, Protocol


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


def build_reranker_provider(config: dict[str, Any] | None = None) -> RerankerProvider:
    rerank_cfg = dict(((config or {}).get("search") or {}).get("rerank") or {})
    provider_cfg = rerank_cfg.get("provider")
    if isinstance(provider_cfg, dict):
        provider_type = str(provider_cfg.get("type") or rerank_cfg.get("type") or "heuristic").strip().lower()
    else:
        provider_type = str(rerank_cfg.get("type") or "heuristic").strip().lower()

    if provider_type in {"", "none", "disabled"}:
        return NoopRerankerProvider()
    if provider_type == "heuristic":
        return HeuristicRerankerProvider()
    raise ValueError(f"Unsupported reranker provider type: {provider_type}")


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
