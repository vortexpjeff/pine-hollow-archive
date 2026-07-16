"""Explicitly non-causal temporal context for Commons Lab events."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ingest import IngestResult, ingest_media, register_deployment, register_sensor, register_site
from .safe_paths import UnsafePathError, resolve_no_symlinks

SITE_ID = "pine-hollow-private"
OBSERVATORY_SENSOR_ID = "vortex-observatory-aggregator"
OBSERVATORY_DEPLOYMENT_ID = "observatory-context-v1"


class ContextError(ValueError):
    """Raised when temporal context cannot satisfy its evidence contract."""


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_aware_timestamp(value: str) -> datetime:
    """Parse ISO-8601 and reject timestamps without an explicit UTC offset."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContextError(f"invalid ISO-8601 timestamp: {value}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContextError(f"timestamp has no timezone offset: {value}")
    return result.astimezone(timezone.utc)


def link_nearest_context(
    conn: sqlite3.Connection,
    *,
    source_event_type: str,
    target_event_type: str,
    relation: str,
    tolerance_seconds: float,
    method: str = "nearest_aware_timestamp_v1",
) -> int:
    """Link each source to the nearest same-site target inside a fixed tolerance.

    The signed offset is target minus source.  The link metadata explicitly
    denies a causal claim; this function only establishes temporal context.
    """
    if tolerance_seconds < 0:
        raise ValueError("tolerance_seconds must be non-negative")
    if source_event_type == target_event_type:
        raise ValueError("source and target event types must differ")
    sources = conn.execute(
        """
        SELECT event_id, site_id, started_at FROM commons_events
        WHERE event_type=? ORDER BY started_at, event_id
        """,
        (source_event_type,),
    ).fetchall()
    targets = conn.execute(
        """
        SELECT event_id, site_id, started_at FROM commons_events
        WHERE event_type=? ORDER BY started_at, event_id
        """,
        (target_event_type,),
    ).fetchall()
    parsed_targets = [
        (str(event_id), str(site_id), parse_aware_timestamp(str(started_at)))
        for event_id, site_id, started_at in targets
    ]
    inserted = 0
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for source_event_id, site_id, started_at in sources:
            source_time = parse_aware_timestamp(str(started_at))
            candidates: list[tuple[float, str, float]] = []
            for target_event_id, target_site_id, target_time in parsed_targets:
                if str(site_id) != target_site_id:
                    continue
                offset = (target_time - source_time).total_seconds()
                absolute = abs(offset)
                if absolute <= tolerance_seconds:
                    candidates.append((absolute, target_event_id, offset))
            if not candidates:
                continue
            _, target_event_id, offset = min(
                candidates, key=lambda item: (item[0], item[1])
            )
            key = f"{source_event_id}|{target_event_id}|{relation}|{method}"
            confidence = (
                1.0
                if tolerance_seconds == 0
                else max(0.0, 1.0 - abs(offset) / tolerance_seconds)
            )
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO commons_event_links(
                    link_id, source_event_id, target_event_id, relation,
                    method, offset_seconds, confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _stable_id("lnk", key),
                    source_event_id,
                    target_event_id,
                    relation,
                    method,
                    offset,
                    confidence,
                    _canonical_json(
                        {
                            "causal_claim": False,
                            "interpretation": "temporal_context_only",
                            "source_event_type": source_event_type,
                            "target_event_type": target_event_type,
                            "tolerance_seconds": tolerance_seconds,
                        }
                    ),
                ),
            )
            inserted += cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return inserted


def _read_snapshot(path: Path) -> tuple[bytes, dict[str, Any], datetime]:
    try:
        source = resolve_no_symlinks(path, require_file=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise ContextError(f"invalid snapshot path: {exc}") from exc
    payload = source.read_bytes()
    if len(payload) > 5 * 1024 * 1024:
        raise ContextError("Observatory snapshot exceeds 5 MiB")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContextError(f"duplicate Observatory JSON key: {key}")
            result[key] = value
        return result

    try:
        document = json.loads(payload, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContextError(f"invalid Observatory JSON: {source}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("updated"), str):
        raise ContextError("Observatory snapshot has no updated timestamp")
    observed = parse_aware_timestamp(document["updated"])
    return payload, document, observed


def read_observatory_updated_at(snapshot_path: Path | str) -> datetime:
    """Return the validated UTC `updated` time without ingesting the snapshot."""
    return _read_snapshot(Path(snapshot_path))[2]


def _promote_snapshot(payload: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256(payload).hexdigest()
    if destination.exists():
        if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ContextError(f"immutable snapshot destination conflicts: {destination}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _reject_symlinked_destination(root: Path, destination_parent: Path) -> None:
    if root.is_symlink():
        raise ContextError(f"snapshot data root is a symlink: {root}")
    resolved_root = root.resolve()
    try:
        relative = destination_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise ContextError("snapshot destination escapes the private data root") from exc
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ContextError(f"snapshot destination ancestor is a symlink: {current}")


def _register_observatory(conn: sqlite3.Connection) -> None:
    register_site(
        conn,
        site_id=SITE_ID,
        name="Pine Hollow private research site",
        public_region="Appalachian hollow, East Tennessee",
        privacy_level="private",
        metadata={"exact_location_public": False},
    )
    register_sensor(
        conn,
        sensor_id=OBSERVATORY_SENSOR_ID,
        name="Vortex Observatory local aggregator",
        sensor_type="environmental_data_aggregator",
        host="Athena",
        privacy_default="private",
        metadata={"source_surface": "existing Vortex Observatory", "network_fetch": False},
    )
    register_deployment(
        conn,
        deployment_id=OBSERVATORY_DEPLOYMENT_ID,
        sensor_id=OBSERVATORY_SENSOR_ID,
        site_id=SITE_ID,
        purpose="Immutable local environmental context snapshots",
        privacy_default="private",
        configuration={
            "capture_mode": "copy_local_generated_payload",
            "causal_claim": False,
            "public_website_mutation": False,
        },
    )


def ingest_observatory_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_path: str | Path,
    data_root: str | Path,
) -> IngestResult:
    """Copy one mutable Observatory payload into immutable private evidence."""
    try:
        source = resolve_no_symlinks(snapshot_path, require_file=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise ContextError(f"invalid snapshot path: {exc}") from exc
    payload, document, observed = _read_snapshot(source)
    digest = hashlib.sha256(payload).hexdigest()
    raw_root = Path(data_root).expanduser().absolute()
    if raw_root.is_symlink():
        raise ContextError(f"snapshot data root is a symlink: {raw_root}")
    root = raw_root.resolve()
    destination = (
        root
        / "observatory_snapshots"
        / observed.strftime("%Y")
        / observed.strftime("%m")
        / observed.strftime("%d")
        / f"observatory_{observed.strftime('%Y%m%dT%H%M%SZ')}_{digest[:16]}.json"
    )
    _reject_symlinked_destination(raw_root, destination.parent)
    _promote_snapshot(payload, destination)
    _register_observatory(conn)
    return ingest_media(
        conn,
        path=destination,
        event_type="observatory_snapshot",
        source="vortex_observatory_local",
        site_id=SITE_ID,
        deployment_id=OBSERVATORY_DEPLOYMENT_ID,
        captured_at=document["updated"],
        timezone="UTC",
        media_type="data",
        mime_type="application/json",
        privacy_level="private",
        transform={
            "kind": "immutable_snapshot_copy",
            "source_path": str(source),
            "source_sha256": digest,
        },
        event_metadata={
            "causal_claim": False,
            "top_level_sections": sorted(document),
        },
        media_metadata={
            "immutable": True,
            "source_overwritten_in_place": True,
        },
        summary="Private Observatory environmental context snapshot",
    )
