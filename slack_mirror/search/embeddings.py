from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

DEFAULT_EMBEDDING_MODEL_ID = "local-hash-128"
DEFAULT_SEMANTIC_PROVIDER_TYPE = "local_hash"
_LOCAL_HASH_PREFIX = "local-hash-"
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class EmbeddingProvider(Protocol):
    name: str

    def embed_texts(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class EmbeddingModelSpec:
    provider_id: str
    model_id: str
    dimensions: int | None


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
    if resolved in {"bge-m3", "BAAI/bge-m3"}:
        return EmbeddingModelSpec(provider_id="sentence_transformers", model_id="BAAI/bge-m3", dimensions=1024)
    return EmbeddingModelSpec(provider_id="external", model_id=resolved, dimensions=None)


def provider_name(provider: EmbeddingProvider) -> str:
    return str(getattr(provider, "name", provider.__class__.__name__))


def probe_embedding_provider(
    config: dict[str, Any] | None = None,
    *,
    model_id: str | None = None,
    smoke_texts: list[str] | None = None,
) -> dict[str, Any]:
    search_cfg = dict((config or {}).get("search") or {})
    semantic_cfg = dict(search_cfg.get("semantic") or {})
    provider_cfg = dict(semantic_cfg.get("provider") or {})
    resolved_model = resolve_embedding_model(model_id or semantic_cfg.get("model"))
    provider_type = str(provider_cfg.get("type") or DEFAULT_SEMANTIC_PROVIDER_TYPE).strip().lower() or DEFAULT_SEMANTIC_PROVIDER_TYPE

    probe: dict[str, Any] = {
        "provider_type": provider_type,
        "model": resolved_model.model_id,
        "resolved_provider_id": resolved_model.provider_id,
        "dimensions": resolved_model.dimensions,
        "available": True,
        "issues": [],
        "runtime": {},
    }

    if provider_type in {"", "local_hash", "local", "hash"}:
        pass
    elif provider_type in {"sentence_transformers", "sentence-transformer", "local_sentence_transformers"}:
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
                    names: list[str] = []
                    for idx in range(device_count):
                        try:
                            names.append(str(torch.cuda.get_device_name(idx)))
                        except Exception:
                            names.append(f"cuda:{idx}")
                    probe["runtime"]["cuda_devices"] = names
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
    elif provider_type == "command":
        command_value = provider_cfg.get("command")
        if isinstance(command_value, str):
            command = shlex.split(command_value)
        elif isinstance(command_value, list):
            command = [str(part) for part in command_value]
        else:
            command = []
        probe["runtime"]["command"] = command
        if not command:
            probe["available"] = False
            probe["issues"].append("command_missing")
    elif provider_type == "http":
        url = str(provider_cfg.get("url") or "").strip()
        probe["runtime"]["url"] = url
        if not url:
            probe["available"] = False
            probe["issues"].append("url_missing")
    else:
        probe["available"] = False
        probe["issues"].append("unsupported_provider_type")

    if smoke_texts and probe["available"]:
        try:
            provider = build_embedding_provider(config)
            t0 = time.perf_counter()
            vectors = provider.embed_texts([str(text or "") for text in smoke_texts], model_id=resolved_model.model_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            probe["runtime"]["smoke"] = {
                "ok": True,
                "texts": len(smoke_texts),
                "dimensions": len(vectors[0]) if vectors else 0,
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


def embed_text(text: str, *, model_id: str | None = None, provider: EmbeddingProvider | None = None) -> list[float]:
    return embed_texts([text], model_id=model_id, provider=provider)[0]


def embed_texts(
    texts: list[str],
    *,
    model_id: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[list[float]]:
    resolved = normalize_embedding_model_id(model_id)
    active_provider = provider or _DEFAULT_PROVIDER
    return active_provider.embed_texts([str(text or "") for text in texts], model_id=resolved)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


class LocalHashEmbeddingProvider:
    name = "local_hash"

    def embed_texts(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        spec = resolve_embedding_model(model_id)
        if spec.provider_id != "local_hash" or spec.dimensions is None:
            raise ValueError(f"Local hash provider does not support model_id={model_id}")
        return [_embed_text_local_hash(text, dim=spec.dimensions) for text in texts]


class SentenceTransformersEmbeddingProvider:
    name = "sentence_transformers"

    def __init__(
        self,
        *,
        device: str | None = None,
        batch_size: int = 16,
        normalize_embeddings: bool = True,
        trust_remote_code: bool = False,
        cache_folder: str | None = None,
    ):
        self.device = None if device is None else (str(device).strip() or None)
        self.batch_size = int(batch_size)
        self.normalize_embeddings = bool(normalize_embeddings)
        self.trust_remote_code = bool(trust_remote_code)
        self.cache_folder = None if cache_folder is None else (str(cache_folder).strip() or None)
        self._loaded_model_name: str | None = None
        self._loaded_model: Any = None

    def _load_model(self, model_name: str):
        if self._loaded_model is not None and self._loaded_model_name == model_name:
            return self._loaded_model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency-optional
            raise RuntimeError(
                "sentence_transformers provider requires the 'sentence-transformers' package and a compatible local torch install"
            ) from exc
        kwargs: dict[str, Any] = {
            "trust_remote_code": self.trust_remote_code,
        }
        if self.device:
            kwargs["device"] = self.device
        if self.cache_folder:
            kwargs["cache_folder"] = self.cache_folder
        self._loaded_model = SentenceTransformer(model_name, **kwargs)
        self._loaded_model_name = model_name
        return self._loaded_model

    def embed_texts(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        spec = resolve_embedding_model(model_id)
        if spec.provider_id == "local_hash":
            return _DEFAULT_PROVIDER.embed_texts(texts, model_id=model_id)
        model = self._load_model(spec.model_id)
        vectors = model.encode(
            texts,
            batch_size=max(1, self.batch_size),
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [list(map(float, row.tolist() if hasattr(row, "tolist") else row)) for row in vectors]


class CommandEmbeddingProvider:
    def __init__(self, command: list[str]):
        if not command:
            raise ValueError("command embedding provider requires a non-empty command")
        self.command = [str(part) for part in command]
        self.name = f"command:{Path(self.command[0]).name}"

    def embed_texts(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        payload = {
            "action": "embed_texts",
            "model_id": str(model_id),
            "texts": [str(text or "") for text in texts],
        }
        result = subprocess.run(
            self.command,
            check=False,
            capture_output=True,
            text=True,
            input=json.dumps(payload),
        )
        if result.returncode != 0:
            raise RuntimeError(f"embedding provider command failed: {result.stderr.strip()}")
        try:
            response = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("embedding provider command returned invalid JSON") from exc
        if not response.get("ok", True):
            raise RuntimeError(str(response.get("error") or "embedding_provider_error"))
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("embedding provider command returned invalid embeddings payload")
        return [[float(value) for value in row] for row in embeddings]


class HttpEmbeddingProvider:
    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        bearer_token_env: str | None = None,
        timeout_s: float = 120.0,
    ):
        normalized_url = str(url or "").strip()
        if not normalized_url:
            raise ValueError("http embedding provider requires a non-empty url")
        parsed = urllib_parse.urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("http embedding provider requires an absolute http(s) url")
        self.url = normalized_url
        self.headers = {str(k): str(v) for k, v in (headers or {}).items()}
        self.bearer_token_env = None if bearer_token_env is None else (str(bearer_token_env).strip() or None)
        self.timeout_s = float(timeout_s)
        self.name = f"http:{parsed.netloc}"

    def embed_texts(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        payload = {
            "action": "embed_texts",
            "model_id": str(model_id),
            "texts": [str(text or "") for text in texts],
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json", **self.headers}
        if self.bearer_token_env:
            token = os.environ.get(self.bearer_token_env, "").strip()
            if not token:
                raise RuntimeError("embedding provider auth token is missing")
            headers.setdefault("Authorization", f"Bearer {token}")
        req = urllib_request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http embedding provider error {exc.code}: {body.strip()}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"http embedding provider connection failed: {exc.reason}") from exc
        try:
            response = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("http embedding provider returned invalid JSON") from exc
        if not response.get("ok", True):
            raise RuntimeError(str(response.get("error") or "embedding_provider_error"))
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("http embedding provider returned invalid embeddings payload")
        return [[float(value) for value in row] for row in embeddings]


_DEFAULT_PROVIDER = LocalHashEmbeddingProvider()


def build_embedding_provider(config: dict[str, Any] | None = None) -> EmbeddingProvider:
    search_cfg = dict((config or {}).get("search") or {})
    semantic_cfg = dict(search_cfg.get("semantic") or {})
    provider_cfg = dict(semantic_cfg.get("provider") or {})
    provider_type = str(provider_cfg.get("type") or DEFAULT_SEMANTIC_PROVIDER_TYPE).strip().lower()

    if provider_type in {"", "local_hash", "local", "hash"}:
        return _DEFAULT_PROVIDER
    if provider_type in {"sentence_transformers", "sentence-transformer", "local_sentence_transformers"}:
        return SentenceTransformersEmbeddingProvider(
            device=provider_cfg.get("device"),
            batch_size=int(provider_cfg.get("batch_size") or 16),
            normalize_embeddings=_config_bool(provider_cfg.get("normalize_embeddings"), default=True),
            trust_remote_code=_config_bool(provider_cfg.get("trust_remote_code"), default=False),
            cache_folder=provider_cfg.get("cache_folder"),
        )
    if provider_type == "command":
        command_value = provider_cfg.get("command")
        if isinstance(command_value, str):
            command = shlex.split(command_value)
        elif isinstance(command_value, list):
            command = [str(part) for part in command_value]
        else:
            command = []
        return CommandEmbeddingProvider(command)
    if provider_type == "http":
        headers_value = provider_cfg.get("headers")
        headers = headers_value if isinstance(headers_value, dict) else {}
        return HttpEmbeddingProvider(
            str(provider_cfg.get("url") or ""),
            headers=headers,
            bearer_token_env=provider_cfg.get("bearer_token_env"),
            timeout_s=float(provider_cfg.get("timeout_s") or 120.0),
        )
    raise ValueError(f"Unsupported semantic embedding provider type: {provider_type}")


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


def _nvidia_smi_probe() -> list[dict[str, Any]] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    rows: list[dict[str, Any]] = []
    for line in (result.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        name, total, used, free, driver_version = parts
        rows.append(
            {
                "name": name,
                "memory_total_mib": int(total),
                "memory_used_mib": int(used),
                "memory_free_mib": int(free),
                "driver_version": driver_version,
            }
        )
    return rows or None


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
