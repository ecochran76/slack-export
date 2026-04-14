from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class RateLimitError(ValueError):
    def __init__(self, message: str, *, retry_after_seconds: int, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.retry_after_seconds = int(max(1, retry_after_seconds))
        self.details = dict(details or {})


@dataclass(frozen=True)
class ServiceError:
    code: str
    message: str
    http_status: int
    mcp_status: int
    retryable: bool
    details: dict[str, Any]

    def envelope(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


def map_service_error(exc: Exception, **details: Any) -> ServiceError:
    message = str(exc)
    merged_details = {key: value for key, value in details.items() if value is not None}

    if isinstance(exc, RateLimitError):
        return ServiceError(
            "RATE_LIMITED",
            message,
            429,
            -32029,
            True,
            {
                **merged_details,
                "retry_after_seconds": exc.retry_after_seconds,
                **exc.details,
            },
        )

    if isinstance(exc, KeyError):
        field = str(exc).strip("'\"")
        return ServiceError(
            "INVALID_ARGUMENT",
            f"{field} is required",
            400,
            -32602,
            False,
            {**merged_details, "field": field},
        )

    if isinstance(exc, ValueError):
        if re.search(r"^Unknown tool:", message):
            return ServiceError("METHOD_NOT_FOUND", message, 404, -32601, False, merged_details)
        if "not found in workspace" in message or "not found in DB" in message or "not found in config" in message:
            return ServiceError("NOT_FOUND", message, 404, -32004, False, merged_details)
        if "ambiguous" in message:
            return ServiceError("AMBIGUOUS_TARGET", message, 409, -32009, False, merged_details)
        if "has no token configured" in message:
            return ServiceError("AUTH_CONFIGURATION_ERROR", message, 400, -32010, False, merged_details)
        if message in {"channel_ref is required", "listener spec requires name"} or message.startswith("Unsupported "):
            return ServiceError("INVALID_ARGUMENT", message, 400, -32602, False, merged_details)
        if message.startswith("Failed to open direct message"):
            return ServiceError("UPSTREAM_ERROR", message, 502, -32011, True, merged_details)
        return ServiceError("INVALID_REQUEST", message, 400, -32000, False, merged_details)

    return ServiceError("INTERNAL_ERROR", message or exc.__class__.__name__, 500, -32603, True, merged_details)
