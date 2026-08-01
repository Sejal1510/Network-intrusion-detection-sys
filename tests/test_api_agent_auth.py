import time

import pytest

from nids.api import store
from nids.api.agent_auth import (
    DeviceCredential,
    authenticate_device,
    exchange_pairing_token,
    issue_pairing_token,
    verify_pairing_token,
)

SECRET = "test-secret-key"


@pytest.fixture
def engine(tmp_path):
    return store.create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


def test_issued_pairing_token_verifies_successfully():
    token = issue_pairing_token(SECRET)
    assert verify_pairing_token(token, SECRET) is True


def test_pairing_token_rejects_wrong_secret():
    token = issue_pairing_token(SECRET)
    assert verify_pairing_token(token, "a-different-secret") is False


def test_pairing_token_rejects_malformed_token():
    assert verify_pairing_token("not-a-real-token", SECRET) is False


def test_pairing_token_expires_after_ttl():
    token = issue_pairing_token(SECRET)
    time.sleep(2.1)  # itsdangerous's age check is second-granular; comfortably past ttl_seconds=1
    assert verify_pairing_token(token, SECRET, ttl_seconds=1) is False


def test_exchange_pairing_token_returns_device_credential(engine):
    token = issue_pairing_token(SECRET)

    credential = exchange_pairing_token(engine, token, SECRET, device_name="ayush-laptop")

    assert isinstance(credential, DeviceCredential)
    assert credential.device_id
    assert credential.token


def test_exchange_pairing_token_persists_a_device(engine):
    token = issue_pairing_token(SECRET)
    credential = exchange_pairing_token(engine, token, SECRET, device_name="ayush-laptop")

    device = authenticate_device(engine, credential.token)

    assert device is not None
    assert device.id == credential.device_id
    assert device.name == "ayush-laptop"


def test_exchange_pairing_token_raises_for_invalid_token(engine):
    with pytest.raises(ValueError, match="invalid or has expired"):
        exchange_pairing_token(engine, "garbage-token", SECRET, device_name="ayush-laptop")


def test_exchange_pairing_token_never_stores_the_raw_credential(engine):
    token = issue_pairing_token(SECRET)
    credential = exchange_pairing_token(engine, token, SECRET, device_name="ayush-laptop")

    # the raw bearer token must never appear as a stored credential_hash
    assert store.get_device_by_credential_hash(engine, credential.token) is None


def test_authenticate_device_returns_none_for_unknown_token(engine):
    assert authenticate_device(engine, "not-a-real-token") is None


def test_authenticate_device_returns_none_for_revoked_device(engine):
    token = issue_pairing_token(SECRET)
    credential = exchange_pairing_token(engine, token, SECRET, device_name="ayush-laptop")
    store.revoke_device(engine, credential.device_id)

    assert authenticate_device(engine, credential.token) is None


def test_authenticate_device_updates_last_seen(engine):
    token = issue_pairing_token(SECRET)
    credential = exchange_pairing_token(engine, token, SECRET, device_name="ayush-laptop")

    device = authenticate_device(engine, credential.token)

    assert device.last_seen_at is not None
