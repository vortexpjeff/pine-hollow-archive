#!/usr/bin/env python3
"""Run Pine Hollow archive label-hardening schema migration."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from schema_hardening import ensure_review_hardening_schema

ARCHIVE_ROOT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_ROOT / "archive.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Pine Hollow archive schema")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db))
    before = {r[1] for r in conn.execute("PRAGMA table_info(clips)")}
    ensure_review_hardening_schema(conn)
    after = {r[1] for r in conn.execute("PRAGMA table_info(clips)")}
    has_events = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='label_events'"
    ).fetchone() is not None
    conn.close()

    added = sorted(after - before)
    print(f"Schema migration OK. Added columns: {added or 'none'}. label_events={has_events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
