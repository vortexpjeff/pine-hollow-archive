"""Additive SQLite schema for the Pine Hollow Commons Lab.

The existing bioacoustics tables remain untouched.  Commons tables separate raw
evidence, assertions, interventions, outcomes, and publication decisions.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

DDL = """
CREATE TABLE IF NOT EXISTS commons_schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commons_sites (
    site_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    public_region TEXT,
    exact_location_json TEXT,
    privacy_level TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_level IN ('public', 'aggregate_only', 'research_by_request', 'private', 'sensitive')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS commons_sensors (
    sensor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    host TEXT,
    privacy_default TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_default IN ('public', 'aggregate_only', 'research_by_request', 'private', 'sensitive')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    retired_at TEXT
);

CREATE TABLE IF NOT EXISTS commons_deployments (
    deployment_id TEXT PRIMARY KEY,
    sensor_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    orientation_json TEXT NOT NULL DEFAULT '{}',
    configuration_json TEXT NOT NULL DEFAULT '{}',
    privacy_default TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_default IN ('public', 'aggregate_only', 'research_by_request', 'private', 'sensitive')),
    FOREIGN KEY(sensor_id) REFERENCES commons_sensors(sensor_id),
    FOREIGN KEY(site_id) REFERENCES commons_sites(site_id)
);

CREATE TABLE IF NOT EXISTS commons_events (
    event_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    timezone TEXT NOT NULL,
    site_id TEXT NOT NULL,
    deployment_id TEXT,
    source TEXT NOT NULL,
    summary TEXT,
    privacy_level TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_level IN ('public', 'aggregate_only', 'research_by_request', 'private', 'sensitive')),
    review_state TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (review_state IN ('unreviewed', 'needs_review', 'reviewed', 'rejected')),
    publication_state TEXT NOT NULL DEFAULT 'blocked'
        CHECK (publication_state IN ('blocked', 'aggregate_only', 'approved')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(site_id) REFERENCES commons_sites(site_id),
    FOREIGN KEY(deployment_id) REFERENCES commons_deployments(deployment_id)
);

CREATE TABLE IF NOT EXISTS commons_media (
    media_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    mime_type TEXT,
    width INTEGER,
    height INTEGER,
    duration_s REAL,
    captured_at TEXT NOT NULL,
    transform_json TEXT NOT NULL DEFAULT '{}',
    privacy_level TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_level IN ('public', 'aggregate_only', 'research_by_request', 'private', 'sensitive')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_measurements (
    measurement_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    sensor_id TEXT,
    phenomenon TEXT NOT NULL,
    value_real REAL,
    value_text TEXT,
    unit TEXT,
    quality_flag TEXT NOT NULL DEFAULT 'unchecked',
    observed_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(sensor_id) REFERENCES commons_sensors(sensor_id),
    CHECK (value_real IS NOT NULL OR value_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS commons_assertions (
    assertion_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    media_id TEXT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('model', 'human', 'sensor', 'rule', 'external_dataset')),
    source_name TEXT NOT NULL,
    source_version TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    authority TEXT NOT NULL DEFAULT 'candidate'
        CHECK (authority IN ('candidate', 'reviewed', 'expert_validated')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(media_id) REFERENCES commons_media(media_id)
);

CREATE TABLE IF NOT EXISTS commons_interventions (
    intervention_id TEXT PRIMARY KEY,
    decision_event_id TEXT NOT NULL,
    target_id TEXT,
    action_type TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    reason TEXT,
    safety_class TEXT NOT NULL DEFAULT 'human_approval'
        CHECK (safety_class IN ('automatic_low_risk', 'human_approval', 'hard_interlock_required')),
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'executed', 'declined', 'cancelled', 'failed')),
    parameters_json TEXT NOT NULL DEFAULT '{}',
    executed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(decision_event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_outcomes (
    outcome_id TEXT PRIMARY KEY,
    intervention_id TEXT NOT NULL,
    observed_event_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value_json TEXT NOT NULL,
    attribution_state TEXT NOT NULL DEFAULT 'associated'
        CHECK (attribution_state IN ('associated', 'plausible', 'controlled_comparison', 'unknown')),
    observed_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(intervention_id) REFERENCES commons_interventions(intervention_id),
    FOREIGN KEY(observed_event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_publications (
    publication_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    surface TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('draft', 'approved', 'published', 'withdrawn')),
    payload_hash TEXT,
    public_uri TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_legacy_links (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    legacy_table TEXT NOT NULL,
    legacy_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'source_evidence',
    UNIQUE(legacy_table, legacy_id, event_id, relation),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_runs (
    run_id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual'
        CHECK (trigger_type IN ('manual', 'systemd_timer', 'retry', 'test')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'skipped', 'failed')),
    event_id TEXT,
    error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id)
);

CREATE TRIGGER IF NOT EXISTS commons_guard_private_publication_update
BEFORE UPDATE OF publication_state, privacy_level ON commons_events
WHEN NEW.publication_state = 'approved' AND NEW.privacy_level != 'public'
BEGIN
    SELECT RAISE(ABORT, 'only public events may be publicly approved');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_private_publication_insert
BEFORE INSERT ON commons_events
WHEN NEW.publication_state = 'approved' AND NEW.privacy_level != 'public'
BEGIN
    SELECT RAISE(ABORT, 'only public events may be publicly approved');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_publication_record_insert
BEFORE INSERT ON commons_publications
WHEN NEW.state IN ('approved', 'published')
AND NOT EXISTS (
    SELECT 1 FROM commons_events
    WHERE event_id = NEW.event_id
      AND privacy_level = 'public'
      AND publication_state = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'publication requires a public approved event');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_publication_record_update
BEFORE UPDATE OF event_id, state ON commons_publications
WHEN NEW.state IN ('approved', 'published')
AND NOT EXISTS (
    SELECT 1 FROM commons_events
    WHERE event_id = NEW.event_id
      AND privacy_level = 'public'
      AND publication_state = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'publication requires a public approved event');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_published_event_downgrade
BEFORE UPDATE OF publication_state, privacy_level ON commons_events
WHEN EXISTS (
    SELECT 1 FROM commons_publications
    WHERE event_id = OLD.event_id
      AND state IN ('approved', 'published')
)
AND (NEW.privacy_level != 'public' OR NEW.publication_state != 'approved')
BEGIN
    SELECT RAISE(ABORT, 'withdraw publication records before downgrading event');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_event_deployment_site_insert
BEFORE INSERT ON commons_events
WHEN NEW.deployment_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM commons_deployments
    WHERE deployment_id = NEW.deployment_id
      AND site_id = NEW.site_id
)
BEGIN
    SELECT RAISE(ABORT, 'event site must match deployment site');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_event_deployment_site_update
BEFORE UPDATE OF deployment_id, site_id ON commons_events
WHEN NEW.deployment_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM commons_deployments
    WHERE deployment_id = NEW.deployment_id
      AND site_id = NEW.site_id
)
BEGIN
    SELECT RAISE(ABORT, 'event site must match deployment site');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_deployment_site_update
BEFORE UPDATE OF site_id ON commons_deployments
WHEN EXISTS (
    SELECT 1 FROM commons_events
    WHERE deployment_id = OLD.deployment_id
      AND site_id != NEW.site_id
)
BEGIN
    SELECT RAISE(ABORT, 'deployment site change conflicts with existing events');
END;

CREATE INDEX IF NOT EXISTS idx_commons_events_time ON commons_events(started_at);
CREATE INDEX IF NOT EXISTS idx_commons_events_type_time ON commons_events(event_type, started_at);
CREATE INDEX IF NOT EXISTS idx_commons_events_publication ON commons_events(publication_state, review_state);
CREATE INDEX IF NOT EXISTS idx_commons_media_event ON commons_media(event_id);
CREATE INDEX IF NOT EXISTS idx_commons_media_sha256 ON commons_media(sha256);
CREATE INDEX IF NOT EXISTS idx_commons_assertions_event ON commons_assertions(event_id);
CREATE INDEX IF NOT EXISTS idx_commons_measurements_phenomenon_time ON commons_measurements(phenomenon, observed_at);
CREATE INDEX IF NOT EXISTS idx_commons_runs_pipeline_time ON commons_runs(pipeline, started_at);
CREATE INDEX IF NOT EXISTS idx_commons_runs_status_time ON commons_runs(status, started_at);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the Commons Lab schema without altering legacy archive tables."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    conn.executemany(
        """
        INSERT OR IGNORE INTO commons_schema_versions(version, description)
        VALUES (?, ?)
        """,
        [
            (1, "Initial Commons Lab event/evidence/research schema"),
            (2, "Publication and deployment/site provenance guards"),
            (3, "Automation run ledger and quality-measurement indices"),
        ],
    )
    conn.commit()
