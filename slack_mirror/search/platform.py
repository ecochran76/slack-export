from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SearchDocument:
    channel_id: str
    channel_name: str | None
    ts: str
    user_id: str | None
    text: str | None
    subtype: str | None
    thread_ts: str | None
    edited_ts: str | None
    deleted: int


class CorpusAdapter(Protocol):
    def lexical_candidates(
        self,
        *,
        workspace_id: int,
        where_sql: str,
        params: list[Any],
        fts_sql: str,
        fts_params: list[Any],
        candidate_limit: int,
        fallback_without_fts: bool,
    ) -> list[dict[str, Any]]: ...

    def semantic_candidates(
        self,
        *,
        workspace_id: int,
        where_sql: str,
        params: list[Any],
        model_id: str,
        candidate_limit: int,
    ) -> list[dict[str, Any]]: ...
