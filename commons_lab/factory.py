"""Bounded orchestration for Pine Hollow's physical-ecology data factory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, Set
from urllib.parse import quote

from .acoustic import import_field_evidence
from .context import (
    ingest_observatory_snapshot,
    link_nearest_context,
    parse_aware_timestamp,
    read_observatory_updated_at,
)
from .incidents import import_field_incident_ledgers
from .jobs import claim_job, complete_job, enqueue_job, fail_job, heartbeat_job
from .safe_paths import resolve_no_symlinks


@dataclass(frozen=True)
class FactoryConfig:
    field_db_path: Path
    review_dir: Path
    bundle_dirs: tuple[Path, ...]
    observatory_path: Path
    data_root: Path
    camera_tolerance_seconds: float = 1200.0
    observatory_tolerance_seconds: float = 1800.0
    nvidia_smi: Path | str = "nvidia-smi"
    incident_dir: Path | None = None
    lease_seconds: int = 300
    heartbeat_interval_seconds: float = 100.0


@dataclass(frozen=True)
class EnqueueSummary:
    created: int
    existing: int
    job_ids: tuple[str, ...]
    omitted: tuple[str, ...]


@dataclass(frozen=True)
class FactoryOutcome:
    job_id: str
    job_type: str
    state: str
    attempts: int
    result: Mapping[str, Any] | None
    error: str | None


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        database_path: str | None,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float,
        clock: Callable[[], datetime],
    ) -> None:
        self.database_path = database_path
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.error: Exception | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.database_path is None or self.interval_seconds <= 0:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"data-factory-heartbeat-{self.job_id}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        if self.database_path is None:
            return
        database_path = self.database_path
        while not self._stop.wait(self.interval_seconds):
            conn = sqlite3.connect(database_path, timeout=30)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                heartbeat_job(
                    conn,
                    job_id=self.job_id,
                    worker_id=self.worker_id,
                    now=self.clock(),
                    lease_seconds=self.lease_seconds,
                )
            except Exception as exc:
                self.error = exc
                return
            finally:
                conn.close()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds + 1.0))


def _database_path(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2] or str(row[2]) == ":memory:":
        return None
    return str(row[2])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _field_watermark(config: FactoryConfig) -> str:
    digest = hashlib.sha256()
    review = resolve_no_symlinks(config.review_dir, require_dir=True)
    recording_ids: list[str] = []
    for category in ("events", "controls"):
        directory = review / category
        if not directory.is_dir():
            continue
        directory = resolve_no_symlinks(directory, require_dir=True)
        for audio in sorted(directory.glob("*.wav")):
            audio = resolve_no_symlinks(audio, require_file=True)
            stat = audio.stat()
            recording_ids.append(audio.stem)
            digest.update(
                f"{category}/{audio.name}|{stat.st_size}|{stat.st_mtime_ns}\n".encode()
            )
            digest.update(_sha256_file(audio).encode("ascii"))
            sidecar = audio.with_suffix(".json")
            if sidecar.is_file():
                sidecar = resolve_no_symlinks(sidecar, require_file=True)
                digest.update(_sha256_file(sidecar).encode())
    field_db = resolve_no_symlinks(config.field_db_path, require_file=True)
    if field_db.is_file() and recording_ids:
        source = sqlite3.connect(f"file:{quote(str(field_db))}?mode=ro", uri=True)
        try:
            for table, ordering in (
                ("recordings", "recording_id"),
                ("scores", "recording_id, bundle_id, start_sample"),
                ("events", "recording_id, bundle_id, start_sample, event_id"),
            ):
                for offset in range(0, len(recording_ids), 500):
                    batch = recording_ids[offset : offset + 500]
                    placeholders = ",".join("?" for _ in batch)
                    rows = source.execute(
                        f"SELECT * FROM {table} "
                        f"WHERE recording_id IN ({placeholders}) ORDER BY {ordering}",
                        batch,
                    ).fetchall()
                    digest.update(
                        json.dumps(
                            rows,
                            sort_keys=False,
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ).encode("utf-8")
                    )
        finally:
            source.close()
    for bundle in sorted(
        (resolve_no_symlinks(path, require_dir=True) for path in config.bundle_dirs),
        key=str,
    ):
        manifest = bundle / "SHA256SUMS"
        if manifest.is_file():
            manifest = resolve_no_symlinks(manifest, require_file=True)
            digest.update(str(bundle).encode())
            digest.update(manifest.read_bytes())
    return digest.hexdigest()


def _context_watermark(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT event_id, event_type, started_at, site_id
        FROM commons_events
        WHERE event_type IN ('acoustic_recording', 'fixed_camera_frame', 'observatory_snapshot')
        ORDER BY event_type, started_at, event_id
        """
    ).fetchall()
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _incident_watermark(directory: Path) -> str:
    directory = resolve_no_symlinks(directory, require_dir=True)
    digest = hashlib.sha256()
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix not in {".json", ".jsonl"}:
            continue
        if not path.is_file() or path.is_symlink():
            continue
        path = resolve_no_symlinks(path, require_file=True)
        digest.update(path.name.encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _configured_incident_dir(config: FactoryConfig) -> Path:
    configured = config.incident_dir
    if configured is None:
        configured = config.field_db_path.expanduser().absolute().parent / "incidents"
    return configured.expanduser().absolute()


def _retained_field_capture_times(config: FactoryConfig) -> list[datetime]:
    raw_field_db = config.field_db_path.expanduser().absolute()
    raw_review = config.review_dir.expanduser().absolute()
    if not raw_field_db.is_file() or not raw_review.is_dir():
        return []
    field_db = resolve_no_symlinks(raw_field_db, require_file=True)
    review = resolve_no_symlinks(raw_review, require_dir=True)
    recording_ids = sorted(
        {
            resolve_no_symlinks(audio, require_file=True).stem
            for category in ("events", "controls")
            for audio in (review / category).glob("*.wav")
            if audio.exists()
        }
    )
    if not recording_ids:
        return []
    source = sqlite3.connect(f"file:{quote(str(field_db))}?mode=ro", uri=True)
    try:
        captured: list[datetime] = []
        for offset in range(0, len(recording_ids), 500):
            batch = recording_ids[offset : offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = source.execute(
                f"SELECT captured_at FROM recordings WHERE recording_id IN ({placeholders})",
                batch,
            ).fetchall()
            captured.extend(parse_aware_timestamp(str(row[0])) for row in rows)
        return captured
    finally:
        source.close()


def _observatory_has_acoustic_context(
    conn: sqlite3.Connection,
    *,
    config: FactoryConfig,
    observed_at: datetime,
) -> bool:
    tolerance = config.observatory_tolerance_seconds
    if tolerance < 0:
        raise ValueError("observatory_tolerance_seconds must be non-negative")
    archived = [
        parse_aware_timestamp(str(row[0]))
        for row in conn.execute(
            """
            SELECT started_at FROM commons_events
            WHERE event_type='acoustic_recording' AND site_id='pine-hollow-private'
            """
        )
    ]
    field = _retained_field_capture_times(config)
    return any(
        abs((candidate - observed_at).total_seconds()) <= tolerance
        for candidate in (*archived, *field)
    )


def enqueue_cycle(
    conn: sqlite3.Connection,
    *,
    config: FactoryConfig,
    now: datetime | None = None,
) -> EnqueueSummary:
    """Enqueue only changed, allowlisted scheduled-CPU stages."""
    current = now or datetime.now(timezone.utc)
    created = existing = 0
    job_ids: list[str] = []
    omitted: list[str] = []

    candidates: list[tuple[str, str, Mapping[str, Any], int]] = []
    field_mark: str | None = None
    observatory_mark: str | None = None
    field_db = config.field_db_path.expanduser().resolve()
    review = config.review_dir.expanduser().resolve()
    bundles_ready = bool(config.bundle_dirs) and all(
        (Path(path).expanduser().resolve() / "SHA256SUMS").is_file()
        for path in config.bundle_dirs
    )
    if field_db.is_file() and review.is_dir() and bundles_ready:
        field_mark = _field_watermark(config)
        candidates.append(
            (
                "field_import",
                f"field:{field_mark}",
                {"source_watermark": field_mark},
                100,
            )
        )
    else:
        omitted.append("field_import: source unavailable")

    incident_dir = _configured_incident_dir(config)
    if incident_dir.is_dir():
        incident_mark = _incident_watermark(incident_dir)
        candidates.append(
            (
                "field_incident_import",
                f"field-incidents:{incident_mark}",
                {"source_watermark": incident_mark},
                95,
            )
        )
    else:
        omitted.append("field_incident_import: source unavailable")

    observatory = config.observatory_path.expanduser().absolute()
    if observatory.is_file():
        observed_at = read_observatory_updated_at(observatory)
        if _observatory_has_acoustic_context(
            conn, config=config, observed_at=observed_at
        ):
            observatory_mark = _sha256_file(observatory)
            candidates.append(
                (
                    "observatory_snapshot",
                    f"observatory:{observatory_mark}",
                    {
                        "source_sha256": observatory_mark,
                        "updated_at": observed_at.isoformat(timespec="microseconds"),
                        "relevance_tolerance_seconds": config.observatory_tolerance_seconds,
                    },
                    90,
                )
            )
        else:
            omitted.append("observatory_snapshot: outside acoustic tolerance")
    else:
        omitted.append("observatory_snapshot: source unavailable")

    event_mark = _context_watermark(conn)
    context_mark = hashlib.sha256(
        json.dumps(
            {
                "archived_events": event_mark,
                "field_source": field_mark,
                "observatory_source": observatory_mark,
                "camera_tolerance_seconds": config.camera_tolerance_seconds,
                "observatory_tolerance_seconds": config.observatory_tolerance_seconds,
                "method": "nearest_aware_timestamp_v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    candidates.append(
        (
            "context_join",
            f"context:{context_mark}",
            {
                "context_watermark": context_mark,
                "archived_event_watermark": event_mark,
                "field_source_watermark": field_mark,
                "observatory_source_watermark": observatory_mark,
                "camera_tolerance_seconds": config.camera_tolerance_seconds,
                "observatory_tolerance_seconds": config.observatory_tolerance_seconds,
            },
            50,
        )
    )
    candidates.append(
        (
            "sqlite_integrity",
            f"integrity:{current.astimezone(timezone.utc).date().isoformat()}",
            {"scope": "archive", "check": "integrity_and_foreign_keys"},
            10,
        )
    )

    for job_type, key, parameters, priority in candidates:
        outcome = enqueue_job(
            conn,
            job_type=job_type,
            idempotency_key=key,
            parameters=parameters,
            priority=priority,
            now=current,
        )
        job_ids.append(outcome.job_id)
        if outcome.created:
            created += 1
        else:
            existing += 1
    return EnqueueSummary(created, existing, tuple(job_ids), tuple(omitted))


def _sqlite_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    integrity = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
    foreign_keys = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    commons_violations = [row for row in foreign_keys if str(row[0]).startswith("commons_")]
    legacy_violations = [row for row in foreign_keys if not str(row[0]).startswith("commons_")]
    if integrity != ["ok"] or commons_violations:
        raise RuntimeError(
            "SQLite Commons integrity failed: "
            f"integrity={integrity!r}, commons_foreign_keys={commons_violations!r}"
        )
    return {
        "integrity_check": "ok",
        "commons_foreign_key_violations": 0,
        "legacy_foreign_key_violations": len(legacy_violations),
        "legacy_violation_sample": legacy_violations[:10],
    }


def _gpu_environment_probe(executable: Path | str) -> dict[str, Any]:
    command = [
        str(executable),
        "--query-gpu=name,memory.total,memory.free,utilization.gpu,driver_version",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    gpus: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            raise RuntimeError(f"unexpected nvidia-smi row: {line!r}")
        gpus.append(
            {
                "name": parts[0],
                "memory_total_mib": int(parts[1]),
                "memory_free_mib": int(parts[2]),
                "utilization_gpu_pct": int(parts[3]),
                "driver_version": parts[4],
            }
        )
    if not gpus:
        raise RuntimeError("nvidia-smi returned no GPUs")
    return {"gpus": gpus, "probe": "nvidia_smi_inventory_v1"}


def _execute(
    conn: sqlite3.Connection,
    *,
    config: FactoryConfig,
    job_type: str,
    parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    if job_type == "field_import":
        return asdict(
            import_field_evidence(
                conn,
                field_db_path=config.field_db_path,
                review_dir=config.review_dir,
                bundle_dirs=config.bundle_dirs,
            )
        )
    if job_type == "field_incident_import":
        return asdict(
            import_field_incident_ledgers(
                conn,
                incident_dir=_configured_incident_dir(config),
                data_root=config.data_root,
            )
        )
    if job_type == "observatory_snapshot":
        return asdict(
            ingest_observatory_snapshot(
                conn,
                snapshot_path=config.observatory_path,
                data_root=config.data_root,
            )
        )
    if job_type == "context_join":
        camera_tolerance = float(
            parameters.get("camera_tolerance_seconds", config.camera_tolerance_seconds)
        )
        observatory_tolerance = float(
            parameters.get(
                "observatory_tolerance_seconds", config.observatory_tolerance_seconds
            )
        )
        visual = link_nearest_context(
            conn,
            source_event_type="acoustic_recording",
            target_event_type="fixed_camera_frame",
            relation="nearest_visual_context",
            tolerance_seconds=camera_tolerance,
            method=f"nearest_aware_timestamp_v1:tolerance={camera_tolerance:g}s",
        )
        environment = link_nearest_context(
            conn,
            source_event_type="acoustic_recording",
            target_event_type="observatory_snapshot",
            relation="contemporaneous_environmental_context",
            tolerance_seconds=observatory_tolerance,
            method=f"nearest_aware_timestamp_v1:tolerance={observatory_tolerance:g}s",
        )
        return {
            "visual_links_inserted": visual,
            "environmental_links_inserted": environment,
            "causal_claim": False,
        }
    if job_type == "sqlite_integrity":
        return _sqlite_integrity(conn)
    if job_type == "gpu_environment_probe":
        return _gpu_environment_probe(config.nvidia_smi)
    raise ValueError(f"job handler is not allowlisted: {job_type}")


def run_jobs(
    conn: sqlite3.Connection,
    *,
    config: FactoryConfig,
    worker_id: str,
    allowed_energy_classes: Set[str],
    max_jobs: int,
    clock: Callable[[], datetime] | None = None,
) -> list[FactoryOutcome]:
    """Run at most max_jobs from explicitly allowed energy classes."""
    if max_jobs < 0:
        raise ValueError("max_jobs must be non-negative")
    if config.lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    if not 0 < config.heartbeat_interval_seconds < config.lease_seconds:
        raise ValueError("heartbeat interval must be positive and shorter than the lease")
    live_clock = clock or (lambda: datetime.now(timezone.utc))
    database_path = _database_path(conn)
    outcomes: list[FactoryOutcome] = []
    for _ in range(max_jobs):
        claim_time = live_clock()
        job = claim_job(
            conn,
            worker_id=worker_id,
            allowed_energy_classes=allowed_energy_classes,
            now=claim_time,
            lease_seconds=config.lease_seconds,
        )
        if job is None:
            break
        heartbeat = _LeaseHeartbeat(
            database_path=database_path,
            job_id=job.job_id,
            worker_id=worker_id,
            lease_seconds=config.lease_seconds,
            interval_seconds=config.heartbeat_interval_seconds,
            clock=live_clock,
        )
        heartbeat.start()
        try:
            result = _execute(
                conn,
                config=config,
                job_type=job.job_type,
                parameters=job.parameters,
            )
            heartbeat.stop()
            if heartbeat.error is not None:
                raise RuntimeError(f"job heartbeat failed: {heartbeat.error}")
            complete_job(
                conn,
                job_id=job.job_id,
                worker_id=worker_id,
                result=result,
                now=live_clock(),
            )
            outcomes.append(
                FactoryOutcome(
                    job.job_id,
                    job.job_type,
                    "success",
                    job.attempts,
                    result,
                    None,
                )
            )
        except Exception as exc:
            heartbeat.stop()
            error = f"{type(exc).__name__}: {exc}"[:2000]
            try:
                state = fail_job(
                    conn,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    error=error,
                    now=live_clock(),
                )
            except ValueError as lease_error:
                state = "running"
                error = f"{error}; failure record rejected: {lease_error}"[:2000]
            outcomes.append(
                FactoryOutcome(
                    job.job_id,
                    job.job_type,
                    state,
                    job.attempts,
                    None,
                    error,
                )
            )
    return outcomes
