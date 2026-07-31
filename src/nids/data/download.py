"""Fetch the NSL-KDD dataset from a pinned, checksum-verified mirror.

The upstream host (UNB/CIC, https://www.unb.ca/cic/datasets/nsl.html) serves the
dataset behind a redirect to an access-controlled file host and does not provide
stable direct-download links, so this module pulls from a public GitHub mirror
pinned to a specific commit. See docs/DATASET.md for the full justification.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import requests

MIRROR_REPO = "jmnwong/NSL-KDD-Dataset"
MIRROR_COMMIT = "9d544d0eb9b87d7e2f43ff65733bdb644631d12f"
MIRROR_BASE_URL = f"https://raw.githubusercontent.com/{MIRROR_REPO}/{MIRROR_COMMIT}"

DEFAULT_DEST = Path("data/raw/nsl-kdd")

# filename -> sha256, captured from the pinned commit at verification time.
FILES: dict[str, str] = {
    "KDDTrain+.txt": "1b86d2f957b33082081bba410fe129b475efebcc13c9014c3f447c8271aadf95",
    "KDDTrain+_20Percent.txt": "7ea86479faab5ca2190b7f18b4982fb058ce5bf2b46e0e1017d0d9ef90f9c16e",
    "KDDTest+.txt": "fa46b0935342616aa83b7c2578db355b6a7aaabbc492248172c7a1e8b7ab8f84",
    "KDDTest-21.txt": "746993ac9e25868827cacf09eab450050a2a1056e1ce48a1ad39f5dc801d531d",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_dataset(dest: Path = DEFAULT_DEST, force: bool = False) -> Path:
    """Download and checksum-verify each NSL-KDD file into `dest`.

    Existing files whose checksum already matches are left untouched unless
    `force` is set. Raises RuntimeError if a downloaded file's checksum does
    not match the pinned value.
    """
    dest.mkdir(parents=True, exist_ok=True)

    for filename, expected_sha256 in FILES.items():
        out_path = dest / filename

        if out_path.exists() and not force and _sha256(out_path) == expected_sha256:
            print(f"[skip] {filename} already present and verified")
            continue

        url = f"{MIRROR_BASE_URL}/{filename}"
        print(f"[fetch] {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        out_path.write_bytes(response.content)

        actual_sha256 = _sha256(out_path)
        if actual_sha256 != expected_sha256:
            out_path.unlink()
            raise RuntimeError(
                f"Checksum mismatch for {filename}: expected {expected_sha256}, "
                f"got {actual_sha256}. Aborting to avoid using tampered/corrupt data."
            )
        print(f"[ok] {filename} verified ({actual_sha256})")

    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true", help="re-download even if verified")
    args = parser.parse_args()

    try:
        fetch_dataset(dest=args.dest, force=args.force)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
