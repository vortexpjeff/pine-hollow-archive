#!/usr/bin/env python3
"""Silent scheduled entrypoint for one Commons Lab camera capture."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.pipeline import DEFAULT_DATA_ROOT, capture_window_frame


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--db", type=Path, default=ROOT / "archive.db")
    command.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    command.add_argument("--trigger", default="systemd_timer")
    command.add_argument("--min-free-gib", type=int, default=20)
    command.add_argument("--json", action="store_true", help="print outcome on success")
    return command


def main() -> int:
    args = parser().parse_args()
    os.umask(0o077)
    try:
        os.nice(10)
    except OSError:
        pass

    try:
        outcome = capture_window_frame(
            db_path=args.db,
            data_root=args.data_root,
            trigger_type=args.trigger,
            min_free_bytes=args.min_free_gib * 1024**3,
        )
    except Exception as exc:
        print(
            f"Commons Lab capture failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(asdict(outcome), sort_keys=True, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
