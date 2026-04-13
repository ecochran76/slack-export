from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from slack_mirror.core import db

HOSTED_AUTH_COOKIE_NAME = "slack_mirror_hosted_session"
PASSWORD_HASH_ITERATIONS = 600_000
HOSTED_AUTH_SESSION_DAYS = 30


@dataclass(frozen=True)
class FrontendAuthConfig:
    enabled: bool
    allow_registration: bool
    cookie_name: str
    cookie_secure_mode: str
    session_days: int


@dataclass(frozen=True)
class FrontendAuthSession:
    authenticated: bool
    user_id: int | None = None
    username: str | None = None
    display_name: str | None = None
    session_id: int | None = None
    auth_source: str = "none"
    expires_at: str | None = None


@dataclass(frozen=True)
class FrontendAuthIssueResult:
    payload: FrontendAuthSession
    session_token: str


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def frontend_auth_config(raw_config: dict[str, Any]) -> FrontendAuthConfig:
    service_cfg = raw_config.get("service") or {}
    auth_cfg = service_cfg.get("auth") or {}
    cookie_name = str(auth_cfg.get("cookie_name") or HOSTED_AUTH_COOKIE_NAME).strip() or HOSTED_AUTH_COOKIE_NAME
    secure_mode = str(auth_cfg.get("cookie_secure_mode") or "").strip().lower()
    if not secure_mode:
        if "cookie_secure" in auth_cfg:
            secure_mode = "always" if _parse_bool(auth_cfg.get("cookie_secure"), False) else "never"
        else:
            secure_mode = "auto"
    if secure_mode not in {"auto", "always", "never"}:
        secure_mode = "auto"
    session_days_value = auth_cfg.get("session_days", HOSTED_AUTH_SESSION_DAYS)
    try:
        session_days = max(1, int(session_days_value))
    except (TypeError, ValueError):
        session_days = HOSTED_AUTH_SESSION_DAYS
    return FrontendAuthConfig(
        enabled=_parse_bool(auth_cfg.get("enabled"), False),
        allow_registration=_parse_bool(auth_cfg.get("allow_registration"), True),
        cookie_name=cookie_name,
        cookie_secure_mode=secure_mode,
        session_days=session_days,
    )


def _password_hash(password: str, salt: str, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    )
    return base64.urlsafe_b64encode(digest).decode("ascii")


def make_password_hash(password: str, *, iterations: int = PASSWORD_HASH_ITERATIONS) -> tuple[str, str, int]:
    salt = secrets.token_urlsafe(16)
    return _password_hash(password, salt, iterations), salt, int(iterations)


def verify_password(password: str, *, password_hash: str, password_salt: str, password_iterations: int) -> bool:
    expected = _password_hash(password, password_salt, password_iterations)
    return hmac.compare_digest(expected, password_hash)


def _normalize_username(value: str) -> str:
    return db.normalize_auth_username(value)


def _require_nonempty_password(password: str) -> str:
    cleaned = str(password or "")
    if len(cleaned) < 8:
        raise ValueError("password must be at least 8 characters")
    return cleaned


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_frontend_auth_session(
    conn,
    *,
    user_id: int,
    username: str,
    display_name: str | None,
    auth_source: str,
    session_days: int,
) -> FrontendAuthIssueResult:
    session_token = secrets.token_urlsafe(32)
    expires_at = (_utcnow() + timedelta(days=max(1, int(session_days)))).isoformat()
    session_row = db.create_auth_session(
        conn,
        user_id=user_id,
        token_hash=_session_token_hash(session_token),
        auth_source=auth_source,
        expires_at=expires_at,
    )
    return FrontendAuthIssueResult(
        payload=FrontendAuthSession(
            authenticated=True,
            user_id=user_id,
            username=username,
            display_name=display_name,
            session_id=int(session_row["id"]),
            auth_source=auth_source,
            expires_at=str(session_row["expires_at"]),
        ),
        session_token=session_token,
    )


def register_frontend_user(
    conn,
    *,
    username: str,
    password: str,
    display_name: str | None,
    session_days: int,
) -> FrontendAuthIssueResult:
    normalized = _normalize_username(username)
    if not normalized:
        raise ValueError("username is required")
    if db.get_auth_user_by_username(conn, normalized) is not None:
        raise ValueError("username already exists")
    password_hash, password_salt, password_iterations = make_password_hash(_require_nonempty_password(password))
    user_row = db.create_auth_user(conn, username=normalized, display_name=display_name)
    db.upsert_auth_local_credential(
        conn,
        user_id=int(user_row["id"]),
        password_hash=password_hash,
        password_salt=password_salt,
        password_iterations=password_iterations,
    )
    return issue_frontend_auth_session(
        conn,
        user_id=int(user_row["id"]),
        username=str(user_row["username"]),
        display_name=str(user_row["display_name"] or "") or None,
        auth_source="local_password",
        session_days=session_days,
    )


def login_frontend_user(
    conn,
    *,
    username: str,
    password: str,
    session_days: int,
) -> FrontendAuthIssueResult:
    normalized = _normalize_username(username)
    user_row = db.get_auth_user_by_username(conn, normalized)
    if user_row is None:
        raise ValueError("invalid username or password")
    credential = db.get_auth_local_credential(conn, int(user_row["id"]))
    if credential is None:
        raise ValueError("invalid username or password")
    if not verify_password(
        _require_nonempty_password(password),
        password_hash=str(credential["password_hash"]),
        password_salt=str(credential["password_salt"]),
        password_iterations=int(credential["password_iterations"]),
    ):
        raise ValueError("invalid username or password")
    return issue_frontend_auth_session(
        conn,
        user_id=int(user_row["id"]),
        username=str(user_row["username"]),
        display_name=str(user_row["display_name"] or "") or None,
        auth_source="local_password",
        session_days=session_days,
    )


def resolve_frontend_auth_session(conn, *, session_token: str | None) -> FrontendAuthSession:
    token = str(session_token or "").strip()
    if not token:
        return FrontendAuthSession(authenticated=False)
    row = db.get_auth_session_by_token_hash(conn, _session_token_hash(token))
    if row is None:
        return FrontendAuthSession(authenticated=False)
    if row["revoked_at"]:
        return FrontendAuthSession(authenticated=False)
    expires_at = str(row["expires_at"] or "").strip()
    if not expires_at:
        return FrontendAuthSession(authenticated=False)
    try:
        expires_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return FrontendAuthSession(authenticated=False)
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=UTC)
    if expires_dt <= _utcnow():
        db.revoke_auth_session(conn, token_hash=_session_token_hash(token))
        return FrontendAuthSession(authenticated=False)
    db.touch_auth_session(conn, token_hash=_session_token_hash(token))
    return FrontendAuthSession(
        authenticated=True,
        user_id=int(row["user_id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"] or "") or None,
        session_id=int(row["id"]),
        auth_source=str(row["auth_source"] or "local_password"),
        expires_at=expires_at,
    )


def logout_frontend_user(conn, *, session_token: str | None) -> None:
    token = str(session_token or "").strip()
    if not token:
        return
    db.revoke_auth_session(conn, token_hash=_session_token_hash(token))


def list_frontend_auth_sessions(conn, *, user_id: int) -> list[dict[str, Any]]:
    rows = db.list_auth_sessions_for_user(conn, user_id=user_id)
    sessions: list[dict[str, Any]] = []
    now = _utcnow()
    for row in rows:
        expires_at = str(row["expires_at"] or "").strip() or None
        expired = False
        if expires_at:
            try:
                expires_dt = datetime.fromisoformat(expires_at)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=UTC)
                expired = expires_dt <= now
            except ValueError:
                expired = False
        sessions.append(
            {
                "session_id": int(row["id"]),
                "auth_source": str(row["auth_source"] or "local_password"),
                "created_at": str(row["created_at"] or ""),
                "last_seen_at": str(row["last_seen_at"] or "") or None,
                "expires_at": expires_at,
                "revoked_at": str(row["revoked_at"] or "") or None,
                "active": row["revoked_at"] is None and not expired,
                "expired": expired,
            }
        )
    return sessions


def revoke_frontend_auth_session(conn, *, user_id: int, session_id: int) -> bool:
    return db.revoke_auth_session_by_id_for_user(conn, user_id=user_id, session_id=session_id)
