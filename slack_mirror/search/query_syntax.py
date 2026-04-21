from __future__ import annotations

from dataclasses import dataclass, field
import shlex


MESSAGE_LANE_OPERATOR_PREFIXES = (
    "from:",
    "participant:",
    "user:",
    "in:",
    "channel:",
    "source:",
    "before:",
    "after:",
    "since:",
    "until:",
    "on:",
    "is:",
)

DERIVED_TEXT_LANE_OPERATOR_PREFIXES = (
    "filename:",
    "file:",
    "mime:",
    "extension:",
    "ext:",
    "attachment-type:",
)

ATTACHMENT_TYPE_MIME_PREFIXES = {
    "doc": ("application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml"),
    "document": ("application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml"),
    "image": ("image/",),
    "pdf": ("application/pdf",),
    "spreadsheet": ("application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml"),
    "text": ("text/",),
}


@dataclass(frozen=True)
class DerivedTextQuery:
    positive_terms: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    has_attachment: bool = False
    filename_terms: list[str] = field(default_factory=list)
    mime_terms: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    attachment_types: list[str] = field(default_factory=list)

    @property
    def has_structured_filters(self) -> bool:
        return bool(
            self.has_attachment
            or self.filename_terms
            or self.mime_terms
            or self.extensions
            or self.attachment_types
        )

    @property
    def semantic_text(self) -> str:
        return " ".join(self.positive_terms)


def split_query_tokens(query: str) -> list[str]:
    try:
        return shlex.split(query or "")
    except ValueError:
        return (query or "").split()


def _strip_negation(token: str) -> tuple[bool, str]:
    if token.startswith("-") and len(token) > 1:
        return True, token[1:]
    return False, token


def _field_value(token: str, prefixes: tuple[str, ...]) -> tuple[str, str] | None:
    lowered = token.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return prefix[:-1], token.split(":", 1)[1].strip()
    return None


def _normalize_extension(value: str) -> str:
    return (value or "").strip().lower().lstrip(".")


def parse_derived_text_query(query: str) -> DerivedTextQuery:
    positive_terms: list[str] = []
    negative_terms: list[str] = []
    filename_terms: list[str] = []
    mime_terms: list[str] = []
    extensions: list[str] = []
    attachment_types: list[str] = []
    has_attachment = False

    for raw_token in split_query_tokens(query):
        negated, token = _strip_negation(raw_token)
        if not token:
            continue

        lowered = token.lower()
        if lowered.startswith("has:"):
            value = token.split(":", 1)[1].strip().lower()
            if value in {"attachment", "attachments", "file", "files"}:
                if not negated:
                    has_attachment = True
                continue

        field = _field_value(token, DERIVED_TEXT_LANE_OPERATOR_PREFIXES)
        if field:
            name, value = field
            if not value:
                continue
            if negated:
                negative_terms.append(value)
                continue
            if name in {"filename", "file"}:
                filename_terms.append(value)
            elif name == "mime":
                mime_terms.append(value.lower())
            elif name in {"extension", "ext"}:
                ext = _normalize_extension(value)
                if ext:
                    extensions.append(ext)
            elif name == "attachment-type":
                attachment_types.append(value.lower())
            continue

        if ":" in token:
            continue
        if negated:
            negative_terms.append(token)
        else:
            positive_terms.append(token)

    return DerivedTextQuery(
        positive_terms=positive_terms,
        negative_terms=negative_terms,
        has_attachment=has_attachment,
        filename_terms=filename_terms,
        mime_terms=mime_terms,
        extensions=extensions,
        attachment_types=attachment_types,
    )


def has_message_lane_operator(query: str) -> bool:
    for raw_token in split_query_tokens(query):
        _, token = _strip_negation(raw_token)
        lowered = token.lower()
        if lowered.startswith("has:"):
            value = lowered.split(":", 1)[1].strip()
            if value == "link":
                return True
            continue
        if any(lowered.startswith(prefix) for prefix in MESSAGE_LANE_OPERATOR_PREFIXES):
            return True
    return False


def has_derived_text_lane_operator(query: str) -> bool:
    parsed = parse_derived_text_query(query)
    return parsed.has_structured_filters
