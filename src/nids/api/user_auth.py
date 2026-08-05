"""User login + session authentication for the dashboard (see
`nids.api.users` for the bootstrap CLI). A second, distinct credential
type from `nids.api.agent_auth`'s device credentials -- a browser
operator proving who they are is a different problem from a live-capture
agent proving which machine it is, and the two stay independently
revocable and independently shaped.

Sessions mirror `DeviceCredential`'s shape exactly: a random opaque token
handed to the caller once, only its SHA-256 hash ever persisted (see
`nids.api.store.SessionRecord`) -- a database read alone can never leak a
usable session token, the same guarantee `agent_auth.py` already gives
device credentials.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.engine import Engine

from nids.api.store import (
    UserRecordView,
    _get_user_credentials_by_username,
    create_user,
    get_session_by_token_hash,
    get_user_by_id,
    revoke_session_by_token_hash,
)
from nids.api.store import (
    create_session as _store_create_session,
)

VALID_ROLES = ("analyst", "admin")


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def register_user(engine: Engine, username: str, password: str, role: str) -> UserRecordView:
    """Used only by `nids.api.users`' `create-user` CLI -- there is no
    HTTP self-signup route (see docs/AUTH.md)."""
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {VALID_ROLES!r}, got {role!r}")
    return create_user(engine, username=username, password_hash=hash_password(password), role=role)


def authenticate_user(engine: Engine, username: str, password: str) -> UserRecordView | None:
    """Used only by `POST /auth/login`. Constant-shape on failure --
    unknown username and wrong password both just return `None`, so a
    login response never distinguishes 'no such user' from 'wrong
    password'."""
    credentials = _get_user_credentials_by_username(engine, username)
    if credentials is None:
        return None
    password_hash, user = credentials
    if not verify_password(password, password_hash):
        return None
    return user


@dataclass(frozen=True)
class RawSessionToken:
    token: str  # raw bearer token -- returned once, never persisted in the clear
    user: UserRecordView


def create_session(engine: Engine, user_id: str, ttl_seconds: int) -> RawSessionToken:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    _store_create_session(engine, user_id=user_id, token_hash=_hash_token(raw_token), expires_at=expires_at)
    user = get_user_by_id(engine, user_id)
    return RawSessionToken(token=raw_token, user=user)


def authenticate_session(engine: Engine, token: str) -> UserRecordView | None:
    session = get_session_by_token_hash(engine, _hash_token(token))
    if session is None or session.revoked:
        return None
    # SQLite/SQLAlchemy round-trips DateTime columns as naive (see
    # SessionRecord.expires_at) even though it was written from an
    # aware datetime -- compare against a naive UTC "now" to match,
    # not datetime.now(timezone.utc) directly (raises TypeError).
    if session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    return get_user_by_id(engine, session.user_id)


def revoke_session(engine: Engine, token: str) -> None:
    revoke_session_by_token_hash(engine, _hash_token(token))
