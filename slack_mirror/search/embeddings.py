from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

DEFAULT_EMBEDDING_MODEL_ID = "local-hash-128"
_LOCAL_HASH_PREFIX = "local-hash-"
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class EmbeddingModelSpec:
    provider_id: str
    model_id: str
    dimensions: int


def normalize_embedding_model_id(model_id: str | None) -> str:
    value = (model_id or "").strip()
    return value or DEFAULT_EMBEDDING_MODEL_ID


def resolve_embedding_model(model_id: str | None) -> EmbeddingModelSpec:
    resolved = normalize_embedding_model_id(model_id)
    if resolved.startswith(_LOCAL_HASH_PREFIX):
        dims_raw = resolved[len(_LOCAL_HASH_PREFIX) :]
        try:
            dims = int(dims_raw)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid local hash embedding model id: {resolved}") from exc
        if dims <= 0:
            raise ValueError(f"invalid local hash embedding size: {resolved}")
        return EmbeddingModelSpec(provider_id="local_hash", model_id=resolved, dimensions=dims)
    raise ValueError(f"unsupported embedding model: {resolved}")


def embed_text(text: str, *, model_id: str | None = None) -> list[float]:
    spec = resolve_embedding_model(model_id)
    if spec.provider_id == "local_hash":
        return _embed_text_local_hash(text, dim=spec.dimensions)
    raise ValueError(f"unsupported embedding provider: {spec.provider_id}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _embed_text_local_hash(text: str, *, dim: int) -> list[float]:
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        slot = int.from_bytes(digest, "little") % dim
        vec[slot] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec
