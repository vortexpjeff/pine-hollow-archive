#!/usr/bin/env python3
"""Operate the local Pine Hollow Commons Lab foundation."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.camera import DEFAULT_DEVICE
from commons_lab.pipeline import (
    DEFAULT_DATA_ROOT,
    capture_window_frame,
    connect,
    register_window_camera,
)
from commons_lab.schema import SCHEMA_VERSION, migrate


def command_init(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    migrate(conn)
    conn.close()
    print(json.dumps({"database": str(args.db), "schema_version": SCHEMA_VERSION}))


def command_register_camera(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    migrate(conn)
    register_window_camera(conn)
    conn.close()
    print(
        json.dumps(
            {
                "sensor_id": "emeet-window-camera",
                "deployment_id": "window-view-v1",
                "privacy": "private",
                "rotation_deg": 180,
            }
        )
    )


def command_capture(args: argparse.Namespace) -> None:
    outcome = capture_window_frame(
        db_path=args.db,
        data_root=args.data_root,
        trigger_type=args.trigger,
        device=args.device,
        output_path=args.output,
        min_free_bytes=args.min_free_gib * 1024**3,
    )
    print(json.dumps(asdict(outcome), indent=2, sort_keys=True, default=list))


def command_status(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    migrate(conn)
    tables = [
        "commons_sites",
        "commons_sensors",
        "commons_deployments",
        "commons_events",
        "commons_media",
        "commons_measurements",
        "commons_assertions",
        "commons_interventions",
        "commons_outcomes",
        "commons_publications",
        "commons_runs",
    ]
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    latest_event = conn.execute(
        """
        SELECT event_id, event_type, started_at, privacy_level,
               review_state, publication_state
        FROM commons_events ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    latest_run = conn.execute(
        """
        SELECT run_id, pipeline, trigger_type, started_at, completed_at,
               status, event_id, error
        FROM commons_runs ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    quality: dict[str, float | str | None] = {}
    if latest_event:
        for phenomenon, value_real, value_text in conn.execute(
            """
            SELECT phenomenon, value_real, value_text
            FROM commons_measurements WHERE event_id=?
            ORDER BY phenomenon
            """,
            (latest_event[0],),
        ):
            quality[phenomenon] = value_real if value_real is not None else value_text
    conn.close()
    args.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    disk = shutil.disk_usage(args.data_root)
    print(
        json.dumps(
            {
                "database": str(args.db),
                "data_root": str(args.data_root),
                "schema_version": SCHEMA_VERSION,
                "counts": counts,
                "latest_event": latest_event,
                "latest_run": latest_run,
                "latest_quality": quality,
                "disk_free_bytes": disk.free,
            },
            indent=2,
        )
    )


def command_run_history(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    migrate(conn)
    rows = conn.execute(
        """
        SELECT run_id, trigger_type, started_at, completed_at, status,
               event_id, error
        FROM commons_runs
        WHERE pipeline='window_camera_capture'
        ORDER BY started_at DESC LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    conn.close()
    print(json.dumps(rows, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db", type=Path, default=ROOT / "archive.db")
    root.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Apply the additive Commons Lab schema")
    init.set_defaults(func=command_init)

    register = sub.add_parser("register-camera", help="Register the private window camera")
    register.set_defaults(func=command_register_camera)

    capture = sub.add_parser(
        "capture-camera", help="Run one complete private capture pipeline"
    )
    capture.add_argument("--device", default=DEFAULT_DEVICE)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--trigger", default="manual")
    capture.add_argument("--min-free-gib", type=int, default=20)
    capture.set_defaults(func=command_capture)

    status = sub.add_parser("status", help="Report ledger, quality, and disk state")
    status.set_defaults(func=command_status)

    history = sub.add_parser("run-history", help="Show recent automation runs")
    history.add_argument("--limit", type=int, default=10)
    history.set_defaults(func=command_run_history)
    return root


def main() -> None:
    args = parser().parse_args()
    args.db = args.db.expanduser().resolve()
    args.data_root = args.data_root.expanduser().resolve()
    args.func(args)


if __name__ == "__main__":
    main()
