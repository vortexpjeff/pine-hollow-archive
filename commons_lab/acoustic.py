"""Strict acoustic evidence import and review for the Commons Lab.

The deployed field listener remains authoritative for capture and scoring.  This
module opens its SQLite ledger read-only, verifies retained evidence and bundle
identity, then adds private archive records without copying or mutating sources.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast
from urllib.parse import quote

from .ingest import ingest_media, register_deployment, register_sensor, register_site
from .safe_paths import UnsafePathError, resolve_no_symlinks

SITE_ID = "pine-hollow-private"
SENSOR_ID = "birdnet-pi-acoustic-stream"
DEPLOYMENT_ID = "birdnet-pi-acoustic-v1"
TIMEZONE = "America/New_York"


class FieldEvidenceError(ValueError):
    """Raised when field evidence cannot satisfy the archival contract."""


@dataclass(frozen=True)
class BundleDescriptor:
    bundle_id: str
    model_slug: str
    class_name: str
    threshold: float
    sample_rate: int
    score_semantics: str
    preprocess_recipe_id: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ImportSummary:
    discovered: int
    imported: int
    existing: int
    windows_inserted: int
    assertions_inserted: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _canonical_json(value: Mapping[str, Any] | Sequence[Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalized_aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"reviewed_at timestamp requires a timezone: {value}")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _strict_json(path: Path) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise FieldEvidenceError(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise FieldEvidenceError(f"invalid JSON evidence: {path}: {exc}") from exc


def _parse_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise FieldEvidenceError(f"cannot read bundle checksums: {path}") from exc
    checksums: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or name in checksums
        ):
            raise FieldEvidenceError(f"invalid bundle checksum line: {line!r}")
        checksums[name] = digest
    if list(checksums) != sorted(checksums) or set(checksums) != {"model.json", "weights.npz"}:
        raise FieldEvidenceError("bundle checksum manifest does not match the field contract")
    return checksums


def bundle_id_from_directory(directory: str | Path) -> BundleDescriptor:
    """Verify a deployed field bundle and reproduce the listener's bundle ID."""
    try:
        root = resolve_no_symlinks(directory, require_dir=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise FieldEvidenceError(f"invalid bundle path: {exc}") from exc
    expected = {"model.json", "weights.npz", "SHA256SUMS"}
    entries = {item.name for item in root.iterdir()}
    if entries != expected:
        raise FieldEvidenceError(f"bundle file set does not match contract: {root}")
    for name in expected:
        try:
            resolve_no_symlinks(root / name, require_file=True)
        except (UnsafePathError, FileNotFoundError, ValueError) as exc:
            raise FieldEvidenceError(f"invalid bundle member: {exc}") from exc

    checksums = _parse_checksums(root / "SHA256SUMS")
    for name, expected_hash in checksums.items():
        if _sha256_file(root / name) != expected_hash:
            raise FieldEvidenceError(f"bundle checksum mismatch: {root / name}")
    metadata = _strict_json(root / "model.json")
    required = {
        "bundle_schema_version",
        "class_name",
        "event_threshold",
        "feature_dimension",
        "model_slug",
        "perch_model_tree_sha256",
        "preprocess_recipe_id",
        "score_semantics",
        "runtime_event_config",
    }
    if not isinstance(metadata, dict) or not required.issubset(metadata):
        raise FieldEvidenceError(f"bundle metadata is incomplete: {root}")
    runtime = metadata["runtime_event_config"]
    if not isinstance(runtime, dict) or "sample_rate" not in runtime:
        raise FieldEvidenceError(f"bundle runtime configuration is incomplete: {root}")
    threshold = float(metadata["event_threshold"])
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise FieldEvidenceError(f"bundle threshold is invalid: {root}")
    sample_rate = int(runtime["sample_rate"])
    if sample_rate <= 0:
        raise FieldEvidenceError(f"bundle sample rate is invalid: {root}")
    bundle_id = hashlib.sha256(
        (checksums["model.json"] + checksums["weights.npz"]).encode("ascii")
    ).hexdigest()
    return BundleDescriptor(
        bundle_id=bundle_id,
        model_slug=str(metadata["model_slug"]),
        class_name=str(metadata["class_name"]),
        threshold=threshold,
        sample_rate=sample_rate,
        score_semantics=str(metadata["score_semantics"]),
        preprocess_recipe_id=str(metadata["preprocess_recipe_id"]),
        metadata=metadata,
    )


def load_bundle_catalog(bundle_dirs: Sequence[str | Path]) -> dict[str, BundleDescriptor]:
    catalog: dict[str, BundleDescriptor] = {}
    for directory in bundle_dirs:
        bundle = bundle_id_from_directory(directory)
        if bundle.bundle_id in catalog:
            raise FieldEvidenceError(f"duplicate deployed bundle ID: {bundle.bundle_id}")
        catalog[bundle.bundle_id] = bundle
    if not catalog:
        raise FieldEvidenceError("at least one deployed bundle is required")
    return catalog


def _read_only_connection(path: Path) -> sqlite3.Connection:
    try:
        resolved = resolve_no_symlinks(path, require_file=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise FieldEvidenceError(f"invalid field ledger path: {exc}") from exc
    uri = f"file:{quote(str(resolved))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    required = {"recordings", "scores", "events"}
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not required.issubset(tables):
        connection.close()
        raise FieldEvidenceError("field ledger schema is incomplete")
    return connection


def _discover_evidence(review_dir: Path) -> list[tuple[str, Path]]:
    try:
        root = resolve_no_symlinks(review_dir, require_dir=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise FieldEvidenceError(f"invalid review evidence root: {exc}") from exc
    result: list[tuple[str, Path]] = []
    for category in ("events", "controls"):
        directory = root / category
        if not directory.exists():
            continue
        if not directory.is_dir() or directory.is_symlink():
            raise FieldEvidenceError(f"invalid review evidence directory: {directory}")
        for audio in sorted(directory.glob("*.wav")):
            try:
                resolved_audio = resolve_no_symlinks(audio, require_file=True)
            except (UnsafePathError, FileNotFoundError, ValueError) as exc:
                raise FieldEvidenceError(f"invalid retained audio path: {exc}") from exc
            result.append((category, resolved_audio))
    return result


def _validate_recording(
    source: sqlite3.Connection,
    *,
    category: str,
    audio: Path,
    catalog: Mapping[str, BundleDescriptor],
) -> tuple[sqlite3.Row, dict[str, Any], list[sqlite3.Row], list[sqlite3.Row]]:
    recording_id = audio.stem
    if len(recording_id) != 64 or any(ch not in "0123456789abcdef" for ch in recording_id):
        raise FieldEvidenceError(f"retained audio filename is not a SHA-256 ID: {audio}")
    digest = _sha256_file(audio)
    if digest != recording_id:
        raise FieldEvidenceError(f"retained audio SHA-256 mismatch: {audio}")
    sidecar_path = audio.with_suffix(".json")
    try:
        sidecar_path = resolve_no_symlinks(sidecar_path, require_file=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise FieldEvidenceError(f"invalid retained audio sidecar: {exc}") from exc
    sidecar = _strict_json(sidecar_path)
    if not isinstance(sidecar, dict) or sidecar.get("recording_id") != recording_id:
        raise FieldEvidenceError(f"retained sidecar recording ID mismatch: {sidecar_path}")

    recording = source.execute(
        "SELECT * FROM recordings WHERE recording_id=?", (recording_id,)
    ).fetchone()
    if recording is None:
        raise FieldEvidenceError(f"retained recording is absent from field ledger: {recording_id}")
    if (
        recording["source_sha256"] != recording_id
        or int(recording["source_bytes"]) != audio.stat().st_size
    ):
        raise FieldEvidenceError(f"field ledger evidence identity mismatch: {recording_id}")
    try:
        metadata = json.loads(recording["metadata_json"])
    except json.JSONDecodeError as exc:
        raise FieldEvidenceError(f"invalid field recording metadata: {recording_id}") from exc
    if not isinstance(metadata, dict) or metadata.get("recording_id") != recording_id:
        raise FieldEvidenceError(f"field recording metadata mismatch: {recording_id}")

    scores = list(
        source.execute(
            "SELECT * FROM scores WHERE recording_id=? ORDER BY bundle_id, start_sample",
            (recording_id,),
        )
    )
    events = list(
        source.execute(
            "SELECT * FROM events WHERE recording_id=? ORDER BY bundle_id, start_sample",
            (recording_id,),
        )
    )
    if not scores:
        raise FieldEvidenceError(f"field recording has no model scores: {recording_id}")
    sidecar_bundles = sidecar.get("bundles")
    if not isinstance(sidecar_bundles, list):
        raise FieldEvidenceError(f"retained sidecar bundle list is invalid: {recording_id}")
    sidecar_by_id: dict[str, dict[str, Any]] = {}
    for item in sidecar_bundles:
        if not isinstance(item, dict) or not isinstance(item.get("bundle_id"), str):
            raise FieldEvidenceError(f"retained sidecar bundle entry is invalid: {recording_id}")
        bundle_id = item["bundle_id"]
        if bundle_id in sidecar_by_id:
            raise FieldEvidenceError(f"duplicate sidecar bundle ID: {bundle_id}")
        sidecar_by_id[bundle_id] = item

    score_bundle_ids = {str(row["bundle_id"]) for row in scores}
    if score_bundle_ids != set(sidecar_by_id):
        raise FieldEvidenceError(f"sidecar and ledger bundle sets disagree: {recording_id}")
    for bundle_id in score_bundle_ids:
        if bundle_id not in catalog:
            raise FieldEvidenceError(f"field score uses an unknown deployed bundle: {bundle_id}")
        bundle = catalog[bundle_id]
        item = sidecar_by_id[bundle_id]
        if item.get("class_name") != bundle.class_name:
            raise FieldEvidenceError(f"sidecar class disagrees with deployed bundle: {bundle_id}")
        bundle_scores = [row for row in scores if row["bundle_id"] == bundle_id]
        sidecar_scores = item.get("scores")
        if not isinstance(sidecar_scores, list) or len(sidecar_scores) != len(bundle_scores):
            raise FieldEvidenceError(f"sidecar score count disagrees with ledger: {bundle_id}")
        if any(
            not math.isclose(float(sidecar_score), float(row["score"]), rel_tol=0.0, abs_tol=1e-12)
            for sidecar_score, row in zip(sidecar_scores, bundle_scores, strict=True)
        ):
            raise FieldEvidenceError(f"sidecar scores disagree with ledger: {bundle_id}")
        source_event_ids = {str(row["event_id"]) for row in events if row["bundle_id"] == bundle_id}
        listed_events = item.get("events")
        if not isinstance(listed_events, list) or set(map(str, listed_events)) != source_event_ids:
            raise FieldEvidenceError(f"sidecar events disagree with ledger: {bundle_id}")
    if category == "controls" and events:
        raise FieldEvidenceError(f"control evidence contains threshold events: {recording_id}")
    return recording, metadata, scores, events


def _register_acoustic_source(conn: sqlite3.Connection) -> None:
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
        sensor_id=SENSOR_ID,
        name="BirdNET-Pi acoustic recording stream",
        sensor_type="microphone",
        host="BirdNET-Pi to Athena durable transport",
        privacy_default="private",
        metadata={"raw_ambient_audio_public": False},
    )
    register_deployment(
        conn,
        deployment_id=DEPLOYMENT_ID,
        sensor_id=SENSOR_ID,
        site_id=SITE_ID,
        purpose="Private continuous bioacoustic field listening",
        privacy_default="private",
        configuration={
            "recording_seconds": 15,
            "archive_policy": "retained_events_and_deterministic_controls_only",
            "source_mutation": False,
        },
    )


def _source_event_for_window(
    events: Iterable[sqlite3.Row], bundle_id: str, start_sample: int, end_sample: int
) -> str | None:
    matches = [
        str(row["event_id"])
        for row in events
        if row["bundle_id"] == bundle_id
        and int(row["start_sample"]) <= start_sample
        and int(row["end_sample"]) >= end_sample
    ]
    if len(matches) > 1:
        raise FieldEvidenceError("one model window belongs to multiple source events")
    return matches[0] if matches else None


def import_field_evidence(
    conn: sqlite3.Connection,
    *,
    field_db_path: str | Path,
    review_dir: str | Path,
    bundle_dirs: Sequence[str | Path],
    limit: int | None = None,
    dry_run: bool = False,
) -> ImportSummary:
    """Import retained field evidence without writing to the source ledger/files."""
    catalog = load_bundle_catalog(bundle_dirs)
    evidence = _discover_evidence(Path(review_dir))
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        evidence = evidence[:limit]
    imported = existing = windows_inserted = assertions_inserted = 0
    source = _read_only_connection(Path(field_db_path))
    try:
        validated = [
            (category, audio, *_validate_recording(source, category=category, audio=audio, catalog=catalog))
            for category, audio in evidence
        ]
        if dry_run:
            return ImportSummary(len(evidence), 0, 0, 0, 0)
        _register_acoustic_source(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        for category, audio, recording, metadata, scores, events in validated:
            sample_rate = catalog[str(scores[0]["bundle_id"])].sample_rate
            duration_s = max(int(row["end_sample"]) for row in scores) / sample_rate
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = ingest_media(
                    conn,
                    path=audio,
                    event_type="acoustic_recording",
                    source="insectnet_field_listener",
                    site_id=SITE_ID,
                    deployment_id=DEPLOYMENT_ID,
                    captured_at=str(recording["captured_at"]),
                    timezone=TIMEZONE,
                    media_type="audio",
                    mime_type="audio/wav",
                    privacy_level="private",
                    transform={
                        "kind": "retained_source_reference",
                        "copied": False,
                        "source_hash_verified": True,
                    },
                    event_metadata={
                        "field_recording_id": recording["recording_id"],
                        "field_category": category,
                        "field_metadata": metadata,
                    },
                    media_metadata={
                        "source_ledger": str(Path(field_db_path).expanduser().resolve()),
                        "source_sidecar": str(audio.with_suffix('.json')),
                        "source_read_only": True,
                    },
                    summary=f"Retained field-listener {category[:-1] if category.endswith('s') else category}",
                    duration_s=duration_s,
                    manage_transaction=False,
                )
            except Exception:
                conn.rollback()
                raise
            if result.created:
                imported += 1
            else:
                existing += 1
            try:
                bundle_windows: dict[str, list[sqlite3.Row]] = {}
                for row in scores:
                    bundle_id = str(row["bundle_id"])
                    bundle = catalog[bundle_id]
                    start_sample = int(row["start_sample"])
                    end_sample = int(row["end_sample"])
                    source_event_id = _source_event_for_window(
                        events, bundle_id, start_sample, end_sample
                    )
                    window_key = f"{recording['recording_id']}|{bundle_id}|{start_sample}"
                    window_id = _stable_id("win", window_key)
                    window_values = (
                        window_id,
                        result.event_id,
                        result.media_id,
                        recording["recording_id"],
                        source_event_id,
                        bundle_id,
                        bundle.model_slug,
                        bundle.class_name,
                        start_sample,
                        end_sample,
                        bundle.sample_rate,
                        float(row["score"]),
                        float(row["raw_score"]),
                        bundle.threshold,
                        int(float(row["score"]) >= bundle.threshold),
                        bundle.score_semantics,
                        bundle.preprocess_recipe_id,
                        _canonical_json({"source": "field_listener_ledger"}),
                    )
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO commons_acoustic_windows(
                            window_id, event_id, media_id, source_recording_id,
                            source_event_id, bundle_id, model_slug, class_name,
                            start_sample, end_sample, sample_rate, score, raw_score,
                            threshold, crosses_threshold, score_semantics,
                            preprocess_recipe_id, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        window_values,
                    )
                    if cursor.rowcount == 0:
                        archived = conn.execute(
                            """
                            SELECT window_id, event_id, media_id, source_recording_id,
                                   source_event_id, bundle_id, model_slug, class_name,
                                   start_sample, end_sample, sample_rate, score, raw_score,
                                   threshold, crosses_threshold, score_semantics,
                                   preprocess_recipe_id, metadata_json
                            FROM commons_acoustic_windows
                            WHERE source_recording_id=? AND bundle_id=? AND start_sample=?
                            """,
                            (recording["recording_id"], bundle_id, start_sample),
                        ).fetchone()
                        if archived is None:
                            raise FieldEvidenceError(
                                "acoustic-window conflict did not resolve to an existing row"
                            )
                        differs = any(
                            not math.isclose(
                                float(cast(Any, actual)),
                                float(cast(Any, expected)),
                                rel_tol=0.0,
                                abs_tol=1e-12,
                            )
                            if index in {11, 12, 13}
                            else actual != expected
                            for index, (actual, expected) in enumerate(
                                zip(archived, window_values)
                            )
                        )
                        if differs:
                            raise FieldEvidenceError(
                                "archived acoustic window differs from replayed field evidence: "
                                f"recording={recording['recording_id']} "
                                f"bundle={bundle_id} start_sample={start_sample}"
                            )
                    windows_inserted += cursor.rowcount
                    bundle_windows.setdefault(bundle_id, []).append(row)
                for bundle_id, rows in bundle_windows.items():
                    bundle = catalog[bundle_id]
                    maximum = max(float(row["score"]) for row in rows)
                    assertion_id = _stable_id(
                        "ast", f"{result.event_id}|model|{bundle_id}"
                    )
                    assertion_value = _canonical_json(
                        {
                            "bundle_id": bundle_id,
                            "class_name": bundle.class_name,
                            "max_score": maximum,
                            "threshold": bundle.threshold,
                            "crosses_threshold": maximum >= bundle.threshold,
                            "score_semantics": bundle.score_semantics,
                            "window_count": len(rows),
                        }
                    )
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO commons_assertions(
                            assertion_id, event_id, media_id, subject, predicate,
                            value_json, source_type, source_name, source_version,
                            confidence, authority
                        ) VALUES (?, ?, ?, ?, 'model_score_for_class', ?, 'model', ?, ?, NULL, 'candidate')
                        """,
                        (
                            assertion_id,
                            result.event_id,
                            result.media_id,
                            bundle.class_name,
                            assertion_value,
                            bundle.model_slug,
                            bundle_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        archived_assertion = conn.execute(
                            """
                            SELECT event_id, media_id, subject, predicate, value_json,
                                   source_type, source_name, source_version,
                                   confidence, authority
                            FROM commons_assertions WHERE assertion_id=?
                            """,
                            (assertion_id,),
                        ).fetchone()
                        expected_assertion = (
                            result.event_id,
                            result.media_id,
                            bundle.class_name,
                            "model_score_for_class",
                            assertion_value,
                            "model",
                            bundle.model_slug,
                            bundle_id,
                            None,
                            "candidate",
                        )
                        if archived_assertion != expected_assertion:
                            raise FieldEvidenceError(
                                "archived model assertion differs from replayed field evidence: "
                                f"event={result.event_id} bundle={bundle_id}"
                            )
                    assertions_inserted += cursor.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    finally:
        source.close()
    return ImportSummary(
        discovered=len(evidence),
        imported=imported,
        existing=existing,
        windows_inserted=windows_inserted,
        assertions_inserted=assertions_inserted,
    )


def score_band(score: float) -> str:
    if score >= 0.9999:
        return "ge_0.9999"
    if score >= 0.999:
        return "0.999_to_0.9999"
    if score >= 0.99:
        return "0.99_to_0.999"
    if score >= 0.9:
        return "0.9_to_0.99"
    if score >= 0.5:
        return "0.5_to_0.9"
    return "lt_0.5"


def populate_calibration_queue(
    conn: sqlite3.Connection,
    *,
    bundle_id: str,
    class_name: str,
    per_band: int = 10,
) -> int:
    """Queue deterministic per-recording maxima across score bands."""
    if per_band < 1:
        raise ValueError("per_band must be positive")
    rows = conn.execute(
        """
        SELECT event_id, MAX(score) AS max_score
        FROM commons_acoustic_windows
        WHERE bundle_id=? AND class_name=?
        GROUP BY event_id ORDER BY max_score DESC, event_id
        """,
        (bundle_id, class_name),
    ).fetchall()
    grouped: dict[str, list[tuple[str, float]]] = {}
    for event_id, maximum in rows:
        band = score_band(float(maximum))
        grouped.setdefault(band, []).append((str(event_id), float(maximum)))
    inserted = 0
    conn.execute("PRAGMA foreign_keys=ON")
    for band, candidates in grouped.items():
        # Stable hash ordering avoids a newest-only review sample within a band.
        ordered = sorted(
            candidates,
            key=lambda item: hashlib.sha256(
                f"{bundle_id}|{band}|{item[0]}".encode("utf-8")
            ).hexdigest(),
        )[:per_band]
        for event_id, maximum in ordered:
            queue_id = _stable_id("que", f"{event_id}|{bundle_id}|{band}")
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO commons_review_queue(
                    queue_id, event_id, bundle_id, class_name, score_band,
                    priority, reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'score_stratified_calibration', ?)
                """,
                (
                    queue_id,
                    event_id,
                    bundle_id,
                    class_name,
                    band,
                    maximum,
                    _canonical_json(
                        {
                            "max_score": maximum,
                            "selection": "deterministic_hash_within_score_band",
                            "training_eligible": False,
                        }
                    ),
                ),
            )
            inserted += cursor.rowcount
    conn.commit()
    return inserted


def record_human_acoustic_review(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    media_id: str,
    bundle_id: str,
    class_name: str,
    present: bool | None,
    certainty: str,
    reviewer: str,
    start_sample: int,
    end_sample: int,
    reviewed_at: str,
    supersedes_assertion_id: str | None = None,
    notes: str | None = None,
    training_eligible: bool | None = None,
    review_context: Mapping[str, Any] | None = None,
    manage_transaction: bool = True,
    complete_calibration_queue: bool = True,
    mark_event_reviewed: bool = True,
) -> str:
    """Append a span-bounded human assertion; corrections supersede, never edit."""
    if certainty not in {"confirmed", "probable", "uncertain"}:
        raise ValueError("certainty must be confirmed, probable, or uncertain")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if start_sample < 0 or end_sample <= start_sample:
        raise ValueError("review span is invalid")
    reviewed_at = _normalized_aware_timestamp(reviewed_at)
    media = conn.execute(
        "SELECT 1 FROM commons_media WHERE media_id=? AND event_id=?",
        (media_id, event_id),
    ).fetchone()
    if media is None:
        raise ValueError("media does not belong to the reviewed event")
    windows = conn.execute(
        """
        SELECT start_sample, end_sample, class_name
        FROM commons_acoustic_windows
        WHERE event_id=? AND media_id=? AND bundle_id=?
        ORDER BY start_sample, end_sample
        """,
        (event_id, media_id, bundle_id),
    ).fetchall()
    if not windows:
        raise ValueError("review has no imported acoustic evidence for this bundle")
    if {str(row[2]) for row in windows} != {class_name}:
        raise ValueError("class does not match the imported bundle windows")
    covered_until = start_sample
    for window_start, window_end, _ in windows:
        window_start = int(window_start)
        window_end = int(window_end)
        if window_end <= covered_until or window_start >= end_sample:
            continue
        if window_start > covered_until:
            break
        covered_until = max(covered_until, min(window_end, end_sample))
        if covered_until >= end_sample:
            break
    if covered_until < end_sample:
        raise ValueError("review span is not continuously covered by imported windows")
    if supersedes_assertion_id is not None:
        prior = conn.execute(
            """
            SELECT media_id, subject, value_json FROM commons_assertions
            WHERE assertion_id=? AND event_id=? AND source_type='human'
            """,
            (supersedes_assertion_id, event_id),
        ).fetchone()
        if prior is None:
            raise ValueError("superseded assertion is not a human review of this event")
        try:
            prior_value = json.loads(str(prior[2]))
        except json.JSONDecodeError as exc:
            raise ValueError("superseded assertion has invalid review provenance") from exc
        same_lineage = (
            str(prior[0]) == media_id
            and str(prior[1]) == class_name
            and prior_value.get("bundle_id") == bundle_id
            and prior_value.get("class_name") == class_name
            and prior_value.get("start_sample") == start_sample
            and prior_value.get("end_sample") == end_sample
        )
        if not same_lineage:
            raise ValueError("superseded assertion must belong to the same review lineage")
    value = {
        "bundle_id": bundle_id,
        "class_name": class_name,
        "present": None if present is None else bool(present),
        "certainty": certainty,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "start_sample": start_sample,
        "end_sample": end_sample,
        "supersedes_assertion_id": supersedes_assertion_id,
        "notes": notes,
        "training_eligible": (
            certainty == "confirmed"
            if training_eligible is None
            else bool(training_eligible)
        ),
    }
    if review_context:
        value.update(dict(review_context))
    key = _canonical_json(value)
    assertion_id = _stable_id("ast", f"{event_id}|human|{key}")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if manage_transaction:
            conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO commons_assertions(
                assertion_id, event_id, media_id, subject, predicate,
                value_json, source_type, source_name, source_version,
                confidence, authority, created_at
            ) VALUES (?, ?, ?, ?, 'human_review_for_class', ?, 'human', ?, NULL,
                      NULL, 'reviewed', ?)
            """,
            (
                assertion_id,
                event_id,
                media_id,
                class_name,
                key,
                reviewer,
                reviewed_at,
            ),
        )
        if mark_event_reviewed:
            conn.execute(
                "UPDATE commons_events SET review_state='reviewed' WHERE event_id=?",
                (event_id,),
            )
        if complete_calibration_queue:
            conn.execute(
                """
                UPDATE commons_review_queue
                SET state='completed', updated_at=?
                WHERE event_id=? AND bundle_id=? AND state IN ('pending', 'in_review')
                """,
                (reviewed_at, event_id, bundle_id),
            )
        if manage_transaction:
            conn.commit()
    except Exception:
        if manage_transaction:
            conn.rollback()
        raise
    return assertion_id
