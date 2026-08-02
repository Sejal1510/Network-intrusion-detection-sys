"""Command-line entry point for the live capture agent.

`python -m nids.agent pair <code>` redeems a short-lived pairing code (see
`nids.api.agent_auth`) for a long-lived device credential, persisted to
`--credential-file` so it doesn't need to be re-entered. `python -m
nids.agent run` then streams flow records -- from a live capture or a
replayed `.pcap` -- to the paired server using that saved credential.

Kept separate from `nids.agent.client` (and out of `nids/agent/__init__.py`'s
import graph) so `python -m nids.agent` doesn't re-import its own module as
__main__ -- same reasoning as `nids.api.cli`/`nids.training.cli`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from nids.agent.client import AgentClient, exchange_pairing_token
from nids.agent.sources import FlowSource, LiveSource, ReplaySource

DEFAULT_CREDENTIAL_PATH = Path.home() / ".nids" / "agent_credential.json"


def save_device_credential(path: Path, token: str) -> None:
    """Persists the device credential redeemed by `pair` -- `run` needs it
    on every future invocation, and the pairing code it was redeemed from
    is single-use and short-lived, so it can't be re-derived."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token}))
    try:
        path.chmod(0o600)  # best-effort; Windows doesn't enforce POSIX perms
    except OSError:
        pass


def load_device_credential(path: Path) -> str:
    if not path.exists():
        raise SystemExit(
            f"No device credential at {path} -- run `python -m nids.agent pair <code>` first."
        )
    return json.loads(path.read_text())["token"]


def ws_url_from_base(base_url: str) -> str:
    """`http(s)://host:port` -> `ws(s)://host:port/agent/ingest` -- the
    agent always connects to that one, single ingest endpoint."""
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base.rstrip('/')}/agent/ingest"


def build_source(args: argparse.Namespace) -> FlowSource:
    if args.pcap:
        return ReplaySource(args.pcap, speed=args.speed)
    return LiveSource(interface=args.interface, bpf_filter=args.bpf_filter)


def _pair(args: argparse.Namespace) -> int:
    token = exchange_pairing_token(args.base_url, args.pairing_code, args.device_name)
    save_device_credential(args.credential_file, token)
    print(f"Paired successfully. Credential saved to {args.credential_file}.")
    return 0


def _run(args: argparse.Namespace) -> int:
    device_token = load_device_credential(args.credential_file)
    source = build_source(args)
    client = AgentClient(ws_url_from_base(args.base_url), device_token, source)
    asyncio.run(client.run())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NIDS live capture agent.")
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=DEFAULT_CREDENTIAL_PATH,
        help="where the device credential is stored/read (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pair_parser = subparsers.add_parser(
        "pair", help="Redeem a pairing code for a device credential."
    )
    pair_parser.add_argument("pairing_code")
    pair_parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    pair_parser.add_argument("--device-name", required=True)
    pair_parser.set_defaults(func=_pair)

    run_parser = subparsers.add_parser("run", help="Stream flow records to the paired server.")
    run_parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    run_parser.add_argument("--interface", default=None, help="NIC to capture on (default: OS default)")
    run_parser.add_argument("--bpf-filter", default=None)
    run_parser.add_argument("--pcap", default=None, help="replay a saved .pcap instead of live capture")
    run_parser.add_argument(
        "--speed", type=float, default=1.0, help="replay speed multiplier (--pcap only)"
    )
    run_parser.set_defaults(func=_run)

    args = parser.parse_args()
    return args.func(args)
