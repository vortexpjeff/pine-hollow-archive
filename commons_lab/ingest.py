"""Idempotent evidence ingestion for Pine Hollow Commons Lab."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .safe_paths import resolve_no_symlinks


@dataclass(frozen=True)
class IngestResult:
    event_id: str
    media_id: str
    sha256: str
    created: bool


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def register_site(
    conn: sqlite3.Connection,
    *,
    site_id: str,
    name: str,
    public_region: str | None = None,
    privacy_level: str = "private",
    metadata: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO commons_sites(
            site_id, name, public_region, privacy_level, metadata_json
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(site_id) DO UPDATE SET
            name=excluded.name,
            public_region=excluded.public_region,
            privacy_level=excluded.privacy_level,
            metadata_json=excluded.metadata_json
        """,
        (site_id, name, public_region, privacy_level, _json(metadata)),
    )
    conn.commit()


def register_sensor(
    conn: sqlite3.Connection,
    *,
    sensor_id: str,
    name: str,
    sensor_type: str,
    manufacturer: str | None = None,
    model: str | None = None,
    host: str | None = None,
    privacy_default: str = "private",
    metadata: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO commons_sensors(
            sensor_id, name, sensor_type, manufacturer, model, host,
            privacy_default, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sensor_id) DO UPDATE SET
            name=excluded.name,
            sensor_type=excluded.sensor_type,
            manufacturer=excluded.manufacturer,
            model=excluded.model,
            host=excluded.host,
            privacy_default=excluded.privacy_default,
            metadata_json=excluded.metadata_json
        """,
        (
            sensor_id,
            name,
            sensor_type,
            manufacturer,
            model,
            host,
            privacy_default,
            _json(metadata),
        ),
    )
    conn.commit()


def register_deployment(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    sensor_id: str,
    site_id: str,
    purpose: str,
    orientation: Mapping[str, Any] | None = None,
    configuration: Mapping[str, Any] | None = None,
    privacy_default: str = "private",
    started_at: str | None = None,
) -> None:
    # A private placeholder keeps deployments self-contained. register_site() can
    # later add the human/public description without changing the site identity.
    conn.execute(
        """
        INSERT OR IGNORE INTO commons_sites(site_id, name, privacy_level)
        VALUES (?, ?, 'private')
        """,
        (site_id, site_id),
    )
    conn.execute(
        """
        INSERT INTO commons_deployments(
            deployment_id, sensor_id, site_id, purpose, started_at,
            orientation_json, configuration_json, privacy_default
        ) VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?)
        ON CONFLICT(deployment_id) DO UPDATE SET
            sensor_id=excluded.sensor_id,
            site_id=excluded.site_id,
            purpose=excluded.purpose,
            orientation_json=excluded.orientation_json,
            configuration_json=excluded.configuration_json,
            privacy_default=excluded.privacy_default
        """,
        (
            deployment_id,
            sensor_id,
            site_id,
            purpose,
            started_at,
            _json(orientation),
            _json(configuration),
            privacy_default,
        ),
    )
    conn.commit()


def ingest_media(
    conn: sqlite3.Connection,
    *,
    path: str | Path,
    event_type: str,
    source: str,
    site_id: str,
    deployment_id: str | None,
    captured_at: str,
    timezone: str,
    media_type: str,
    mime_type: str | None = None,
    privacy_level: str = "private",
    transform: Mapping[str, Any] | None = None,
    event_metadata: Mapping[str, Any] | None = None,
    media_metadata: Mapping[str, Any] | None = None,
    summary: str | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_s: float | None = None,
    manage_transaction: bool = True,
) -> IngestResult:
    """Register a media observation while retaining the source file in place.

    Identity combines site, deployment (when present), source, capture time,
    event type, and file digest. A retry returns the original IDs and does not
    create duplicate evidence.
    """
    media_path = resolve_no_symlinks(path, require_file=True)
    byte_size = media_path.stat().st_size
    sha256 = _hash_file(media_path)
    legacy_event_key = "|".join(
        [deployment_id or "no-deployment", captured_at, event_type, sha256]
    )
    event_key = "|".join(
        [site_id, deployment_id or "no-deployment", source, captured_at, event_type, sha256]
    )
    media_key = "|".join([event_key, str(media_path), media_type])
    event_id = _stable_id("evt", event_key)
    media_id = _stable_id("med", media_key)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        # Serialize the check-and-insert sequence across capture processes. A
        # second caller waits here, then observes the committed event below.
        if manage_transaction:
            conn.execute("BEGIN IMMEDIATE")
        if deployment_id is not None:
            deployment = conn.execute(
                "SELECT site_id FROM commons_deployments WHERE deployment_id=?",
                (deployment_id,),
            ).fetchone()
            if deployment is None:
                raise ValueError(f"unknown deployment: {deployment_id}")
            if deployment[0] != site_id:
                raise ValueError(
                    f"deployment {deployment_id} belongs to site {deployment[0]}, not {site_id}"
                )
        existing = conn.execute(
            "SELECT event_id FROM commons_events WHERE idempotency_key=?",
            (event_key,),
        ).fetchone()
        # v0.1 initially omitted site/source from deployed-event keys. Preserve
        # retry compatibility for those known-safe deployed records only. Never
        # use the legacy no-deployment namespace, which can cross site bounds.
        if not existing and deployment_id is not None:
            existing = conn.execute(
                """
                SELECT event_id FROM commons_events
                WHERE idempotency_key=? AND site_id=?
                  AND deployment_id=? AND source=?
                """,
                (legacy_event_key, site_id, deployment_id, source),
            ).fetchone()
        if existing:
            row = conn.execute(
                """
                SELECT media_id FROM commons_media
                WHERE event_id=? AND sha256=? AND media_type=?
                ORDER BY created_at LIMIT 1
                """,
                (existing[0], sha256, media_type),
            ).fetchone()
            if not row:
                raise RuntimeError("event exists without its expected media record")
            if manage_transaction:
                conn.commit()
            return IngestResult(existing[0], row[0], sha256, False)

        conn.execute(
            """
            INSERT INTO commons_events(
                event_id, idempotency_key, event_type, started_at, timezone,
                site_id, deployment_id, source, summary, privacy_level,
                review_state, publication_state, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unreviewed', 'blocked', ?)
            """,
            (
                event_id,
                event_key,
                event_type,
                captured_at,
                timezone,
                site_id,
                deployment_id,
                source,
                summary,
                privacy_level,
                _json(event_metadata),
            ),
        )
        conn.execute(
            """
            INSERT INTO commons_media(
                media_id, event_id, idempotency_key, media_type, path, sha256,
                byte_size, mime_type, width, height, duration_s, captured_at,
                transform_json, privacy_level, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                media_id,
                event_id,
                media_key,
                media_type,
                str(media_path),
                sha256,
                byte_size,
                mime_type,
                width,
                height,
                duration_s,
                captured_at,
                _json(transform),
                privacy_level,
                _json(media_metadata),
            ),
        )
        if manage_transaction:
            conn.commit()
    except Exception:
        if manage_transaction:
            conn.rollback()
        raise

    return IngestResult(event_id, media_id, sha256, True)
