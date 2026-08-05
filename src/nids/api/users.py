"""Command-line admin tool for bootstrapping dashboard users (see
`nids.api.user_auth`, `nids.api.auth`). Deliberately NOT env-var-
bootstrapped credentials and NOT part of `nids.api.cli` (which starts the
server) -- this is a one-off admin action against a database, not a
server flag.

Builds a bare `create_db_engine(database_url)`, not a full
`ServingConfig` -- nothing here serves a model or starts uvicorn, so
`ServingConfig`'s `run_id`/`artifact_root`/etc. fields are all irrelevant
to this tool.

Verb set kept deliberately tight -- no `delete-user`/`deactivate-user`:
deleting a user would orphan its `sessions`/`devices.user_id` rows, and
there's no real need for disabling a user yet. A follow-up milestone, not
this one.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from nids.api.store import create_db_engine, get_user_by_username, list_users, set_user_role
from nids.api.user_auth import VALID_ROLES, register_user


def _add_database_url_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=os.environ.get("NIDS_DATABASE_URL"),
        help="SQLAlchemy URL for the dashboard's database (env: NIDS_DATABASE_URL)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage NIDS dashboard users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-user", help="create a new user")
    _add_database_url_arg(create)
    create.add_argument("--username", required=True)
    create.add_argument("--password", help="omit to be prompted (not echoed)")
    create.add_argument("--role", required=True, choices=VALID_ROLES)

    list_parser = subparsers.add_parser("list-users", help="list existing users")
    _add_database_url_arg(list_parser)

    set_role = subparsers.add_parser("set-role", help="change a user's role")
    _add_database_url_arg(set_role)
    set_role.add_argument("--username", required=True)
    set_role.add_argument("--role", required=True, choices=VALID_ROLES)

    args = parser.parse_args(argv)

    if not args.database_url:
        parser.error("--database-url is required (or set the NIDS_DATABASE_URL environment variable)")

    engine = create_db_engine(args.database_url)

    if args.command == "create-user":
        if get_user_by_username(engine, args.username) is not None:
            print(f"User {args.username!r} already exists.", file=sys.stderr)
            return 1
        password = args.password or getpass.getpass("Password: ")
        user = register_user(engine, args.username, password, args.role)
        print(f"Created user {user.username!r} (role={user.role})")
        return 0

    if args.command == "list-users":
        page = list_users(engine, limit=1000, offset=0)
        for user in page.items:
            print(f"{user.username}\t{user.role}\t{user.created_at.isoformat()}")
        return 0

    if args.command == "set-role":
        user = get_user_by_username(engine, args.username)
        if user is None:
            print(f"No such user: {args.username!r}", file=sys.stderr)
            return 1
        set_user_role(engine, user.id, args.role)
        print(f"Set {args.username!r} role to {args.role!r}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
