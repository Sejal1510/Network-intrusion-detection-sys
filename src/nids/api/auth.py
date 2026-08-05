"""User login/session HTTP boundary (see `nids.api.user_auth`) and the
`CurrentUserDep`/`OptionalCurrentUserDep`/`require_role` dependencies
every login-gated route in this API imports. A fourth `APIRouter`,
following the exact "one file per route group" norm `history.py`/
`ingest.py`/`broadcast.py` already establish.

`CurrentUserDep` raises `401`, not the `503`/`404` every other `_get_x`
dependency in this codebase raises (see `history.py`'s `DbEngineDep`,
`nids.api.app`'s `ServedEnsembleDep`) -- `401` is a correct new addition
here: those existing dependencies report "this deployment isn't
configured"/"this id doesn't exist," never "you are not who you claim to
be." A missing/invalid `Authorization` header is genuinely a different
failure class.

Unlike the tiny, safely-duplicated `_get_db_engine` (three lines, fine to
copy per module), `CurrentUserDep`/`require_role` are the one real
auth-check in this API and live in exactly one place, imported by every
gated route (`history.py`, `nids.api.devices`) -- duplicating security
logic across files is a liability, not a style matter.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from nids.api.config import ServingConfig
from nids.api.schemas import CurrentUserResponse, LoginRequest, LoginResponse
from nids.api.store import UserRecordView, record_audit_event
from nids.api.user_auth import (
    authenticate_session,
    authenticate_user,
    create_session,
    revoke_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")


def _get_db_engine(request: Request):
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        raise HTTPException(
            status_code=503, detail="No database is configured for this deployment."
        )
    return db_engine


async def _enforce_auth_rate_limit(request: Request) -> None:
    config: ServingConfig = request.app.state.serving_config
    limiter = request.app.state.rate_limiter
    client_host = request.client.host if request.client else "unknown"
    key = f"auth:{client_host}"
    if not await limiter.allow(key, limit=config.auth_rate_limit_per_minute, window_seconds=60):
        logger.warning("Rate limit exceeded: scope=auth client=%s", client_host)
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")


AuthRateLimitDep = Annotated[None, Depends(_enforce_auth_rate_limit)]


def _get_current_user(request: Request) -> UserRecordView:
    db_engine = _get_db_engine(request)
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    user = authenticate_session(db_engine, token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


CurrentUserDep = Annotated[UserRecordView, Depends(_get_current_user)]


def _get_current_user_optional(request: Request) -> UserRecordView | None:
    """For call sites that want an identity if present but must keep
    working anonymously (`nids.api.ingest`'s `pair_exchange` -- pairing
    stays usable from a logged-out browser tab or the live-capture
    agent's CLI, neither of which carries a login session). Deliberately
    a separate function, not `CurrentUserDep` wrapped in a try/except at
    the call site, so "auth is optional here" is visible in the
    function's own signature."""
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        return None
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    return authenticate_session(db_engine, token) if token else None


OptionalCurrentUserDep = Annotated[UserRecordView | None, Depends(_get_current_user_optional)]


def require_role(role: str):
    def _check(current_user: CurrentUserDep) -> UserRecordView:
        if current_user.role != role:
            raise HTTPException(status_code=403, detail=f"Requires the {role!r} role.")
        return current_user

    return Depends(_check)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, _rate_limit: AuthRateLimitDep) -> LoginResponse:
    db_engine = _get_db_engine(request)
    config: ServingConfig = request.app.state.serving_config
    client_host = request.client.host if request.client else "unknown"
    user = authenticate_user(db_engine, payload.username, payload.password)
    if user is None:
        record_audit_event(
            db_engine, event_type="login_failed", actor=client_host, detail=payload.username
        )
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    session = create_session(db_engine, user.id, ttl_seconds=config.session_ttl_seconds)
    record_audit_event(db_engine, event_type="login_succeeded", actor=f"user:{user.username}")
    return LoginResponse(token=session.token, username=user.username, role=user.role)


@router.post("/logout", status_code=204)
def logout(request: Request, current_user: CurrentUserDep) -> None:
    db_engine = _get_db_engine(request)
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    revoke_session(db_engine, token)
    record_audit_event(db_engine, event_type="logout", actor=f"user:{current_user.username}")


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(username=current_user.username, role=current_user.role)
