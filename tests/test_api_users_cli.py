import pytest

from nids.api import store
from nids.api import users as users_module
from nids.api.user_auth import authenticate_user


@pytest.fixture(autouse=True)
def _clean_nids_env(monkeypatch):
    monkeypatch.delenv("NIDS_DATABASE_URL", raising=False)


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{tmp_path / 'users.db'}"


def test_create_user_persists_hashed_password(database_url):
    exit_code = users_module.main(
        ["create-user", "--database-url", database_url, "--username", "alice", "--password", "hunter2", "--role", "analyst"]
    )

    assert exit_code == 0
    engine = store.create_db_engine(database_url)
    assert authenticate_user(engine, "alice", "hunter2") is not None


def test_create_user_rejects_duplicate_username(database_url, capsys):
    users_module.main(
        ["create-user", "--database-url", database_url, "--username", "alice", "--password", "hunter2", "--role", "analyst"]
    )

    exit_code = users_module.main(
        ["create-user", "--database-url", database_url, "--username", "alice", "--password", "other", "--role", "admin"]
    )

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err


def test_create_user_reads_database_url_from_env(database_url, monkeypatch):
    monkeypatch.setenv("NIDS_DATABASE_URL", database_url)

    exit_code = users_module.main(
        ["create-user", "--username", "alice", "--password", "hunter2", "--role", "analyst"]
    )

    assert exit_code == 0
    engine = store.create_db_engine(database_url)
    assert authenticate_user(engine, "alice", "hunter2") is not None


def test_create_user_requires_database_url(capsys):
    with pytest.raises(SystemExit) as exc_info:
        users_module.main(["create-user", "--username", "alice", "--password", "x", "--role", "analyst"])

    assert exc_info.value.code == 2
    assert "--database-url is required" in capsys.readouterr().err


def test_list_users_prints_created_users(database_url, capsys):
    users_module.main(
        ["create-user", "--database-url", database_url, "--username", "alice", "--password", "hunter2", "--role", "analyst"]
    )

    exit_code = users_module.main(["list-users", "--database-url", database_url])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "alice" in output
    assert "analyst" in output


def test_set_role_updates_existing_user(database_url):
    users_module.main(
        ["create-user", "--database-url", database_url, "--username", "alice", "--password", "hunter2", "--role", "analyst"]
    )

    exit_code = users_module.main(
        ["set-role", "--database-url", database_url, "--username", "alice", "--role", "admin"]
    )

    assert exit_code == 0
    engine = store.create_db_engine(database_url)
    assert store.get_user_by_username(engine, "alice").role == "admin"


def test_set_role_fails_for_unknown_user(database_url, capsys):
    exit_code = users_module.main(
        ["set-role", "--database-url", database_url, "--username", "nobody", "--role", "admin"]
    )

    assert exit_code == 1
    assert "No such user" in capsys.readouterr().err
