from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


BUILTIN_RETRIEVAL_PROFILES: dict[str, dict[str, Any]] = {
    "baseline": {
        "description": "Release-safe hybrid retrieval with the built-in local hash embedding baseline.",
        "mode": "hybrid",
        "model": "local-hash-128",
        "semantic_provider": {"type": "local_hash"},
        "weights": {"lexical": 0.6, "semantic": 0.4, "semantic_scale": 10.0},
        "rerank": False,
        "rerank_top_n": 50,
        "rerank_provider": {"type": "heuristic"},
        "experimental": False,
    },
    "local-bge": {
        "description": "Local sentence-transformers semantic retrieval with BAAI/bge-m3.",
        "mode": "hybrid",
        "model": "BAAI/bge-m3",
        "semantic_provider": {"type": "sentence_transformers"},
        "weights": {"lexical": 0.45, "semantic": 0.55, "semantic_scale": 10.0},
        "rerank": False,
        "rerank_top_n": 50,
        "rerank_provider": {"type": "heuristic"},
        "experimental": True,
    },
    "local-bge-rerank": {
        "description": "Local BGE retrieval plus the experimental local CrossEncoder reranker.",
        "mode": "hybrid",
        "model": "BAAI/bge-m3",
        "semantic_provider": {"type": "sentence_transformers"},
        "weights": {"lexical": 0.45, "semantic": 0.55, "semantic_scale": 10.0},
        "rerank": True,
        "rerank_top_n": 50,
        "rerank_provider": {
            "type": "sentence_transformers",
            "model": "BAAI/bge-reranker-v2-m3",
        },
        "experimental": True,
    },
}


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    description: str
    mode: str
    model: str
    semantic_provider: dict[str, Any]
    weights: dict[str, float]
    rerank: bool
    rerank_top_n: int
    rerank_provider: dict[str, Any]
    experimental: bool = False
    source: str = "builtin"

    @property
    def lexical_weight(self) -> float:
        return float(self.weights.get("lexical", 0.6))

    @property
    def semantic_weight(self) -> float:
        return float(self.weights.get("semantic", 0.4))

    @property
    def semantic_scale(self) -> float:
        return float(self.weights.get("semantic_scale", 10.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "model": self.model,
            "semantic_provider": dict(self.semantic_provider),
            "weights": dict(self.weights),
            "rerank": self.rerank,
            "rerank_top_n": self.rerank_top_n,
            "rerank_provider": dict(self.rerank_provider),
            "experimental": self.experimental,
            "source": self.source,
        }


def list_retrieval_profiles(config: dict[str, Any] | None = None) -> list[RetrievalProfile]:
    profiles: list[RetrievalProfile] = []
    for name in sorted(_merged_profile_maps(config)):
        profiles.append(resolve_retrieval_profile(config, name))
    return profiles


def resolve_retrieval_profile(config: dict[str, Any] | None, name: str | None) -> RetrievalProfile:
    profile_name = str(name or "baseline").strip() or "baseline"
    merged = _merged_profile_maps(config)
    if profile_name not in merged:
        available = ", ".join(sorted(merged))
        raise ValueError(f"Unknown retrieval profile '{profile_name}'. Available profiles: {available}")
    raw = merged[profile_name]
    return _profile_from_mapping(profile_name, raw)


def config_with_retrieval_profile(config: dict[str, Any] | None, profile: RetrievalProfile) -> dict[str, Any]:
    data = copy.deepcopy(config or {})
    search_cfg = data.setdefault("search", {})
    semantic_cfg = search_cfg.setdefault("semantic", {})
    semantic_cfg["model"] = profile.model
    semantic_cfg["mode_default"] = profile.mode
    semantic_cfg["provider"] = dict(profile.semantic_provider)
    semantic_cfg["weights"] = dict(profile.weights)

    rerank_cfg = search_cfg.setdefault("rerank", {})
    rerank_cfg["provider"] = dict(profile.rerank_provider)
    return data


def _merged_profile_maps(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    merged = {name: copy.deepcopy(value) for name, value in BUILTIN_RETRIEVAL_PROFILES.items()}
    configured = ((config or {}).get("search") or {}).get("retrieval_profiles") or {}
    if not isinstance(configured, dict):
        return merged
    for name, override in configured.items():
        profile_name = str(name).strip()
        if not profile_name or not isinstance(override, dict):
            continue
        base = copy.deepcopy(merged.get(profile_name, {}))
        merged[profile_name] = _deep_merge(base, override)
    return merged


def _profile_from_mapping(name: str, raw: dict[str, Any]) -> RetrievalProfile:
    weights_raw = raw.get("weights") or raw.get("semantic_weights") or {}
    weights = {
        "lexical": float(weights_raw.get("lexical", 0.6)),
        "semantic": float(weights_raw.get("semantic", 0.4)),
        "semantic_scale": float(weights_raw.get("semantic_scale", 10.0)),
    }
    semantic_provider = raw.get("semantic_provider") or raw.get("provider") or {"type": "local_hash"}
    rerank_provider = raw.get("rerank_provider") or {"type": "heuristic"}
    return RetrievalProfile(
        name=name,
        description=str(raw.get("description") or ""),
        mode=str(raw.get("mode") or "hybrid"),
        model=str(raw.get("model") or raw.get("model_id") or "local-hash-128"),
        semantic_provider=dict(semantic_provider) if isinstance(semantic_provider, dict) else {"type": str(semantic_provider)},
        weights=weights,
        rerank=_config_bool(raw.get("rerank"), default=False),
        rerank_top_n=int(raw.get("rerank_top_n") or raw.get("rerank_top_k") or 50),
        rerank_provider=dict(rerank_provider) if isinstance(rerank_provider, dict) else {"type": str(rerank_provider)},
        experimental=_config_bool(raw.get("experimental"), default=False),
        source=str(raw.get("source") or ("configured" if name not in BUILTIN_RETRIEVAL_PROFILES else "builtin")),
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(dict(base[key]), value)
        else:
            base[key] = copy.deepcopy(value)
    if "source" not in base:
        base["source"] = "configured"
    return base


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
