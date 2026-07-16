"""Additive SQLite schema for the Pine Hollow Commons Lab.

The existing bioacoustics tables remain untouched.  Commons tables separate raw
evidence, assertions, interventions, outcomes, and publication decisions.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 7

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

CREATE TABLE IF NOT EXISTS commons_acoustic_windows (
    window_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    source_recording_id TEXT NOT NULL,
    source_event_id TEXT,
    bundle_id TEXT NOT NULL,
    model_slug TEXT NOT NULL,
    class_name TEXT NOT NULL,
    start_sample INTEGER NOT NULL CHECK (start_sample >= 0),
    end_sample INTEGER NOT NULL CHECK (end_sample > start_sample),
    sample_rate INTEGER NOT NULL CHECK (sample_rate > 0),
    score REAL NOT NULL CHECK (score >= 0.0 AND score <= 1.0),
    raw_score REAL NOT NULL,
    threshold REAL NOT NULL CHECK (threshold >= 0.0 AND threshold <= 1.0),
    crosses_threshold INTEGER NOT NULL CHECK (crosses_threshold IN (0, 1)),
    score_semantics TEXT NOT NULL,
    preprocess_recipe_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_recording_id, bundle_id, start_sample),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(media_id) REFERENCES commons_media(media_id)
);

CREATE TABLE IF NOT EXISTS commons_event_links (
    link_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    target_event_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    method TEXT NOT NULL,
    offset_seconds REAL NOT NULL,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_event_id, target_event_id, relation, method),
    CHECK (source_event_id != target_event_id),
    FOREIGN KEY(source_event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(target_event_id) REFERENCES commons_events(event_id)
);

CREATE VIEW IF NOT EXISTS commons_current_event_links AS
SELECT link_id, source_event_id, target_event_id, relation, method,
       offset_seconds, confidence, metadata_json, created_at
FROM (
    SELECT links.*,
           ROW_NUMBER() OVER (
               PARTITION BY source_event_id, relation, method
               ORDER BY ABS(offset_seconds), created_at DESC, link_id
           ) AS nearest_rank
    FROM commons_event_links AS links
)
WHERE nearest_rank = 1;

CREATE TABLE IF NOT EXISTS commons_review_queue (
    queue_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    score_band TEXT NOT NULL,
    priority REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'in_review', 'completed', 'dismissed')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(event_id, bundle_id, score_band),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_jobs (
    job_id TEXT PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL,
    energy_class TEXT NOT NULL
        CHECK (energy_class IN ('critical_continuous', 'scheduled_cpu', 'deferrable_gpu', 'manual_high_energy')),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'success', 'skipped', 'failed', 'cancelled')),
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    not_before TEXT,
    lease_owner TEXT,
    leased_until TEXT,
    input_event_id TEXT,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(input_event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_job_transitions (
    transition_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    transitioned_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES commons_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS commons_research_records (
    record_id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    record_type TEXT NOT NULL
        CHECK (record_type IN ('research', 'decision', 'development', 'experiment', 'validation', 'incident', 'operation')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    related_run_id TEXT,
    related_job_id TEXT,
    related_event_id TEXT,
    author TEXT NOT NULL DEFAULT 'Hermes',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(related_run_id) REFERENCES commons_runs(run_id),
    FOREIGN KEY(related_job_id) REFERENCES commons_jobs(job_id),
    FOREIGN KEY(related_event_id) REFERENCES commons_events(event_id)
);

CREATE TABLE IF NOT EXISTS commons_validation_packets (
    packet_id TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    week_start TEXT NOT NULL,
    timezone TEXT NOT NULL,
    sampling_seed TEXT NOT NULL,
    target_count INTEGER NOT NULL CHECK (target_count > 0),
    state TEXT NOT NULL DEFAULT 'ready'
        CHECK (state IN ('ready', 'in_progress', 'completed')),
    manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(protocol_version, week_start)
);

CREATE TABLE IF NOT EXISTS commons_validation_items (
    item_id TEXT PRIMARY KEY,
    packet_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    event_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    source_recording_id TEXT NOT NULL,
    start_sample INTEGER NOT NULL CHECK (start_sample >= 0),
    end_sample INTEGER NOT NULL CHECK (end_sample > start_sample),
    sample_rate INTEGER NOT NULL CHECK (sample_rate > 0),
    lane TEXT NOT NULL
        CHECK (lane IN ('model_positive', 'boundary', 'random_control', 'blind_repeat')),
    source_item_id TEXT,
    primary_class_name TEXT,
    primary_bundle_id TEXT,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'completed')),
    sampling_metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(packet_id, position),
    FOREIGN KEY(packet_id) REFERENCES commons_validation_packets(packet_id),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(media_id) REFERENCES commons_media(media_id),
    FOREIGN KEY(source_item_id) REFERENCES commons_validation_items(item_id)
);

CREATE TABLE IF NOT EXISTS commons_validation_reviews (
    review_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE,
    reviewer TEXT NOT NULL,
    insect_presence TEXT NOT NULL
        CHECK (insect_presence IN ('present', 'absent', 'uncertain')),
    chicken_presence TEXT NOT NULL
        CHECK (chicken_presence IN ('present', 'absent', 'uncertain')),
    signal_quality TEXT NOT NULL
        CHECK (signal_quality IN ('clear', 'distant', 'overlapping', 'clipped', 'noisy', 'inaudible')),
    confounders_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    review_seconds REAL CHECK (review_seconds IS NULL OR review_seconds >= 0),
    assertion_ids_json TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(item_id) REFERENCES commons_validation_items(item_id)
);

CREATE TABLE IF NOT EXISTS commons_validation_sentinels (
    sentinel_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    expected_media_sha256 TEXT NOT NULL CHECK (length(expected_media_sha256) = 64),
    expected_context_json TEXT NOT NULL,
    label_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    promoted_by TEXT NOT NULL,
    promoted_at TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES commons_validation_items(item_id),
    FOREIGN KEY(event_id) REFERENCES commons_events(event_id),
    FOREIGN KEY(media_id) REFERENCES commons_media(media_id)
);

CREATE TABLE IF NOT EXISTS commons_validation_sentinel_checks (
    check_id TEXT PRIMARY KEY,
    sentinel_id TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'drift', 'missing')),
    observed_json TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY(sentinel_id) REFERENCES commons_validation_sentinels(sentinel_id)
);

CREATE TRIGGER IF NOT EXISTS commons_guard_assertions_update
BEFORE UPDATE ON commons_assertions
BEGIN
    SELECT RAISE(ABORT, 'assertions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_assertions_delete
BEFORE DELETE ON commons_assertions
BEGIN
    SELECT RAISE(ABORT, 'assertions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_acoustic_windows_update
BEFORE UPDATE ON commons_acoustic_windows
BEGIN
    SELECT RAISE(ABORT, 'acoustic windows are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_acoustic_windows_delete
BEFORE DELETE ON commons_acoustic_windows
BEGIN
    SELECT RAISE(ABORT, 'acoustic windows are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_event_links_update
BEFORE UPDATE ON commons_event_links
BEGIN
    SELECT RAISE(ABORT, 'event links are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_event_links_delete
BEFORE DELETE ON commons_event_links
BEGIN
    SELECT RAISE(ABORT, 'event links are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_job_transitions_update
BEFORE UPDATE ON commons_job_transitions
BEGIN
    SELECT RAISE(ABORT, 'job transitions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_job_transitions_delete
BEFORE DELETE ON commons_job_transitions
BEGIN
    SELECT RAISE(ABORT, 'job transitions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_research_records_update
BEFORE UPDATE ON commons_research_records
BEGIN
    SELECT RAISE(ABORT, 'research records are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_research_records_delete
BEFORE DELETE ON commons_research_records
BEGIN
    SELECT RAISE(ABORT, 'research records are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_packet_manifest_update
BEFORE UPDATE OF protocol_version, week_start, timezone, sampling_seed,
                 target_count, manifest_sha256, manifest_json, created_at
ON commons_validation_packets
BEGIN
    SELECT RAISE(ABORT, 'validation packet manifests are immutable');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_item_manifest_update
BEFORE UPDATE OF packet_id, position, event_id, media_id, source_recording_id, start_sample,
                 end_sample, sample_rate, lane, source_item_id,
                 primary_class_name, primary_bundle_id,
                 sampling_metadata_json, created_at
ON commons_validation_items
BEGIN
    SELECT RAISE(ABORT, 'validation item manifests are immutable');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_packets_delete
BEFORE DELETE ON commons_validation_packets
BEGIN
    SELECT RAISE(ABORT, 'validation packets are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_items_delete
BEFORE DELETE ON commons_validation_items
BEGIN
    SELECT RAISE(ABORT, 'validation items are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_reviews_update
BEFORE UPDATE ON commons_validation_reviews
BEGIN
    SELECT RAISE(ABORT, 'validation reviews are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_reviews_delete
BEFORE DELETE ON commons_validation_reviews
BEGIN
    SELECT RAISE(ABORT, 'validation reviews are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_sentinels_update
BEFORE UPDATE ON commons_validation_sentinels
BEGIN
    SELECT RAISE(ABORT, 'validation sentinels are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_sentinels_delete
BEFORE DELETE ON commons_validation_sentinels
BEGIN
    SELECT RAISE(ABORT, 'validation sentinels are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_sentinel_checks_update
BEFORE UPDATE ON commons_validation_sentinel_checks
BEGIN
    SELECT RAISE(ABORT, 'validation sentinel checks are append-only');
END;

CREATE TRIGGER IF NOT EXISTS commons_guard_validation_sentinel_checks_delete
BEFORE DELETE ON commons_validation_sentinel_checks
BEGIN
    SELECT RAISE(ABORT, 'validation sentinel checks are append-only');
END;

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
CREATE INDEX IF NOT EXISTS idx_commons_acoustic_windows_event ON commons_acoustic_windows(event_id);
CREATE INDEX IF NOT EXISTS idx_commons_acoustic_windows_class_score ON commons_acoustic_windows(class_name, score DESC);
CREATE INDEX IF NOT EXISTS idx_commons_event_links_source ON commons_event_links(source_event_id, relation);
CREATE INDEX IF NOT EXISTS idx_commons_event_links_target ON commons_event_links(target_event_id, relation);
CREATE INDEX IF NOT EXISTS idx_commons_review_queue_state_priority ON commons_review_queue(state, priority DESC);
CREATE INDEX IF NOT EXISTS idx_commons_jobs_state_energy_priority ON commons_jobs(state, energy_class, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_commons_jobs_lease ON commons_jobs(state, leased_until);
CREATE INDEX IF NOT EXISTS idx_commons_job_transitions_job_time ON commons_job_transitions(job_id, transitioned_at);
CREATE INDEX IF NOT EXISTS idx_commons_research_records_type_time ON commons_research_records(record_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_commons_validation_packets_week ON commons_validation_packets(week_start, state);
CREATE INDEX IF NOT EXISTS idx_commons_validation_items_packet ON commons_validation_items(packet_id, position, state);
CREATE INDEX IF NOT EXISTS idx_commons_validation_items_event ON commons_validation_items(event_id, start_sample);
CREATE INDEX IF NOT EXISTS idx_commons_validation_items_recording ON commons_validation_items(source_recording_id);
CREATE INDEX IF NOT EXISTS idx_commons_validation_sentinels_active ON commons_validation_sentinels(active, promoted_at);
CREATE INDEX IF NOT EXISTS idx_commons_validation_sentinel_checks_time ON commons_validation_sentinel_checks(sentinel_id, checked_at);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the Commons Lab schema without altering legacy archive tables."""
    conn.execute("PRAGMA foreign_keys = ON")
    validation_items_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='commons_validation_items'"
    ).fetchone() is not None
    if validation_items_exists:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(commons_validation_items)")
        }
        if "source_recording_id" not in columns:
            conn.execute("DROP TRIGGER IF EXISTS commons_guard_validation_item_manifest_update")
            conn.execute(
                "ALTER TABLE commons_validation_items ADD COLUMN source_recording_id TEXT"
            )
            conn.execute(
                """
                UPDATE commons_validation_items
                SET source_recording_id=(
                    SELECT MIN(w.source_recording_id)
                    FROM commons_acoustic_windows AS w
                    WHERE w.event_id=commons_validation_items.event_id
                      AND w.media_id=commons_validation_items.media_id
                      AND w.start_sample=commons_validation_items.start_sample
                      AND w.end_sample=commons_validation_items.end_sample
                      AND w.sample_rate=commons_validation_items.sample_rate
                )
                WHERE source_recording_id IS NULL
                """
            )
            missing = int(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_validation_items WHERE source_recording_id IS NULL"
                ).fetchone()[0]
            )
            if missing:
                conn.rollback()
                raise RuntimeError(
                    f"cannot backfill source recording identity for {missing} validation items"
                )
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
            (4, "Physical-ecology acoustic, context, job, and research automation line"),
            (5, "Current nearest-context view and reviewed factory hardening"),
            (6, "Blinded weekly field-validation packets, reviews, and sentinels"),
            (7, "Frozen source-recording identity and complete validation immutability"),
        ],
    )
    conn.commit()
