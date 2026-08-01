"""Command-line entry point for running the inference API server.

Kept separate from nids.api.app (and out of nids/api/__init__.py's import
graph) so `python -m nids.api` doesn't re-import its own module as
__main__ -- same reasoning as nids.training.cli.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from nids.api.app import create_app
from nids.api.config import DEFAULT_ARTIFACT_ROOT, ServingConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NIDS inference API.")
    parser.add_argument("--run-id", required=True, help="run_id (under --artifact-root) to serve")
    parser.add_argument(
        "--anomaly-run-id",
        default=None,
        help="optional run_id of an anomaly detector (e.g. isolation_forest) to serve "
        "alongside --run-id for hybrid detection",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="directory containing training run outputs",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    config = ServingConfig(
        run_id=args.run_id,
        anomaly_run_id=args.anomaly_run_id,
        artifact_root=Path(args.artifact_root),
        host=args.host,
        port=args.port,
    )
    app = create_app(config)

    uvicorn.run(app, host=config.host, port=config.port)
    return 0
