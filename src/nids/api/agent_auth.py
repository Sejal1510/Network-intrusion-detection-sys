"""Device pairing and authentication for the live capture agent
(`nids.agent`). Two distinct credentials, each with a purpose-matched
lifetime:

- A short-lived (~10 minute) **pairing token**: self-contained and
  stateless (HMAC-signed via `itsdangerous`, already installed) -- no
  database row to create or expire-and-clean-up. Issuing one works
  identically whether or not a database is configured.
- A long-lived, revocable **device credential**, issued once a pairing
  token is redeemed. This one *is* persisted (the `devices` table in
  `nids.api.store`, gated by `database_url` exactly like `predictions`/
  `alerts`) -- only its hash is ever stored, never the raw value, so a
  database read alone can never leak a usable credential.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.engine import Engine

from nids.api.store import (
    DeviceRecordView,
    get_device_by_credential_hash,
    register_device,
    touch_device_last_seen,
)

_PAIRING_SALT = "nids-agent-pairing"
DEFAULT_PAIRING_TTL_SECONDS = 600


def issue_pairing_token(secret_key: str) -> str:
    """A short-lived, stateless pairing code -- nothing to store, so
    issuing one works even without a database configured. Expiry is
    enforced entirely at `verify_pairing_token` time via the token's own
    embedded, signed timestamp."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_PAIRING_SALT)
    return serializer.dumps({"purpose": "agent-pairing"})


def verify_pairing_token(
    token: str, secret_key: str, ttl_seconds: int = DEFAULT_PAIRING_TTL_SECONDS
) -> bool:
    """`True` for a valid, unexpired pairing token; `False` (never
    raises) for a malformed or expired one -- an invalid pairing attempt
    is an expected caller mistake, not an exceptional program state."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_PAIRING_SALT)
    try:
        serializer.loads(token, max_age=ttl_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return True


def _hash_credential(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeviceCredential:
    device_id: str
    token: str  # the raw bearer token -- returned to the agent once, never persisted in the clear


def exchange_pairing_token(
    engine: Engine,
    pairing_token: str,
    secret_key: str,
    device_name: str,
    user_id: str | None = None,
) -> DeviceCredential:
    """Redeem a valid pairing token for a long-lived device credential.

    Raises `ValueError` for an invalid/expired pairing token -- the
    caller (the `/agent/pair/exchange` route) maps that to an HTTP 400,
    the same convention every other input-validation failure in this API
    already uses (see `nids.api.app`).
    """
    if not verify_pairing_token(pairing_token, secret_key):
        raise ValueError("Pairing token is invalid or has expired.")

    raw_token = secrets.token_urlsafe(32)
    device = register_device(
        engine, name=device_name, credential_hash=_hash_credential(raw_token), user_id=user_id
    )
    return DeviceCredential(device_id=device.id, token=raw_token)


def authenticate_device(engine: Engine, token: str) -> DeviceRecordView | None:
    """Look up the device behind a bearer token; `None` if unknown or
    revoked. Updates `last_seen_at` on success -- called on every
    `/agent/ingest` WebSocket connection (see `nids.api.ingest`)."""
    credential_hash = _hash_credential(token)
    device = get_device_by_credential_hash(engine, credential_hash)
    if device is None or device.revoked:
        return None
    touch_device_last_seen(engine, device.id)
    # re-fetch: `device` was read before the touch above, so it still
    # carries the pre-update (stale) last_seen_at otherwise.
    return get_device_by_credential_hash(engine, credential_hash)
