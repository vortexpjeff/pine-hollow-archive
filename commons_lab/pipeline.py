"""One-shot Commons Lab capture pipeline for the fixed Pine Hollow camera."""

from __future__ import annotations

import fcntl
import json
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .automation import (
    QualityResult,
    analyze_image,
    finish_run,
    record_quality_measurements,
    start_run,
)
from .camera import DEFAULT_DEVICE, capture_frame
from .ingest import ingest_media, register_deployment, register_sensor, register_site
from .schema import migrate

ROOT = Path(__file__).resolve().parents[1]
SITE_ID = "pine-hollow-private"
SENSOR_ID = "emeet-window-camera"
DEPLOYMENT_ID = "window-view-v1"
TIMEZONE = "America/New_York"
PIPELINE_NAME = "window_camera_capture"
DEFAULT_DATA_ROOT = ROOT / "private" / "commons_lab"
DEFAULT_MIN_FREE_BYTES = 20 * 1024**3
DEFAULT_LOCK_PATH = Path.home() / ".cache" / "pine-hollow-commons" / "window-camera.lock"


@dataclass(frozen=True)
class CaptureOutcome:
    run_id: str | None
    status: str
    event_id: str | None
    media_id: str | None
    path: str | None
    quality: QualityResult | None
    reason: str | None = None


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path), timeout=15)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def register_window_camera(conn: sqlite3.Connection) -> None:
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
        name="Window Camera",
        sensor_type="rgb_camera",
        manufacturer="EMEET",
        model="SmartCam Nova 4K",
        host="Athena-Windows",
        privacy_default="private",
        metadata={"transport": "Windows DirectShow", "wsl_video_device": False},
    )
    register_deployment(
        conn,
        deployment_id=DEPLOYMENT_ID,
        sensor_id=SENSOR_ID,
        site_id=SITE_ID,
        purpose="Fixed window environmental and phenology observation",
        orientation={
            "raw_orientation": "upside_down",
            "rotation_applied_deg": 180,
            "normalized_orientation": True,
        },
        configuration={
            "capture_mode": "scheduled_still",
            "cadence_minutes": 30,
            "active_hours_local": "06:00-21:30",
            "raw_frame_retained": False,
            "public_raw_media": False,
            "quality_method": "rgb_64x36_area_sample_v1",
        },
        privacy_default="private",
    )


def image_dimensions(path: str | Path) -> tuple[int | None, int | None]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(Path(path).resolve()),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        return None, None
    return streams[0].get("width"), streams[0].get("height")


def _capture_window_frame_locked(
    *,
    db_path: str | Path = ROOT / "archive.db",
    data_root: str | Path = DEFAULT_DATA_ROOT,
    trigger_type: str = "manual",
    device: str = DEFAULT_DEVICE,
    output_path: str | Path | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
) -> CaptureOutcome:
    """Run one bounded capture, ingest, measurement, and ledger transaction chain."""
    started = datetime.now(ZoneInfo(TIMEZONE))
    data = Path(data_root).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = connect(db_path)
    migrate(conn)
    register_window_camera(conn)
    free_bytes = shutil.disk_usage(data).free
    run_id = start_run(
        conn,
        pipeline=PIPELINE_NAME,
        started_at=started.isoformat(),
        trigger_type=trigger_type,
        metadata={
            "device": device,
            "data_root": str(data),
            "min_free_bytes": min_free_bytes,
            "free_bytes_at_start": free_bytes,
        },
    )

    if free_bytes < min_free_bytes:
        completed = datetime.now(ZoneInfo(TIMEZONE))
        reason = "minimum free-space guard"
        finish_run(
            conn,
            run_id=run_id,
            status="skipped",
            completed_at=completed.isoformat(),
            error=reason,
        )
        conn.close()
        return CaptureOutcome(run_id, "skipped", None, None, None, None, reason)

    output = Path(output_path).expanduser().resolve() if output_path else (
        data
        / "window_camera"
        / started.strftime("%Y")
        / started.strftime("%m")
        / started.strftime("%d")
        / f"window_{started.strftime('%Y%m%dT%H%M%S%f%z')}_{uuid.uuid4().hex[:8]}.jpg"
    )
    event_id: str | None = None
    try:
        captured = capture_frame(output, device=device, rotate_180=True)
        width, height = image_dimensions(captured)
        result = ingest_media(
            conn,
            path=captured,
            event_type="fixed_camera_frame",
            source="window_camera",
            site_id=SITE_ID,
            deployment_id=DEPLOYMENT_ID,
            captured_at=started.isoformat(),
            timezone=TIMEZONE,
            media_type="image",
            mime_type="image/jpeg",
            privacy_level="private",
            transform={
                "rotation_deg": 180,
                "normalized_orientation": True,
                "raw_frame_retained": False,
            },
            event_metadata={
                "capture_policy": "private_by_default",
                "trigger_type": trigger_type,
            },
            media_metadata={
                "device": device,
                "capture_bridge": "windows_dshow",
                "atomic_promotion": True,
            },
            width=width,
            height=height,
        )
        event_id = result.event_id
        quality = analyze_image(captured)
        record_quality_measurements(
            conn,
            event_id=result.event_id,
            sensor_id=SENSOR_ID,
            observed_at=started.isoformat(),
            quality=quality,
        )
        completed = datetime.now(ZoneInfo(TIMEZONE))
        finish_run(
            conn,
            run_id=run_id,
            status="success",
            completed_at=completed.isoformat(),
            event_id=result.event_id,
            metadata={
                "device": device,
                "data_root": str(data),
                "min_free_bytes": min_free_bytes,
                "free_bytes_at_start": free_bytes,
                "path": str(captured),
                "media_id": result.media_id,
                "quality": asdict(quality),
                "width": width,
                "height": height,
            },
        )
        conn.close()
        return CaptureOutcome(
            run_id,
            "success",
            result.event_id,
            result.media_id,
            str(captured),
            quality,
        )
    except Exception as exc:
        completed = datetime.now(ZoneInfo(TIMEZONE))
        error = f"{type(exc).__name__}: {exc}"[:1000]
        try:
            finish_run(
                conn,
                run_id=run_id,
                status="failed",
                completed_at=completed.isoformat(),
                event_id=event_id,
                error=error,
                metadata={
                    "device": device,
                    "data_root": str(data),
                    "path": str(output) if output.exists() else None,
                    "file_retained": output.exists(),
                },
            )
        finally:
            conn.close()
        raise


def capture_window_frame(
    *,
    db_path: str | Path = ROOT / "archive.db",
    data_root: str | Path = DEFAULT_DATA_ROOT,
    trigger_type: str = "manual",
    device: str = DEFAULT_DEVICE,
    output_path: str | Path | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> CaptureOutcome:
    """Run one capture while enforcing a shared lock for every entry point."""
    lock = Path(lock_path).expanduser().resolve()
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = lock.open("a+")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return CaptureOutcome(
                None,
                "skipped",
                None,
                None,
                None,
                None,
                "capture already running",
            )
        return _capture_window_frame_locked(
            db_path=db_path,
            data_root=data_root,
            trigger_type=trigger_type,
            device=device,
            output_path=output_path,
            min_free_bytes=min_free_bytes,
        )
    finally:
        handle.close()
