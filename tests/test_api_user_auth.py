import pytest

from nids.api import store
from nids.api.user_auth import (
    RawSessionToken,
    authenticate_session,
    authenticate_user,
    create_session,
    hash_password,
    register_user,
    revoke_session,
    verify_password,
)


@pytest.fixture
def engine(tmp_path):
    return store.create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


def test_hash_password_does_not_return_the_raw_password():
    assert hash_password("hunter2") != "hunter2"


def test_verify_password_accepts_correct_password():
    hashed = hash_password("hunter2")
    assert verify_password("hunter2", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("hunter2")
    assert verify_password("wrong", hashed) is False


def test_register_user_hashes_the_password(engine):
    register_user(engine, "alice", "hunter2", "analyst")

    credentials = store._get_user_credentials_by_username(engine, "alice")

    assert credentials is not None
    password_hash, _view = credentials
    assert password_hash != "hunter2"


def test_register_user_rejects_invalid_role(engine):
    with pytest.raises(ValueError, match="role must be one of"):
        register_user(engine, "alice", "hunter2", "superuser")


def test_authenticate_user_returns_view_for_correct_credentials(engine):
    register_user(engine, "alice", "hunter2", "analyst")

    user = authenticate_user(engine, "alice", "hunter2")

    assert user is not None
    assert user.username == "alice"
    assert user.role == "analyst"


def test_authenticate_user_returns_none_for_unknown_username(engine):
    assert authenticate_user(engine, "does-not-exist", "hunter2") is None


def test_authenticate_user_returns_none_for_wrong_password(engine):
    register_user(engine, "alice", "hunter2", "analyst")

    assert authenticate_user(engine, "alice", "wrong-password") is None


def test_create_session_returns_raw_session_token(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")

    session = create_session(engine, user.id, ttl_seconds=3600)

    assert isinstance(session, RawSessionToken)
    assert session.token
    assert session.user.id == user.id


def test_authenticate_session_returns_view_for_valid_token(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")
    session = create_session(engine, user.id, ttl_seconds=3600)

    authenticated = authenticate_session(engine, session.token)

    assert authenticated is not None
    assert authenticated.id == user.id


def test_authenticate_session_returns_none_for_unknown_token(engine):
    assert authenticate_session(engine, "not-a-real-token") is None


def test_authenticate_session_returns_none_for_revoked_session(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")
    session = create_session(engine, user.id, ttl_seconds=3600)
    revoke_session(engine, session.token)

    assert authenticate_session(engine, session.token) is None


def test_authenticate_session_returns_none_for_expired_session(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")
    session = create_session(engine, user.id, ttl_seconds=-1)

    assert authenticate_session(engine, session.token) is None


def test_revoke_session_makes_token_unusable(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")
    session = create_session(engine, user.id, ttl_seconds=3600)
    assert authenticate_session(engine, session.token) is not None

    revoke_session(engine, session.token)

    assert authenticate_session(engine, session.token) is None


def test_create_session_never_stores_the_raw_token(engine):
    user = register_user(engine, "alice", "hunter2", "analyst")
    session = create_session(engine, user.id, ttl_seconds=3600)

    assert store.get_session_by_token_hash(engine, session.token) is None
