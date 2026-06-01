#!/usr/bin/env python3
"""Shared schema + training eligibility rules for Pine Hollow labels."""

from __future__ import annotations

import sqlite3

REVIEW_COLUMNS = {
    "label_certainty": "ALTER TABLE clips ADD COLUMN label_certainty TEXT",
    "review_notes": "ALTER TABLE clips ADD COLUMN review_notes TEXT",
    "review_source": "ALTER TABLE clips ADD COLUMN review_source TEXT",
}

LABEL_EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS label_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clip_id INTEGER NOT NULL,
        label TEXT,
        label_type TEXT,
        source TEXT NOT NULL,
        reviewer TEXT,
        confidence TEXT,
        evidence TEXT,
        action TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        model_version TEXT,
        notes TEXT,
        FOREIGN KEY(clip_id) REFERENCES clips(id)
    )
"""


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def ensure_review_hardening_schema(conn: sqlite3.Connection) -> None:
    """Idempotent migration for certainty, provenance, and label event ledger."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    for column, ddl in REVIEW_COLUMNS.items():
        if column not in existing:
            conn.execute(ddl)
    conn.execute(LABEL_EVENTS_DDL)

    # Preserve old training behavior, but make provenance explicit.
    conn.execute("""
        UPDATE clips
        SET label_certainty = 'probable'
        WHERE review_status IN ('confirmed', 'corrected')
        AND (label_certainty IS NULL OR label_certainty = '')
    """)
    conn.execute("""
        UPDATE clips
        SET review_source = CASE WHEN source = 'public' THEN 'public_dataset' ELSE 'legacy_reviewed' END
        WHERE review_status IN ('confirmed', 'corrected')
        AND (review_source IS NULL OR review_source = '')
    """)
    conn.commit()


def training_eligibility_sql(alias: str = "") -> str:
    """Current hard gate for labels allowed into retrain."""
    p = f"{alias}." if alias else ""
    return (
        f"{p}review_status IN ('confirmed', 'corrected') "
        f"AND {p}label_certainty IN ('certain', 'probable') "
        f"AND COALESCE({p}review_source, '') != 'batch_auto_accept'"
    )
