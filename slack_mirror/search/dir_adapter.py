from __future__ import annotations

import math
import shlex
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from typing import Any


@dataclass
class DirDoc:
    path: str
    text: str


def _embed_text_local(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    for tok in shlex.split((text or "").lower().replace("\n", " ")):
        h = blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h, "little") % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _load_docs(root: str, glob: str = "**/*.md", max_chars: int = 12000) -> list[DirDoc]:
    base = Path(root)
    docs: list[DirDoc] = []
    for p in base.glob(glob):
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        docs.append(DirDoc(path=str(p.relative_to(base)), text=txt[:max_chars]))
    return docs


def _snippet(text: str, query: str, max_chars: int = 220) -> str:
    t = " ".join((text or "").split())
    if len(t) <= max_chars:
        return t
    q_terms = [x for x in query.replace('"', " ").split() if ":" not in x and not x.startswith("-")]
    low = t.lower()
    idx = -1
    for term in q_terms:
        i = low.find(term.lower())
        if i >= 0:
            idx = i
            break
    if idx < 0:
        return t[: max_chars - 1] + "…"
    start = max(0, idx - max_chars // 3)
    end = min(len(t), start + max_chars)
    out = t[start:end]
    if start > 0:
        out = "…" + out
    if end < len(t):
        out = out + "…"
    return out


def query_directory(
    *,
    root: str,
    query: str,
    mode: str = "hybrid",
    glob: str = "**/*.md",
    limit: int = 20,
) -> list[dict[str, Any]]:
    docs = _load_docs(root, glob=glob)
    if not docs:
        return []

    q = (query or "").strip()
    terms = [t for t in shlex.split(q) if ":" not in t and not t.startswith("-")]
    neg_terms = [t[1:] for t in shlex.split(q) if t.startswith("-") and len(t) > 1]

    qvec = _embed_text_local(" ".join(terms) if terms else q)
    scored: list[dict[str, Any]] = []
    for d in docs:
        low = d.text.lower()
        if any(nt.lower() in low for nt in neg_terms):
            continue
        term_hits = sum(low.count(t.lower()) for t in terms)
        lex = float(term_hits)
        sem = _cosine(qvec, _embed_text_local(d.text))

        if mode == "lexical":
            final = lex
        elif mode == "semantic":
            final = sem
        else:
            final = (0.6 * lex) + (0.4 * sem * 10.0)

        if final <= 0:
            continue
        scored.append(
            {
                "path": d.path,
                "_score": round(final, 6),
                "_lexical_score": round(lex, 6),
                "_semantic_score": round(sem, 6),
                "snippet": _snippet(d.text, q),
            }
        )

    scored.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    return scored[: max(1, limit)]
