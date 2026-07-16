"""Durable, allowlisted job ledger for the physical-ecology data factory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Set

JOB_ENERGY_CLASS = {
    "field_import": "scheduled_cpu",
    "field_incident_import": "scheduled_cpu",
    "observatory_snapshot": "scheduled_cpu",
    "context_join": "scheduled_cpu",
    "sqlite_integrity": "scheduled_cpu",
    "gpu_environment_probe": "deferrable_gpu",
}
ENERGY_CLASSES = {
    "critical_continuous",
    "scheduled_cpu",
    "deferrable_gpu",
    "manual_high_energy",
}
TERMINAL_STATES = {"success", "skipped", "failed", "cancelled"}


@dataclass(frozen=True)
class EnqueueResult:
    job_id: str
    created: bool
    state: str


@dataclass(frozen=True)
class Job:
    job_id: str
    job_type: str
    energy_class: str
    state: str
    priority: int
    attempts: int
    max_attempts: int
    input_event_id: str | None
    parameters: Mapping[str, Any]
    lease_owner: str | None
    leased_until: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("job timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _aware_utc(value).isoformat(timespec="microseconds")


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("job parameters must be finite JSON data") from exc


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _transition(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    from_state: str | None,
    to_state: str,
    actor: str,
    at: datetime,
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO commons_job_transitions(
            transition_id, job_id, from_state, to_state, actor, reason,
            metadata_json, transitioned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"jtr_{uuid.uuid4().hex}",
            job_id,
            from_state,
            to_state,
            actor,
            reason,
            _canonical_json(metadata or {}),
            _timestamp(at),
        ),
    )


def _row_to_job(row: sqlite3.Row | tuple[Any, ...]) -> Job:
    return Job(
        job_id=str(row[0]),
        job_type=str(row[1]),
        energy_class=str(row[2]),
        state=str(row[3]),
        priority=int(row[4]),
        attempts=int(row[5]),
        max_attempts=int(row[6]),
        input_event_id=None if row[7] is None else str(row[7]),
        parameters=json.loads(row[8]),
        lease_owner=None if row[9] is None else str(row[9]),
        leased_until=None if row[10] is None else str(row[10]),
    )


def enqueue_job(
    conn: sqlite3.Connection,
    *,
    job_type: str,
    idempotency_key: str,
    parameters: Mapping[str, Any],
    energy_class: str | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    not_before: datetime | None = None,
    input_event_id: str | None = None,
    actor: str = "data_factory",
    now: datetime | None = None,
) -> EnqueueResult:
    """Create one deterministic allowlisted job or return the existing job."""
    if job_type not in JOB_ENERGY_CLASS:
        raise ValueError(f"job type is not allowlisted: {job_type}")
    expected_energy = JOB_ENERGY_CLASS[job_type]
    selected_energy = energy_class or expected_energy
    if selected_energy != expected_energy:
        raise ValueError(
            f"job type {job_type} requires energy class {expected_energy}, not {selected_energy}"
        )
    if selected_energy not in ENERGY_CLASSES:
        raise ValueError(f"unknown energy class: {selected_energy}")
    if not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    parameter_json = _canonical_json(parameters)
    created_at = _aware_utc(now or _utc_now())
    not_before_text = None if not_before is None else _timestamp(not_before)
    job_key = f"{job_type}|{idempotency_key}"
    job_id = _stable_id("job", job_key)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT job_id, state, energy_class, parameters_json, input_event_id,
                   max_attempts FROM commons_jobs WHERE job_key=?
            """,
            (job_key,),
        ).fetchone()
        if existing is not None:
            if (
                existing[2] != selected_energy
                or existing[3] != parameter_json
                or existing[4] != input_event_id
                or int(existing[5]) != max_attempts
            ):
                raise ValueError("idempotency key already exists with a different job contract")
            conn.commit()
            return EnqueueResult(str(existing[0]), False, str(existing[1]))
        conn.execute(
            """
            INSERT INTO commons_jobs(
                job_id, job_key, job_type, energy_class, state, priority,
                max_attempts, not_before, input_event_id, parameters_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_key,
                job_type,
                selected_energy,
                priority,
                max_attempts,
                not_before_text,
                input_event_id,
                parameter_json,
                _timestamp(created_at),
                _timestamp(created_at),
            ),
        )
        _transition(
            conn,
            job_id=job_id,
            from_state=None,
            to_state="queued",
            actor=actor,
            at=created_at,
            reason="enqueued",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return EnqueueResult(job_id, True, "queued")


def _recover_expired(conn: sqlite3.Connection, *, now: datetime, actor: str) -> None:
    now_text = _timestamp(now)
    rows = conn.execute(
        """
        SELECT job_id, attempts, max_attempts, lease_owner
        FROM commons_jobs
        WHERE state='running' AND leased_until IS NOT NULL AND leased_until <= ?
        ORDER BY leased_until, job_id
        """,
        (now_text,),
    ).fetchall()
    for job_id, attempts, max_attempts, lease_owner in rows:
        next_state = "failed" if int(attempts) >= int(max_attempts) else "queued"
        conn.execute(
            """
            UPDATE commons_jobs
            SET state=?, lease_owner=NULL, leased_until=NULL,
                completed_at=CASE WHEN ?='failed' THEN ? ELSE NULL END,
                error='worker lease expired', updated_at=?
            WHERE job_id=? AND state='running'
            """,
            (next_state, next_state, now_text, now_text, job_id),
        )
        _transition(
            conn,
            job_id=str(job_id),
            from_state="running",
            to_state=next_state,
            actor=actor,
            at=now,
            reason="worker lease expired",
            metadata={"expired_lease_owner": lease_owner},
        )


def claim_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    allowed_energy_classes: Set[str],
    now: datetime | None = None,
    lease_seconds: int = 300,
) -> Job | None:
    """Recover expired work and lease at most one eligible queued job."""
    if not worker_id.strip():
        raise ValueError("worker_id is required")
    if not allowed_energy_classes or not allowed_energy_classes.issubset(ENERGY_CLASSES):
        raise ValueError("allowed_energy_classes is empty or invalid")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    current = _aware_utc(now or _utc_now())
    current_text = _timestamp(current)
    leased_until = _timestamp(current + timedelta(seconds=lease_seconds))
    placeholders = ",".join("?" for _ in allowed_energy_classes)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        _recover_expired(conn, now=current, actor=worker_id)
        row = conn.execute(
            f"""
            SELECT job_id FROM commons_jobs
            WHERE state='queued'
              AND attempts < max_attempts
              AND energy_class IN ({placeholders})
              AND (not_before IS NULL OR not_before <= ?)
            ORDER BY priority DESC, created_at, job_id
            LIMIT 1
            """,
            (*sorted(allowed_energy_classes), current_text),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        job_id = str(row[0])
        cursor = conn.execute(
            """
            UPDATE commons_jobs
            SET state='running', attempts=attempts+1, lease_owner=?,
                leased_until=?, started_at=COALESCE(started_at, ?),
                completed_at=NULL, updated_at=?
            WHERE job_id=? AND state='queued'
            """,
            (worker_id, leased_until, current_text, current_text, job_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("job lease race was not serialized")
        _transition(
            conn,
            job_id=job_id,
            from_state="queued",
            to_state="running",
            actor=worker_id,
            at=current,
            reason="leased",
            metadata={"leased_until": leased_until},
        )
        claimed = conn.execute(
            """
            SELECT job_id, job_type, energy_class, state, priority, attempts,
                   max_attempts, input_event_id, parameters_json,
                   lease_owner, leased_until
            FROM commons_jobs WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _row_to_job(claimed)


def heartbeat_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = 300,
) -> str:
    """Extend an unexpired lease owned by the calling worker."""
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    current = _aware_utc(now or _utc_now())
    current_text = _timestamp(current)
    renewed_until = _timestamp(current + timedelta(seconds=lease_seconds))
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state, lease_owner, leased_until FROM commons_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown job_id: {job_id}")
        if row[0] != "running" or row[1] != worker_id:
            raise ValueError("only the current lease owner may heartbeat a running job")
        if row[2] is None or str(row[2]) <= current_text:
            raise ValueError("job lease has expired")
        conn.execute(
            """
            UPDATE commons_jobs SET leased_until=?, updated_at=?
            WHERE job_id=? AND state='running' AND lease_owner=?
            """,
            (renewed_until, current_text, job_id, worker_id),
        )
        _transition(
            conn,
            job_id=job_id,
            from_state="running",
            to_state="running",
            actor=worker_id,
            at=current,
            reason="heartbeat",
            metadata={"leased_until": renewed_until},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return renewed_until


def complete_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    worker_id: str,
    result: Mapping[str, Any],
    now: datetime | None = None,
    state: str = "success",
    reason: str | None = None,
) -> None:
    if state not in {"success", "skipped"}:
        raise ValueError("completion state must be success or skipped")
    result_json = _canonical_json(result)
    current = _aware_utc(now or _utc_now())
    current_text = _timestamp(current)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state, lease_owner, leased_until FROM commons_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown job_id: {job_id}")
        if row[0] != "running" or row[1] != worker_id:
            raise ValueError("only the current lease owner may complete a running job")
        if row[2] is None or str(row[2]) <= current_text:
            raise ValueError("job lease has expired")
        conn.execute(
            """
            UPDATE commons_jobs
            SET state=?, result_json=?, error=NULL, lease_owner=NULL,
                leased_until=NULL, completed_at=?, updated_at=?
            WHERE job_id=?
            """,
            (state, result_json, current_text, current_text, job_id),
        )
        _transition(
            conn,
            job_id=job_id,
            from_state="running",
            to_state=state,
            actor=worker_id,
            at=current,
            reason=reason or "completed",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def fail_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    worker_id: str,
    error: str,
    now: datetime | None = None,
) -> str:
    current = _aware_utc(now or _utc_now())
    current_text = _timestamp(current)
    safe_error = error[:2000]
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT state, lease_owner, attempts, max_attempts, leased_until
            FROM commons_jobs WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown job_id: {job_id}")
        if row[0] != "running" or row[1] != worker_id:
            raise ValueError("only the current lease owner may fail a running job")
        if row[4] is None or str(row[4]) <= current_text:
            raise ValueError("job lease has expired")
        next_state = "failed" if int(row[2]) >= int(row[3]) else "queued"
        retry_after = None
        if next_state == "queued":
            backoff_seconds = min(300, 30 * (2 ** max(0, int(row[2]) - 1)))
            retry_after = _timestamp(current + timedelta(seconds=backoff_seconds))
        conn.execute(
            """
            UPDATE commons_jobs
            SET state=?, error=?, lease_owner=NULL, leased_until=NULL,
                completed_at=CASE WHEN ?='failed' THEN ? ELSE NULL END,
                not_before=?, updated_at=?
            WHERE job_id=?
            """,
            (
                next_state,
                safe_error,
                next_state,
                current_text,
                retry_after,
                current_text,
                job_id,
            ),
        )
        _transition(
            conn,
            job_id=job_id,
            from_state="running",
            to_state=next_state,
            actor=worker_id,
            at=current,
            reason=safe_error,
            metadata={"retry_not_before": retry_after},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return next_state


def append_research_record(
    conn: sqlite3.Connection,
    *,
    record_type: str,
    title: str,
    body: str,
    recorded_at: datetime,
    sources: list[Mapping[str, Any]] | None = None,
    related_run_id: str | None = None,
    related_job_id: str | None = None,
    related_event_id: str | None = None,
    author: str = "Hermes",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "record_type": record_type,
        "title": title,
        "body": body,
        "recorded_at": _timestamp(recorded_at),
        "sources": sources or [],
        "related_run_id": related_run_id,
        "related_job_id": related_job_id,
        "related_event_id": related_event_id,
        "author": author,
        "metadata": metadata or {},
    }
    record_id = _stable_id("rec", _canonical_json(payload))
    conn.execute(
        """
        INSERT OR IGNORE INTO commons_research_records(
            record_id, recorded_at, record_type, title, body, sources_json,
            related_run_id, related_job_id, related_event_id, author,
            metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_id,
            payload["recorded_at"],
            record_type,
            title,
            body,
            _canonical_json({"sources": sources or []}),
            related_run_id,
            related_job_id,
            related_event_id,
            author,
            _canonical_json(metadata or {}),
        ),
    )
    conn.commit()
    return record_id
