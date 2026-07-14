"""Low-cost automation primitives for Pine Hollow Commons Lab."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class QualityResult:
    mean_luma: float
    bright_fraction: float
    dark_fraction: float
    green_chromatic_coordinate: float
    excess_green: float
    edge_energy: float
    quality_state: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


def metrics_from_rgb(rgb: bytes, *, width: int, height: int) -> QualityResult:
    """Compute explainable quality/phenology metrics from packed RGB bytes."""
    expected = width * height * 3
    if len(rgb) != expected:
        raise ValueError(f"expected {expected} RGB bytes, received {len(rgb)}")
    if width < 1 or height < 1:
        raise ValueError("sample dimensions must be positive")

    pixels: list[tuple[float, int, int, int]] = []
    gcc_values: list[float] = []
    excess_values: list[float] = []
    for offset in range(0, len(rgb), 3):
        red, green, blue = rgb[offset : offset + 3]
        luma = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
        pixels.append((luma, red, green, blue))
        channel_sum = red + green + blue
        if channel_sum > 15:
            gcc_values.append(green / channel_sum)
        excess_values.append((2 * green - red - blue) / 510.0)

    lumas = [pixel[0] for pixel in pixels]
    count = len(lumas)
    mean_luma = sum(lumas) / count
    bright_fraction = sum(value >= 0.95 for value in lumas) / count
    dark_fraction = sum(value <= 0.05 for value in lumas) / count
    gcc = sum(gcc_values) / len(gcc_values) if gcc_values else 0.0
    excess_green = sum(excess_values) / count

    edges: list[float] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if x + 1 < width:
                edges.append(abs(lumas[index] - lumas[index + 1]))
            if y + 1 < height:
                edges.append(abs(lumas[index] - lumas[index + width]))
    edge_energy = sum(edges) / len(edges) if edges else 0.0

    reasons: list[str] = []
    if bright_fraction > 0.55:
        reasons.append("high_clipping")
    if dark_fraction > 0.85:
        reasons.append("mostly_dark")
    if edge_energy < 0.01:
        reasons.append("low_detail")
    quality_state = "degraded" if reasons else "accepted"

    return QualityResult(
        mean_luma=mean_luma,
        bright_fraction=bright_fraction,
        dark_fraction=dark_fraction,
        green_chromatic_coordinate=gcc,
        excess_green=excess_green,
        edge_energy=edge_energy,
        quality_state=quality_state,
        reasons=tuple(reasons),
    )


def analyze_image(
    path: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    sample_width: int = 64,
    sample_height: int = 36,
) -> QualityResult:
    """Downsample one image through FFmpeg and compute CPU-only metrics."""
    image = Path(path).expanduser().resolve()
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(image),
        "-vf",
        f"scale={sample_width}:{sample_height}:flags=area",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    result = subprocess.run(command, check=True, capture_output=True, timeout=20)
    return metrics_from_rgb(
        result.stdout,
        width=sample_width,
        height=sample_height,
    )


def _measurement_id(event_id: str, phenomenon: str) -> str:
    key = f"{event_id}|{phenomenon}".encode("utf-8")
    return f"mea_{hashlib.sha256(key).hexdigest()[:24]}"


def record_quality_measurements(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    sensor_id: str,
    observed_at: str,
    quality: QualityResult,
) -> None:
    """Upsert transparent frame-quality measurements for one event."""
    real_values = {
        "image_mean_luma": quality.mean_luma,
        "image_bright_fraction": quality.bright_fraction,
        "image_dark_fraction": quality.dark_fraction,
        "green_chromatic_coordinate": quality.green_chromatic_coordinate,
        "excess_green": quality.excess_green,
        "image_edge_energy": quality.edge_energy,
    }
    metadata = json.dumps(
        {"method": "rgb_64x36_area_sample_v1", "reasons": list(quality.reasons)},
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute("PRAGMA foreign_keys = ON")
    for phenomenon, value in real_values.items():
        conn.execute(
            """
            INSERT INTO commons_measurements(
                measurement_id, event_id, sensor_id, phenomenon, value_real,
                unit, quality_flag, observed_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, 'fraction', ?, ?, ?)
            ON CONFLICT(measurement_id) DO UPDATE SET
                value_real=excluded.value_real,
                quality_flag=excluded.quality_flag,
                observed_at=excluded.observed_at,
                metadata_json=excluded.metadata_json
            """,
            (
                _measurement_id(event_id, phenomenon),
                event_id,
                sensor_id,
                phenomenon,
                value,
                quality.quality_state,
                observed_at,
                metadata,
            ),
        )
    conn.execute(
        """
        INSERT INTO commons_measurements(
            measurement_id, event_id, sensor_id, phenomenon, value_text,
            quality_flag, observed_at, metadata_json
        ) VALUES (?, ?, ?, 'capture_quality_state', ?, ?, ?, ?)
        ON CONFLICT(measurement_id) DO UPDATE SET
            value_text=excluded.value_text,
            quality_flag=excluded.quality_flag,
            observed_at=excluded.observed_at,
            metadata_json=excluded.metadata_json
        """,
        (
            _measurement_id(event_id, "capture_quality_state"),
            event_id,
            sensor_id,
            quality.quality_state,
            quality.quality_state,
            observed_at,
            metadata,
        ),
    )
    conn.commit()


def start_run(
    conn: sqlite3.Connection,
    *,
    pipeline: str,
    started_at: str,
    trigger_type: str = "manual",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    run_id = f"run_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO commons_runs(
            run_id, pipeline, trigger_type, started_at, status, metadata_json
        ) VALUES (?, ?, ?, ?, 'running', ?)
        """,
        (
            run_id,
            pipeline,
            trigger_type,
            started_at,
            json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
        ),
    )
    conn.commit()
    return run_id


def finish_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    completed_at: str,
    event_id: str | None = None,
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    values: list[Any] = [status, completed_at, event_id, error]
    metadata_clause = ""
    if metadata is not None:
        metadata_clause = ", metadata_json=?"
        values.append(json.dumps(metadata, sort_keys=True, separators=(",", ":")))
    values.append(run_id)
    cursor = conn.execute(
        f"""
        UPDATE commons_runs
        SET status=?, completed_at=?, event_id=?, error=?{metadata_clause}
        WHERE run_id=?
        """,
        values,
    )
    if cursor.rowcount != 1:
        conn.rollback()
        raise ValueError(f"unknown run_id: {run_id}")
    conn.commit()
