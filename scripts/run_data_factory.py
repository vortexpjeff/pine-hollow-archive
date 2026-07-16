#!/usr/bin/env python3
"""Operate Pine Hollow's local physical-ecology data factory."""

from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import socket
import sqlite3
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.acoustic import (
    import_field_evidence,
    load_bundle_catalog,
    populate_calibration_queue,
    record_human_acoustic_review,
)
from commons_lab.automation import finish_run, start_run
from commons_lab.factory import FactoryConfig, enqueue_cycle, run_jobs
from commons_lab.jobs import append_research_record, enqueue_job
from commons_lab.schema import SCHEMA_VERSION, migrate
from commons_lab.validation import (
    PROTOCOL_VERSION,
    generate_weekly_packet,
    promote_validation_sentinel,
    record_validation_review,
    validation_report,
    validation_sampling_readiness,
    verify_validation_sentinels,
)

DEFAULT_DB = ROOT / "archive.db"
DEFAULT_DATA_ROOT = ROOT / "private" / "commons_lab"
DEFAULT_FIELD_DB = Path.home() / ".local/share/insectnet-field/events.sqlite3"
DEFAULT_REVIEW_DIR = Path.home() / ".local/share/insectnet-field/review"
DEFAULT_BUNDLES = (
    Path.home() / ".local/share/insectnet-field/bundles/insectnet-dev2-field-probe",
    Path.home() / ".local/share/insectnet-field/bundles/chickennet-dev2-field-probe",
)
DEFAULT_OBSERVATORY = Path.home() / "vortex-site/data/observatory.json"
DEFAULT_LOCK = Path.home() / ".cache/pine-hollow-commons/data-factory.lock"
DEFAULT_MIN_FREE_GIB = 20


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def make_config(args: argparse.Namespace) -> FactoryConfig:
    return FactoryConfig(
        field_db_path=args.field_db.expanduser().absolute(),
        review_dir=args.review_dir.expanduser().absolute(),
        bundle_dirs=tuple(path.expanduser().absolute() for path in args.bundle),
        observatory_path=args.observatory.expanduser().absolute(),
        data_root=args.data_root.expanduser().absolute(),
        camera_tolerance_seconds=args.camera_tolerance_seconds,
        observatory_tolerance_seconds=args.observatory_tolerance_seconds,
        nvidia_smi=args.nvidia_smi,
    )


def emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def command_dry_run(args: argparse.Namespace) -> None:
    config = make_config(args)
    scratch = sqlite3.connect(":memory:")
    migrate(scratch)
    bundles = load_bundle_catalog(config.bundle_dirs)
    field = import_field_evidence(
        scratch,
        field_db_path=config.field_db_path,
        review_dir=config.review_dir,
        bundle_dirs=config.bundle_dirs,
        limit=args.limit,
        dry_run=True,
    )
    observatory = json.loads(config.observatory_path.read_text(encoding="utf-8"))
    scratch.close()
    emit(
        {
            "mode": "dry_run",
            "field": asdict(field),
            "bundles": {
                bundle_id: {
                    "model_slug": bundle.model_slug,
                    "class_name": bundle.class_name,
                    "threshold": bundle.threshold,
                    "sample_rate": bundle.sample_rate,
                    "score_semantics": bundle.score_semantics,
                }
                for bundle_id, bundle in bundles.items()
            },
            "observatory_updated": observatory.get("updated"),
            "writes": False,
        }
    )


def _acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.write(f"pid={__import__('os').getpid()} host={socket.gethostname()}\n")
    handle.flush()
    return handle


def command_cycle(args: argparse.Namespace) -> None:
    lock = _acquire_lock(args.lock.expanduser().resolve())
    if lock is None:
        emit({"status": "skipped", "reason": "data factory cycle already running"})
        return
    config = make_config(args)
    config.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    free_bytes = shutil.disk_usage(config.data_root).free
    if free_bytes < args.min_free_gib * 1024**3:
        emit(
            {
                "status": "skipped",
                "reason": "minimum free-space guard",
                "free_bytes": free_bytes,
            }
        )
        lock.close()
        return
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    now = datetime.now(timezone.utc)
    run_id = start_run(
        conn,
        pipeline="physical_ecology_data_factory",
        started_at=now.isoformat(),
        trigger_type=args.trigger,
        metadata={
            "schema_version": SCHEMA_VERSION,
            "worker": args.worker,
            "energy_classes": ["scheduled_cpu"],
            "max_jobs": args.max_jobs,
            "free_bytes_at_start": free_bytes,
        },
    )
    try:
        enqueued = enqueue_cycle(conn, config=config, now=now)
        outcomes = run_jobs(
            conn,
            config=config,
            worker_id=args.worker,
            allowed_energy_classes={"scheduled_cpu"},
            max_jobs=args.max_jobs,
        )
        bad = [item for item in outcomes if item.state != "success"]
        status = "failed" if bad else "success"
        completed = datetime.now(timezone.utc)
        result = {
            "enqueued": asdict(enqueued),
            "outcomes": [asdict(item) for item in outcomes],
            "free_bytes_at_start": free_bytes,
            "gpu_jobs_automated": False,
        }
        finish_run(
            conn,
            run_id=run_id,
            status=status,
            completed_at=completed.isoformat(),
            error=None if not bad else f"{len(bad)} job(s) did not succeed",
            metadata=result,
        )
        emit({"run_id": run_id, "status": status, **result})
        if bad:
            raise SystemExit(1)
    except BaseException as exc:
        if not isinstance(exc, SystemExit):
            finish_run(
                conn,
                run_id=run_id,
                status="failed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=f"{type(exc).__name__}: {exc}"[:1000],
            )
        raise
    finally:
        conn.close()
        lock.close()


def command_status(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    tables = (
        "commons_events",
        "commons_media",
        "commons_acoustic_windows",
        "commons_assertions",
        "commons_event_links",
        "commons_review_queue",
        "commons_jobs",
        "commons_job_transitions",
        "commons_research_records",
        "commons_runs",
        "commons_validation_packets",
        "commons_validation_items",
        "commons_validation_reviews",
        "commons_validation_sentinels",
        "commons_validation_sentinel_checks",
    )
    counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
    job_states = dict(
        conn.execute("SELECT state, COUNT(*) FROM commons_jobs GROUP BY state").fetchall()
    )
    latest_run = conn.execute(
        """
        SELECT run_id, started_at, completed_at, status, error
        FROM commons_runs WHERE pipeline='physical_ecology_data_factory'
        ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    emit(
        {
            "schema_version": SCHEMA_VERSION,
            "counts": counts,
            "job_states": job_states,
            "latest_factory_run": latest_run,
        }
    )


def command_gpu_probe(args: argparse.Namespace) -> None:
    config = make_config(args)
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    now = datetime.now(timezone.utc)
    key = args.key or now.replace(second=0, microsecond=0).isoformat()
    job = enqueue_job(
        conn,
        job_type="gpu_environment_probe",
        idempotency_key=f"gpu-probe:{key}",
        parameters={"requested_by": args.worker},
        now=now,
    )
    outcomes = run_jobs(
        conn,
        config=config,
        worker_id=args.worker,
        allowed_energy_classes={"deferrable_gpu"},
        max_jobs=1,
    )
    conn.close()
    emit({"job": asdict(job), "outcomes": [asdict(item) for item in outcomes]})


def command_queue_calibration(args: argparse.Namespace) -> None:
    config = make_config(args)
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    catalog = load_bundle_catalog(config.bundle_dirs)
    inserted: dict[str, int] = {}
    for bundle_id, bundle in catalog.items():
        inserted[bundle.model_slug] = populate_calibration_queue(
            conn,
            bundle_id=bundle_id,
            class_name=bundle.class_name,
            per_band=args.per_band,
        )
    conn.close()
    emit({"inserted": inserted, "per_band": args.per_band})


def command_record_review(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    assertion_id = record_human_acoustic_review(
        conn,
        event_id=args.event_id,
        media_id=args.media_id,
        bundle_id=args.bundle_id,
        class_name=args.class_name,
        present=args.present,
        certainty=args.certainty,
        reviewer=args.reviewer,
        start_sample=args.start_sample,
        end_sample=args.end_sample,
        reviewed_at=args.reviewed_at or datetime.now(timezone.utc).isoformat(),
        supersedes_assertion_id=args.supersedes,
        notes=args.notes,
    )
    conn.close()
    emit({"assertion_id": assertion_id, "append_only": True})


def command_validation_packet(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    selected_week = None if args.week_start is None else date.fromisoformat(args.week_start)
    result = generate_weekly_packet(conn, week_start=selected_week)
    conn.close()
    emit(asdict(result))


def command_validation_status(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    packets = [
        {
            "packet_id": str(row[0]),
            "week_start": str(row[1]),
            "state": str(row[2]),
            "completed": int(row[3]),
            "total": int(row[4]),
            "manifest_sha256": str(row[5]),
            "protocol_version": str(row[6]),
            "active": str(row[6]) == PROTOCOL_VERSION,
        }
        for row in conn.execute(
            """
            SELECT p.packet_id,p.week_start,p.state,
                   SUM(CASE WHEN i.state='completed' THEN 1 ELSE 0 END),
                   COUNT(i.item_id),p.manifest_sha256,p.protocol_version
            FROM commons_validation_packets AS p
            LEFT JOIN commons_validation_items AS i ON i.packet_id=p.packet_id
            GROUP BY p.packet_id ORDER BY p.week_start DESC,p.created_at DESC
            """
        )
    ]
    sentinels = {
        "active": int(
            conn.execute(
                "SELECT COUNT(*) FROM commons_validation_sentinels WHERE active=1"
            ).fetchone()[0]
        ),
        "latest_checks": [
            {
                "sentinel_id": str(row[0]),
                "checked_at": str(row[1]),
                "status": str(row[2]),
                "error": None if row[3] is None else str(row[3]),
            }
            for row in conn.execute(
                """
                SELECT c.sentinel_id,c.checked_at,c.status,c.error
                FROM commons_validation_sentinel_checks AS c
                JOIN (
                    SELECT sentinel_id,MAX(checked_at) AS latest
                    FROM commons_validation_sentinel_checks GROUP BY sentinel_id
                ) AS latest
                  ON latest.sentinel_id=c.sentinel_id AND latest.latest=c.checked_at
                ORDER BY c.sentinel_id
                """
            )
        ],
    }
    readiness = validation_sampling_readiness(conn)
    conn.close()
    active_packet_id = next(
        (packet["packet_id"] for packet in packets if packet["active"]), None
    )
    emit(
        {
            "readiness": readiness,
            "active_packet_id": active_packet_id,
            "packets": packets,
            "sentinels": sentinels,
        }
    )


def command_validation_report(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    report = validation_report(conn, packet_id=args.packet_id)
    conn.close()
    emit(report)


def command_validation_review(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    result = record_validation_review(
        conn,
        item_id=args.item_id,
        reviewer=args.reviewer,
        insect_presence=args.insect_presence,
        chicken_presence=args.chicken_presence,
        signal_quality=args.signal_quality,
        confounders=args.confounder,
        notes=args.notes,
        review_seconds=args.review_seconds,
        reviewed_at=args.reviewed_at or datetime.now(timezone.utc).isoformat(),
    )
    conn.close()
    emit(asdict(result))


def command_validation_promote_sentinel(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    sentinel_id = promote_validation_sentinel(
        conn,
        item_id=args.item_id,
        promoted_by=args.promoted_by,
        promoted_at=args.promoted_at or datetime.now(timezone.utc).isoformat(),
    )
    conn.close()
    emit({"sentinel_id": sentinel_id, "fresh_audio_rescore": False})


def command_validation_check_sentinels(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    result = verify_validation_sentinels(conn)
    conn.close()
    emit(result)


def command_research_log(args: argparse.Namespace) -> None:
    conn = connect(args.db.expanduser().resolve())
    migrate(conn)
    record_id = append_research_record(
        conn,
        record_type=args.record_type,
        title=args.title,
        body=args.body,
        recorded_at=datetime.now(timezone.utc),
        sources=[{"uri": value} for value in args.source],
        author=args.author,
    )
    conn.close()
    emit({"record_id": record_id, "append_only": True})


def add_common(root: argparse.ArgumentParser) -> None:
    root.add_argument("--db", type=Path, default=DEFAULT_DB)
    root.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    root.add_argument("--field-db", type=Path, default=DEFAULT_FIELD_DB)
    root.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    root.add_argument("--bundle", action="append", type=Path, default=None)
    root.add_argument("--observatory", type=Path, default=DEFAULT_OBSERVATORY)
    root.add_argument("--camera-tolerance-seconds", type=float, default=1200)
    root.add_argument("--observatory-tolerance-seconds", type=float, default=1800)
    root.add_argument("--nvidia-smi", default="nvidia-smi")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    add_common(root)
    sub = root.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run", help="Validate all sources without persistent writes")
    dry.add_argument("--limit", type=int)
    dry.set_defaults(func=command_dry_run)

    cycle = sub.add_parser("cycle", help="Enqueue and run one bounded scheduled-CPU cycle")
    cycle.add_argument("--trigger", choices=("manual", "systemd_timer", "retry", "test"), default="manual")
    cycle.add_argument("--worker", default=f"cpu:{socket.gethostname()}")
    cycle.add_argument("--max-jobs", type=int, default=8)
    cycle.add_argument("--min-free-gib", type=int, default=DEFAULT_MIN_FREE_GIB)
    cycle.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    cycle.set_defaults(func=command_cycle)

    status = sub.add_parser("status", help="Report factory counts, jobs, and latest run")
    status.set_defaults(func=command_status)

    gpu = sub.add_parser("gpu-probe", help="Explicitly enqueue and run one deferrable GPU inventory probe")
    gpu.add_argument("--key")
    gpu.add_argument("--worker", default=f"gpu:{socket.gethostname()}")
    gpu.set_defaults(func=command_gpu_probe)

    queue = sub.add_parser("queue-calibration", help="Populate deterministic score-band review queues")
    queue.add_argument("--per-band", type=int, default=10)
    queue.set_defaults(func=command_queue_calibration)

    review = sub.add_parser("record-review", help="Append a span-bounded human acoustic assertion")
    review.add_argument("--event-id", required=True)
    review.add_argument("--media-id", required=True)
    review.add_argument("--bundle-id", required=True)
    review.add_argument("--class-name", required=True)
    review.add_argument("--present", action=argparse.BooleanOptionalAction, required=True)
    review.add_argument("--certainty", choices=("confirmed", "probable", "uncertain"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--start-sample", type=int, required=True)
    review.add_argument("--end-sample", type=int, required=True)
    review.add_argument("--reviewed-at")
    review.add_argument("--supersedes")
    review.add_argument("--notes")
    review.set_defaults(func=command_record_review)

    validation_packet = sub.add_parser(
        "validation-packet",
        help="Create or replay one deterministic weekly blinded packet",
    )
    validation_packet.add_argument("--week-start", help="Local Monday as YYYY-MM-DD")
    validation_packet.set_defaults(func=command_validation_packet)

    validation_status = sub.add_parser(
        "validation-status", help="Report packet progress, readiness, and sentinels"
    )
    validation_status.set_defaults(func=command_validation_status)

    validation_report_parser = sub.add_parser(
        "validation-report", help="Emit packet or cumulative scientific metrics"
    )
    validation_report_parser.add_argument("--packet-id")
    validation_report_parser.set_defaults(func=command_validation_report)

    validation_review = sub.add_parser(
        "validation-review", help="Append one two-label validation judgment"
    )
    validation_review.add_argument("--item-id", required=True)
    validation_review.add_argument("--reviewer", required=True)
    validation_review.add_argument(
        "--insect-presence", choices=("present", "absent", "uncertain"), required=True
    )
    validation_review.add_argument(
        "--chicken-presence", choices=("present", "absent", "uncertain"), required=True
    )
    validation_review.add_argument(
        "--signal-quality",
        choices=("clear", "distant", "overlapping", "clipped", "noisy", "inaudible"),
        required=True,
    )
    validation_review.add_argument("--confounder", action="append", default=[])
    validation_review.add_argument("--notes")
    validation_review.add_argument("--review-seconds", type=float)
    validation_review.add_argument("--reviewed-at")
    validation_review.set_defaults(func=command_validation_review)

    validation_promote = sub.add_parser(
        "validation-promote-sentinel",
        help="Promote one decided reviewed item into the artifact sentinel set",
    )
    validation_promote.add_argument("--item-id", required=True)
    validation_promote.add_argument("--promoted-by", required=True)
    validation_promote.add_argument("--promoted-at")
    validation_promote.set_defaults(func=command_validation_promote_sentinel)

    validation_check = sub.add_parser(
        "validation-check-sentinels",
        help="Append byte/span/model-context checks for active sentinels",
    )
    validation_check.set_defaults(func=command_validation_check_sentinels)

    research = sub.add_parser("research-log", help="Append a research/development record")
    research.add_argument("--record-type", choices=("research", "decision", "development", "experiment", "validation", "incident", "operation"), required=True)
    research.add_argument("--title", required=True)
    research.add_argument("--body", required=True)
    research.add_argument("--source", action="append", default=[])
    research.add_argument("--author", default="Hermes")
    research.set_defaults(func=command_research_log)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.bundle is None:
        args.bundle = list(DEFAULT_BUNDLES)
    args.func(args)


if __name__ == "__main__":
    main()
