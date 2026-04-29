#!/usr/bin/env python3
"""
Clear stale ``pharos_ingest_*`` directories left in the system temp dir.

The hybrid ingestion pipeline clones repos under ``tempfile.mkdtemp(prefix=
"pharos_ingest_")``. The clone is normally removed in the ``finally`` block of
``HybridIngestionPipeline.ingest_github_repo``, but a hard worker crash, a
killed process, or a Windows-side handle lock can leave the clone behind.

After the failed Linux ingest there were ~30 of these dirs (~3 GB) sitting in
%TEMP%. Run this script periodically (or wire it into worker startup) to
reclaim disk.

Usage:
    python clear_stale_temp_dirs.py                 # dry-run, lists candidates
    python clear_stale_temp_dirs.py --delete        # actually delete
    python clear_stale_temp_dirs.py --min-age 12    # only dirs older than 12h
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path


PREFIX = "pharos_ingest_"


def _dir_size_bytes(path: Path) -> int:
    """Best-effort recursive dir size; ignores files that vanish mid-walk."""
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return total


def find_stale_dirs(min_age_hours: float) -> list[tuple[Path, float, int]]:
    """Return [(path, age_hours, size_bytes), ...] for all stale clone dirs."""
    tmp_root = Path(tempfile.gettempdir())
    cutoff = time.time() - (min_age_hours * 3600)
    out: list[tuple[Path, float, int]] = []
    for entry in tmp_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith(PREFIX):
            continue
        try:
            mtime = entry.stat().st_mtime
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if mtime > cutoff:
            continue
        age_hours = (time.time() - mtime) / 3600
        size = _dir_size_bytes(entry)
        out.append((entry, age_hours, size))
    return sorted(out, key=lambda t: t[1], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete; without this flag, prints what would be deleted",
    )
    parser.add_argument(
        "--min-age",
        type=float,
        default=1.0,
        help="Only consider dirs older than N hours (default: 1)",
    )
    args = parser.parse_args()

    candidates = find_stale_dirs(args.min_age)
    if not candidates:
        print(f"No stale {PREFIX}* dirs older than {args.min_age}h.")
        return 0

    total_bytes = sum(size for _, _, size in candidates)
    print(f"Found {len(candidates)} stale clone dir(s) (~{total_bytes / 1e9:.2f} GB):")
    for path, age, size in candidates:
        print(f"  {path}  age={age:.1f}h  size={size / 1e9:.2f} GB")

    if not args.delete:
        print("\nDry-run only. Pass --delete to remove these.")
        return 0

    removed = 0
    failed = 0
    for path, _, _ in candidates:
        try:
            shutil.rmtree(path, ignore_errors=False)
            removed += 1
        except Exception as exc:
            print(f"  FAILED {path}: {exc}", file=sys.stderr)
            failed += 1
    print(f"\nDeleted {removed}, failed {failed}, freed ~{total_bytes / 1e9:.2f} GB.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
