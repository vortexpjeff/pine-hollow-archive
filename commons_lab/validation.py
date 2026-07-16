"""Blinded weekly field-validation packets and review science helpers."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sqlite3
import wave
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .acoustic import record_human_acoustic_review
from .safe_paths import resolve_no_symlinks

PROTOCOL_VERSION = "weekly_blinded_v4"
LOCAL_TIMEZONE = "America/New_York"
TARGET_COUNT = 24
UNIQUE_COUNT = 22
MODEL_CLASSES = (
    "insect_present",
    "chicken_vocalization_present",
)


@dataclass(frozen=True)
class PacketResult:
    packet_id: str | None
    created: bool
    item_count: int
    reason: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    review_id: str
    item_id: str
    packet_id: str
    assertion_ids: tuple[str, str]


@dataclass(frozen=True)
class _Candidate:
    event_id: str
    media_id: str
    source_recording_id: str
    media_path: str
    media_sha256: str
    started_at: str
    start_sample: int
    end_sample: int
    sample_rate: int
    model_context: Mapping[str, Mapping[str, Any]]

    @property
    def diversity_group(self) -> tuple[str, int]:
        observed = _aware_datetime(self.started_at)
        local = observed.astimezone(ZoneInfo(LOCAL_TIMEZONE))
        return local.date().isoformat(), local.hour // 6


@dataclass(frozen=True)
class _Selected:
    candidate: _Candidate
    lane: str
    primary_class_name: str | None
    primary_bundle_id: str | None
    selection: str
    boundary_side: str | None = None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _stable_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _aware_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("validation timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def local_week_start(now: datetime, timezone_name: str = LOCAL_TIMEZONE) -> date:
    aware = _aware_datetime(now)
    local_day = aware.astimezone(ZoneInfo(timezone_name)).date()
    return local_day - timedelta(days=local_day.weekday())


def _sampling_frame(conn: sqlite3.Connection) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT e.event_id,m.media_id,m.path,m.sha256,e.started_at,
               w.source_recording_id,w.start_sample,w.end_sample,w.sample_rate,w.bundle_id,
               w.model_slug,w.class_name,w.score,w.raw_score,w.threshold,
               w.crosses_threshold,w.score_semantics,w.preprocess_recipe_id
        FROM commons_events AS e
        JOIN commons_media AS m ON m.event_id=e.event_id
        JOIN commons_acoustic_windows AS w
          ON w.event_id=e.event_id AND w.media_id=m.media_id
        WHERE e.event_type='acoustic_recording'
          AND w.class_name IN ('insect_present','chicken_vocalization_present')
        ORDER BY e.event_id,w.start_sample,w.class_name,w.bundle_id
        """
    ).fetchall()
    grouped: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    for row in rows:
        key = (str(row[5]), int(row[6]), int(row[7]), int(row[8]))
        entry = grouped.setdefault(
            key,
            {
                "event_id": str(row[0]),
                "media_id": str(row[1]),
                "source_recording_id": str(row[5]),
                "media_path": str(row[2]),
                "media_sha256": str(row[3]),
                "started_at": str(row[4]),
                "start_sample": int(row[6]),
                "end_sample": int(row[7]),
                "sample_rate": int(row[8]),
                "model_context": {},
            },
        )
        if str(entry["media_sha256"]) != str(row[3]):
            raise ValueError(
                f"source recording {row[5]} has conflicting retained media hashes"
            )
        if str(row[0]) < str(entry["event_id"]):
            entry.update(
                event_id=str(row[0]),
                media_id=str(row[1]),
                media_path=str(row[2]),
                started_at=str(row[4]),
            )
        context = entry["model_context"]
        class_name = str(row[11])
        candidate_context = {
            "bundle_id": str(row[9]),
            "model_slug": str(row[10]),
            "class_name": class_name,
            "score": float(row[12]),
            "raw_score": float(row[13]),
            "threshold": float(row[14]),
            "crosses_threshold": bool(row[15]),
            "score_semantics": str(row[16]),
            "preprocess_recipe_id": str(row[17]),
        }
        if class_name in context:
            if context[class_name] != candidate_context:
                raise ValueError(
                    f"source recording {row[5]} has conflicting {class_name} model context"
                )
            continue
        context[class_name] = candidate_context
    candidates: list[_Candidate] = []
    for entry in grouped.values():
        if set(entry["model_context"]) != set(MODEL_CLASSES):
            continue
        candidates.append(_Candidate(**entry))
    return candidates


def _history_recordings(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT source_recording_id FROM commons_validation_items
            WHERE lane!='blind_repeat'
            """
        )
    }


def validation_sampling_readiness(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    timezone_name: str = LOCAL_TIMEZONE,
) -> dict[str, Any]:
    """Run the active packet planner without writing and report its feasibility."""
    frame = _sampling_frame(conn)
    unique_recordings = {candidate.source_recording_id for candidate in frame}
    class_counts: dict[str, dict[str, int]] = {}
    marginal_ready = len(unique_recordings) >= UNIQUE_COUNT
    for class_name in MODEL_CLASSES:
        above = {
            candidate.source_recording_id
            for candidate in frame
            if _score(candidate, class_name) >= _threshold(candidate, class_name)
        }
        below = {
            candidate.source_recording_id
            for candidate in frame
            if _score(candidate, class_name) < _threshold(candidate, class_name)
        }
        class_counts[class_name] = {
            "above_events": len(above),
            "below_events": len(below),
        }
        marginal_ready = marginal_ready and len(above) >= 6 and len(below) >= 2
    current = _aware_datetime(now or datetime.now(timezone.utc))
    week_text = local_week_start(current, timezone_name).isoformat()
    seed = hashlib.sha256(
        f"{PROTOCOL_VERSION}|{timezone_name}|{week_text}".encode("utf-8")
    ).hexdigest()
    if marginal_ready:
        _, reason = _plan_selection(
            frame, seed=seed, used_history=_history_recordings(conn)
        )
    else:
        reason = "sampling-frame marginal counts are insufficient"
    return {
        "ready": reason is None,
        "reason": reason,
        "protocol_version": PROTOCOL_VERSION,
        "unique_parent_recordings": len(unique_recordings),
        "class_counts": class_counts,
    }


def active_sentinel_set_hash(conn: sqlite3.Connection) -> str | None:
    rows = [
        list(row)
        for row in conn.execute(
            """
            SELECT sentinel_id,expected_media_sha256,expected_context_json,label_json
            FROM commons_validation_sentinels WHERE active=1 ORDER BY sentinel_id
            """
        )
    ]
    if not rows:
        return None
    return hashlib.sha256(_canonical_json(rows).encode("utf-8")).hexdigest()


def _pick_ranked(
    candidates: Iterable[_Candidate],
    *,
    count: int,
    used_now: set[str],
    used_history: set[str],
    seed: str,
    rank: Callable[[_Candidate], float],
) -> list[_Candidate]:
    available = [
        candidate
        for candidate in candidates
        if candidate.source_recording_id not in used_now
    ]
    selected: list[_Candidate] = []
    group_counts: dict[tuple[str, int], int] = {}
    while len(selected) < count and available:
        chosen = min(
            available,
            key=lambda candidate: (
                candidate.source_recording_id in used_history,
                group_counts.get(candidate.diversity_group, 0),
                rank(candidate),
                _stable_hash(
                    seed, candidate.source_recording_id, candidate.start_sample
                ),
            ),
        )
        selected.append(chosen)
        used_now.add(chosen.source_recording_id)
        group_counts[chosen.diversity_group] = group_counts.get(chosen.diversity_group, 0) + 1
        available = [
            candidate
            for candidate in available
            if candidate.source_recording_id != chosen.source_recording_id
        ]
    return selected


def _score(candidate: _Candidate, class_name: str) -> float:
    return float(candidate.model_context[class_name]["score"])


def _threshold(candidate: _Candidate, class_name: str) -> float:
    return float(candidate.model_context[class_name]["threshold"])


def _boundary_selection(
    frame: Sequence[_Candidate],
    *,
    class_name: str,
    side: str,
    used_now: set[str],
    used_history: set[str],
    seed: str,
) -> list[_Candidate]:
    if side == "above":
        eligible = [candidate for candidate in frame if _score(candidate, class_name) >= _threshold(candidate, class_name)]
    elif side == "below":
        eligible = [candidate for candidate in frame if _score(candidate, class_name) < _threshold(candidate, class_name)]
    else:
        raise ValueError("boundary side must be above or below")
    return _pick_ranked(
        eligible,
        count=2,
        used_now=used_now,
        used_history=used_history,
        seed=f"{seed}|boundary|{class_name}|{side}",
        rank=lambda candidate: abs(_score(candidate, class_name) - _threshold(candidate, class_name)),
    )


def _positive_spread_selection(
    frame: Sequence[_Candidate],
    *,
    class_name: str,
    used_now: set[str],
    used_history: set[str],
    seed: str,
) -> list[_Candidate]:
    eligible = [
        candidate
        for candidate in frame
        if candidate.source_recording_id not in used_now
        and _score(candidate, class_name) >= _threshold(candidate, class_name)
    ]
    if not eligible:
        return []
    low = min(_score(candidate, class_name) for candidate in eligible)
    high = max(_score(candidate, class_name) for candidate in eligible)
    targets = [low + (high - low) * fraction for fraction in (0.1, 0.4, 0.7, 0.95)]
    selected: list[_Candidate] = []
    for index, target in enumerate(targets):
        picked = _pick_ranked(
            eligible,
            count=1,
            used_now=used_now,
            used_history=used_history,
            seed=f"{seed}|positive|{class_name}|{index}",
            rank=lambda candidate, target=target: abs(_score(candidate, class_name) - target),
        )
        if not picked:
            break
        selected.extend(picked)
        eligible = [
            candidate
            for candidate in eligible
            if candidate.source_recording_id not in used_now
        ]
    return selected


def _random_controls(
    frame: Sequence[_Candidate],
    *,
    used_now: set[str],
    seed: str,
) -> list[_Candidate]:
    by_recording: dict[str, list[_Candidate]] = {}
    for candidate in frame:
        if candidate.source_recording_id not in used_now:
            by_recording.setdefault(candidate.source_recording_id, []).append(candidate)
    representatives: list[_Candidate] = []
    for recording_id, spans in by_recording.items():
        representatives.append(
            min(
                spans,
                key=lambda item: _stable_hash(
                    seed, recording_id, item.start_sample
                ),
            )
        )
    selected = sorted(
        representatives,
        key=lambda candidate: _stable_hash(
            seed, "random-control", candidate.source_recording_id
        ),
    )[:6]
    used_now.update(candidate.source_recording_id for candidate in selected)
    return selected


def _plan_selection(
    frame: Sequence[_Candidate],
    *,
    seed: str,
    used_history: set[str],
) -> tuple[list[_Selected], str | None]:
    used_now: set[str] = set()
    controls = _random_controls(frame, used_now=used_now, seed=seed)
    if len(controls) != 6:
        return [], "insufficient random-control recordings"
    selected: list[_Selected] = [
        _Selected(
            candidate,
            "random_control",
            None,
            None,
            "uniform_full_frame_score_independent",
        )
        for candidate in controls
    ]
    for class_name in MODEL_CLASSES:
        for side in ("above", "below"):
            candidates = _boundary_selection(
                frame,
                class_name=class_name,
                side=side,
                used_now=used_now,
                used_history=used_history,
                seed=seed,
            )
            if len(candidates) != 2:
                return [], f"insufficient {class_name} boundary-{side} recordings"
            for candidate in candidates:
                context = candidate.model_context[class_name]
                selected.append(
                    _Selected(
                        candidate,
                        "boundary",
                        class_name,
                        str(context["bundle_id"]),
                        "nearest_threshold_with_day_hour_diversity",
                        side,
                    )
                )
    for class_name in MODEL_CLASSES:
        candidates = _positive_spread_selection(
            frame,
            class_name=class_name,
            used_now=used_now,
            used_history=used_history,
            seed=seed,
        )
        if len(candidates) != 4:
            return [], f"insufficient {class_name} positive recordings"
        for candidate in candidates:
            context = candidate.model_context[class_name]
            selected.append(
                _Selected(
                    candidate,
                    "model_positive",
                    class_name,
                    str(context["bundle_id"]),
                    "positive_score_spread_with_day_hour_diversity",
                )
            )
    if len(selected) != UNIQUE_COUNT:
        return [], f"validation sampler produced {len(selected)} unique items"
    selected.sort(
        key=lambda item: _stable_hash(
            seed,
            "display",
            item.candidate.source_recording_id,
            item.candidate.start_sample,
            item.lane,
            item.primary_class_name,
        )
    )
    return selected, None


def _selected_metadata(selected: _Selected) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "selection": selected.selection,
        "model_context": selected.candidate.model_context,
        "recorded_at": selected.candidate.started_at,
        "media_sha256": selected.candidate.media_sha256,
        "training_eligible": False,
        "causal_claim": False,
    }
    if selected.boundary_side is not None:
        metadata["boundary_side"] = selected.boundary_side
    return metadata


def _verify_existing_packet(conn: sqlite3.Connection, row: sqlite3.Row | tuple[Any, ...]) -> int:
    packet_id = str(row[0])
    protocol_version = str(row[1])
    week_start = str(row[2])
    timezone_name = str(row[3])
    target_count = int(row[4])
    manifest_sha256 = str(row[5])
    manifest_json = str(row[6])
    if hashlib.sha256(manifest_json.encode("utf-8")).hexdigest() != manifest_sha256:
        raise RuntimeError("existing validation packet manifest hash mismatch")
    try:
        manifest = json.loads(manifest_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("existing validation packet manifest is invalid JSON") from exc
    if (
        manifest.get("protocol_version") != protocol_version
        or manifest.get("week_start") != week_start
        or manifest.get("timezone") != timezone_name
        or int(manifest.get("target_count", -1)) != target_count
    ):
        raise RuntimeError("existing validation packet manifest header mismatch")
    expected_items = manifest.get("items")
    if not isinstance(expected_items, list) or len(expected_items) != target_count:
        raise RuntimeError("existing validation packet manifest item count mismatch")
    actual_rows = conn.execute(
        """
        SELECT item_id,position,event_id,media_id,source_recording_id,start_sample,
               end_sample,sample_rate,lane,source_item_id,primary_class_name,
               primary_bundle_id,sampling_metadata_json
        FROM commons_validation_items WHERE packet_id=? ORDER BY position
        """,
        (packet_id,),
    ).fetchall()
    actual_items = []
    for item in actual_rows:
        try:
            metadata = json.loads(str(item[12]))
        except json.JSONDecodeError as exc:
            raise RuntimeError("existing validation packet item metadata is invalid") from exc
        actual_items.append(
            {
                "item_id": str(item[0]),
                "position": int(item[1]),
                "event_id": str(item[2]),
                "media_id": str(item[3]),
                "source_recording_id": str(item[4]),
                "start_sample": int(item[5]),
                "end_sample": int(item[6]),
                "sample_rate": int(item[7]),
                "lane": str(item[8]),
                "source_item_id": None if item[9] is None else str(item[9]),
                "primary_class_name": None if item[10] is None else str(item[10]),
                "primary_bundle_id": None if item[11] is None else str(item[11]),
                "sampling_metadata": metadata,
            }
        )
    if actual_items != expected_items:
        raise RuntimeError("existing validation packet items do not match manifest")
    return len(actual_items)


def generate_weekly_packet(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    week_start: date | None = None,
    timezone_name: str = LOCAL_TIMEZONE,
) -> PacketResult:
    """Create one immutable blinded validation packet for a local week."""
    current = _aware_datetime(now or datetime.now(timezone.utc))
    selected_week = week_start or local_week_start(current, timezone_name)
    week_text = selected_week.isoformat()
    packet_id = _stable_id("vpk", f"{PROTOCOL_VERSION}|{timezone_name}|{week_text}")
    existing = conn.execute(
        """
        SELECT packet_id,protocol_version,week_start,timezone,target_count,
               manifest_sha256,manifest_json
        FROM commons_validation_packets
        WHERE protocol_version=? AND week_start=?
        """,
        (PROTOCOL_VERSION, week_text),
    ).fetchone()
    if existing is not None:
        item_count = _verify_existing_packet(conn, existing)
        return PacketResult(str(existing[0]), False, item_count, "existing packet")

    frame = _sampling_frame(conn)
    unique_recordings = {candidate.source_recording_id for candidate in frame}
    if len(unique_recordings) < UNIQUE_COUNT:
        return PacketResult(
            None,
            False,
            0,
            f"sampling frame needs at least 22 unique parent recordings; found {len(unique_recordings)}",
        )

    seed = hashlib.sha256(
        f"{PROTOCOL_VERSION}|{timezone_name}|{week_text}".encode("utf-8")
    ).hexdigest()
    used_history = _history_recordings(conn)
    selected, selection_error = _plan_selection(
        frame, seed=seed, used_history=used_history
    )
    if selection_error is not None:
        return PacketResult(None, False, 0, selection_error)
    item_specs: list[dict[str, Any]] = []
    for position, item in enumerate(selected, start=1):
        item_id = _stable_id(
            "vit",
            f"{packet_id}|{position}|{item.candidate.source_recording_id}|{item.candidate.start_sample}|{item.lane}|{item.primary_class_name}",
        )
        item_specs.append(
            {
                "item_id": item_id,
                "position": position,
                "event_id": item.candidate.event_id,
                "media_id": item.candidate.media_id,
                "source_recording_id": item.candidate.source_recording_id,
                "start_sample": item.candidate.start_sample,
                "end_sample": item.candidate.end_sample,
                "sample_rate": item.candidate.sample_rate,
                "lane": item.lane,
                "source_item_id": None,
                "primary_class_name": item.primary_class_name,
                "primary_bundle_id": item.primary_bundle_id,
                "sampling_metadata": _selected_metadata(item),
            }
        )

    repeat_sources = sorted(
        item_specs[:18], key=lambda item: _stable_hash(seed, "repeat", item["item_id"])
    )[:2]
    for position, source in enumerate(repeat_sources, start=23):
        metadata = dict(source["sampling_metadata"])
        metadata["selection"] = "hidden_repeat_for_within_reviewer_agreement"
        metadata["repeat_of_item_id"] = source["item_id"]
        item_specs.append(
            {
                **{key: source[key] for key in (
                    "event_id",
                    "media_id",
                    "source_recording_id",
                    "start_sample",
                    "end_sample",
                    "sample_rate",
                    "primary_class_name",
                    "primary_bundle_id",
                )},
                "item_id": _stable_id(
                    "vit", f"{packet_id}|{position}|repeat|{source['item_id']}"
                ),
                "position": position,
                "lane": "blind_repeat",
                "source_item_id": source["item_id"],
                "sampling_metadata": metadata,
            }
        )

    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "week_start": week_text,
        "timezone": timezone_name,
        "sampling_seed": seed,
        "target_count": TARGET_COUNT,
        "sampling_unit": "unique_parent_recording_except_hidden_repeats",
        "review_span": "exact_imported_five_second_window",
        "blinded_fields": ["lane", "model", "score", "threshold", "crosses_threshold"],
        "training_eligible": False,
        "items": item_specs,
    }
    manifest_json = _canonical_json(manifest)
    manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    created_at = current.isoformat(timespec="microseconds")

    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO commons_validation_packets(
                packet_id,protocol_version,week_start,timezone,sampling_seed,
                target_count,state,manifest_sha256,manifest_json,created_at
            ) VALUES (?,?,?,?,?,?,'ready',?,?,?)
            """,
            (
                packet_id,
                PROTOCOL_VERSION,
                week_text,
                timezone_name,
                seed,
                TARGET_COUNT,
                manifest_sha256,
                manifest_json,
                created_at,
            ),
        )
        for item in item_specs:
            conn.execute(
                """
                INSERT INTO commons_validation_items(
                    item_id,packet_id,position,event_id,media_id,source_recording_id,start_sample,
                    end_sample,sample_rate,lane,source_item_id,
                    primary_class_name,primary_bundle_id,state,
                    sampling_metadata_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending',?,?)
                """,
                (
                    item["item_id"],
                    packet_id,
                    item["position"],
                    item["event_id"],
                    item["media_id"],
                    item["source_recording_id"],
                    item["start_sample"],
                    item["end_sample"],
                    item["sample_rate"],
                    item["lane"],
                    item["source_item_id"],
                    item["primary_class_name"],
                    item["primary_bundle_id"],
                    _canonical_json(item["sampling_metadata"]),
                    created_at,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return PacketResult(packet_id, True, len(item_specs), None)


def wav_span_bytes(
    source_value: bytes | Path | str,
    *,
    start_sample: int,
    end_sample: int,
    span_sample_rate: int,
) -> bytes:
    """Return a model-time span in the source WAV's native format and rate."""
    if isinstance(source_value, bytes):
        source_bytes = source_value
    else:
        source_path = resolve_no_symlinks(source_value, require_file=True)
        source_bytes = source_path.read_bytes()
    if start_sample < 0 or end_sample <= start_sample or span_sample_rate <= 0:
        raise ValueError("validation audio span is invalid")
    with wave.open(io.BytesIO(source_bytes), "rb") as source:
        source_sample_rate = source.getframerate()
        source_start = (
            start_sample * source_sample_rate + span_sample_rate // 2
        ) // span_sample_rate
        source_end = (
            end_sample * source_sample_rate + span_sample_rate // 2
        ) // span_sample_rate
        if source_end > source.getnframes():
            raise ValueError("validation audio span is outside WAV frame range")
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        compression_type = source.getcomptype()
        compression_name = source.getcompname()
        source.setpos(source_start)
        frames = source.readframes(source_end - source_start)
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(source_sample_rate)
        target.setcomptype(compression_type, compression_name)
        target.writeframes(frames)
    return output.getvalue()


def _presence_assertion(value: str) -> tuple[bool | None, str]:
    if value == "present":
        return True, "confirmed"
    if value == "absent":
        return False, "confirmed"
    if value == "uncertain":
        return None, "uncertain"
    raise ValueError("presence must be present, absent, or uncertain")


def record_validation_review(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    reviewer: str,
    insect_presence: str,
    chicken_presence: str,
    signal_quality: str,
    reviewed_at: str,
    confounders: Sequence[str] = (),
    notes: str | None = None,
    review_seconds: float | None = None,
) -> ReviewResult:
    """Append one blinded two-label review and both human assertions atomically."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    insect_value, insect_certainty = _presence_assertion(insect_presence)
    chicken_value, chicken_certainty = _presence_assertion(chicken_presence)
    qualities = {"clear", "distant", "overlapping", "clipped", "noisy", "inaudible"}
    if signal_quality not in qualities:
        raise ValueError("unknown signal quality")
    if review_seconds is not None and (not math.isfinite(review_seconds) or review_seconds < 0):
        raise ValueError("review_seconds must be a finite non-negative number")
    normalized_reviewed_at = _aware_datetime(reviewed_at).isoformat(timespec="microseconds")
    normalized_confounders = sorted({str(value).strip() for value in confounders if str(value).strip()})
    if any(len(value) > 80 for value in normalized_confounders):
        raise ValueError("confounder labels must be at most 80 characters")
    if notes is not None and len(notes) > 4000:
        raise ValueError("review notes must be at most 4000 characters")

    row = conn.execute(
        """
        SELECT i.packet_id,i.event_id,i.media_id,i.start_sample,i.end_sample,
               i.sample_rate,i.lane,i.state,i.sampling_metadata_json,p.protocol_version
        FROM commons_validation_items AS i
        JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
        WHERE i.item_id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("validation item does not exist")
    if str(row[9]) != PROTOCOL_VERSION:
        raise ValueError("validation item belongs to an inactive validation protocol")
    if str(row[7]) != "pending":
        raise ValueError("validation item is already reviewed")
    if conn.execute(
        "SELECT 1 FROM commons_validation_reviews WHERE item_id=?", (item_id,)
    ).fetchone() is not None:
        raise ValueError("validation item is already reviewed")

    packet_id = str(row[0])
    event_id = str(row[1])
    media_id = str(row[2])
    start_sample = int(row[3])
    end_sample = int(row[4])
    lane = str(row[6])
    try:
        metadata = json.loads(str(row[8]))
        model_context = metadata["model_context"]
        contexts = {class_name: model_context[class_name] for class_name in MODEL_CLASSES}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("validation item has invalid frozen model context") from exc
    review_id = _stable_id("vrw", item_id)
    review_context = {
        "validation_protocol_version": str(row[9]),
        "validation_packet_id": packet_id,
        "validation_item_id": item_id,
        "validation_review_id": review_id,
        "validation_lane": lane,
    }

    assertion_ids: list[str] = []
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for class_name, present, certainty in (
            ("insect_present", insect_value, insect_certainty),
            ("chicken_vocalization_present", chicken_value, chicken_certainty),
        ):
            context = contexts[class_name]
            assertion_ids.append(
                record_human_acoustic_review(
                    conn,
                    event_id=event_id,
                    media_id=media_id,
                    bundle_id=str(context["bundle_id"]),
                    class_name=class_name,
                    present=present,
                    certainty=certainty,
                    reviewer=reviewer,
                    start_sample=start_sample,
                    end_sample=end_sample,
                    reviewed_at=normalized_reviewed_at,
                    notes=notes,
                    training_eligible=False,
                    review_context=review_context,
                    manage_transaction=False,
                    complete_calibration_queue=False,
                    mark_event_reviewed=False,
                )
            )
        conn.execute(
            """
            INSERT INTO commons_validation_reviews(
                review_id,item_id,reviewer,insect_presence,chicken_presence,
                signal_quality,confounders_json,notes,review_seconds,
                assertion_ids_json,reviewed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                review_id,
                item_id,
                reviewer,
                insect_presence,
                chicken_presence,
                signal_quality,
                _canonical_json(normalized_confounders),
                notes,
                review_seconds,
                _canonical_json(assertion_ids),
                normalized_reviewed_at,
            ),
        )
        conn.execute(
            """
            UPDATE commons_validation_items
            SET state='completed',completed_at=? WHERE item_id=? AND state='pending'
            """,
            (normalized_reviewed_at, item_id),
        )
        pending = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM commons_validation_items
                WHERE packet_id=? AND state='pending'
                """,
                (packet_id,),
            ).fetchone()[0]
        )
        if pending == 0:
            conn.execute(
                """
                UPDATE commons_validation_packets
                SET state='completed',completed_at=? WHERE packet_id=?
                """,
                (normalized_reviewed_at, packet_id),
            )
        else:
            conn.execute(
                """
                UPDATE commons_validation_packets
                SET state='in_progress' WHERE packet_id=? AND state='ready'
                """,
                (packet_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ReviewResult(review_id, item_id, packet_id, (assertion_ids[0], assertion_ids[1]))


def wilson_interval(
    successes: int, total: int, *, z: float = 1.959963984540054
) -> tuple[float | None, float | None]:
    """Return a two-sided Wilson score interval for one binomial proportion."""
    if total == 0:
        return None, None
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("Wilson interval counts are invalid")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return center - margin, center + margin


def _presence_summary(values: Sequence[str]) -> dict[str, Any]:
    present = sum(value == "present" for value in values)
    absent = sum(value == "absent" for value in values)
    uncertain = sum(value == "uncertain" for value in values)
    decided = present + absent
    low, high = wilson_interval(present, decided)
    return {
        "reviewed": len(values),
        "decided": decided,
        "present": present,
        "absent": absent,
        "uncertain": uncertain,
        "empirical_positive_rate": None if decided == 0 else present / decided,
        "wilson_95_low": low,
        "wilson_95_high": high,
        "interval_scope": "descriptive_binomial_interval_for_realized_sample_only",
    }


def _report_score_band(score: float) -> str:
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


def validation_report(
    conn: sqlite3.Connection, *, packet_id: str | None = None
) -> dict[str, Any]:
    """Build event-level packet or cumulative metrics without recall claims."""
    where = "WHERE i.state='completed' AND p.protocol_version=?"
    parameters: tuple[Any, ...] = (PROTOCOL_VERSION,)
    if packet_id is not None:
        where = "WHERE i.state='completed' AND i.packet_id=?"
        parameters = (packet_id,)
    rows = conn.execute(
        f"""
        SELECT i.item_id,i.packet_id,i.event_id,i.lane,i.source_item_id,
               i.primary_class_name,i.sampling_metadata_json,
               r.insect_presence,r.chicken_presence,r.signal_quality,
               r.review_seconds,r.reviewed_at,e.started_at,i.source_recording_id
        FROM commons_validation_items AS i
        JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
        JOIN commons_validation_reviews AS r ON r.item_id=i.item_id
        JOIN commons_events AS e ON e.event_id=i.event_id
        {where}
        ORDER BY r.reviewed_at,i.item_id
        """,
        parameters,
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(str(row[6]))
        except json.JSONDecodeError as exc:
            raise ValueError(f"validation item {row[0]} has invalid metadata") from exc
        records.append(
            {
                "item_id": str(row[0]),
                "packet_id": str(row[1]),
                "event_id": str(row[2]),
                "lane": str(row[3]),
                "source_item_id": None if row[4] is None else str(row[4]),
                "primary_class_name": None if row[5] is None else str(row[5]),
                "metadata": metadata,
                "insect_present": str(row[7]),
                "chicken_vocalization_present": str(row[8]),
                "signal_quality": str(row[9]),
                "review_seconds": None if row[10] is None else float(row[10]),
                "reviewed_at": str(row[11]),
                "started_at": str(row[12]),
                "source_recording_id": str(row[13]),
            }
        )
    non_repeats = [record for record in records if record["lane"] != "blind_repeat"]
    if packet_id is None:
        by_recording: dict[str, dict[str, Any]] = {}
        for record in non_repeats:
            by_recording.setdefault(record["source_recording_id"], record)
        analysis_records = list(by_recording.values())
    else:
        analysis_records = non_repeats
    performance: dict[str, dict[str, Any]] = {}
    for class_name in MODEL_CLASSES:
        class_performance: dict[str, Any] = {}
        class_performance["model_positive"] = _presence_summary(
            [
                record[class_name]
                for record in analysis_records
                if record["lane"] == "model_positive"
                and record["primary_class_name"] == class_name
            ]
        )
        for side in ("above", "below"):
            class_performance[f"boundary_{side}"] = _presence_summary(
                [
                    record[class_name]
                    for record in analysis_records
                    if record["lane"] == "boundary"
                    and record["primary_class_name"] == class_name
                    and record["metadata"].get("boundary_side") == side
                ]
            )
        class_performance["random_control"] = _presence_summary(
            [
                record[class_name]
                for record in analysis_records
                if record["lane"] == "random_control"
            ]
        )
        performance[class_name] = class_performance

    score_bands: dict[str, dict[str, Any]] = {}
    for class_name in MODEL_CLASSES:
        grouped: dict[str, list[str]] = {}
        for record in analysis_records:
            context = record["metadata"]["model_context"][class_name]
            band = _report_score_band(float(context["score"]))
            grouped.setdefault(band, []).append(record[class_name])
        score_bands[class_name] = {
            band: _presence_summary(values) for band, values in sorted(grouped.items())
        }

    by_item = {record["item_id"]: record for record in records}
    repeat_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        if record["lane"] != "blind_repeat" or record["source_item_id"] is None:
            continue
        source = by_item.get(record["source_item_id"])
        if source is not None:
            repeat_pairs.append((source, record))
    paired = len(repeat_pairs)
    repeat_agreement = {
        "paired_items": paired,
        "insect_exact_agreement": (
            None
            if paired == 0
            else sum(left["insect_present"] == right["insect_present"] for left, right in repeat_pairs) / paired
        ),
        "chicken_exact_agreement": (
            None
            if paired == 0
            else sum(left["chicken_vocalization_present"] == right["chicken_vocalization_present"] for left, right in repeat_pairs) / paired
        ),
        "signal_quality_exact_agreement": (
            None
            if paired == 0
            else sum(left["signal_quality"] == right["signal_quality"] for left, right in repeat_pairs) / paired
        ),
    }

    local_times = [
        _aware_datetime(record["started_at"]).astimezone(ZoneInfo(LOCAL_TIMEZONE))
        for record in analysis_records
    ]
    review_times = [
        record["review_seconds"]
        for record in records
        if record["review_seconds"] is not None
    ]
    uncertain_labels = sum(
        record[class_name] == "uncertain"
        for record in records
        for class_name in MODEL_CLASSES
    )
    report = {
        "scope": "cumulative" if packet_id is None else "packet",
        "packet_id": packet_id,
        "reviewed_items": len(records),
        "analysis_parent_recordings": len(analysis_records),
        "performance": performance,
        "score_band_empirical_rates": score_bands,
        "repeat_agreement": repeat_agreement,
        "coverage": {
            "unique_recordings": len(
                {record["source_recording_id"] for record in analysis_records}
            ),
            "local_dates": sorted({value.date().isoformat() for value in local_times}),
            "local_hours": sorted({value.hour for value in local_times}),
        },
        "uncertainty": {
            "uncertain_labels": uncertain_labels,
            "total_labels": len(records) * len(MODEL_CLASSES),
            "rate": None if not records else uncertain_labels / (len(records) * len(MODEL_CLASSES)),
        },
        "review_burden": {
            "timed_reviews": len(review_times),
            "total_seconds": sum(review_times),
            "median_seconds": None if not review_times else median(review_times),
        },
        "limitations": [
            "Candidate and boundary review does not estimate recall; recall requires independent complete review of bounded microphone-days or time blocks.",
            "Model scores are uncalibrated ranking scores and must not be interpreted as probabilities.",
            "Random-control positives estimate target occurrence in sampled controls, not abundance or occupancy.",
            "Wilson intervals are descriptive binomial intervals conditional on the realized packet; purposive lanes and deterministic selection do not support design-based population confidence claims.",
            "Cumulative performance summaries use at most one reviewed item per frozen source recording; neighboring windows and later-week reuse are not treated as independent observations.",
            "Environmental and visual context remain non-causal unless a separate study design establishes causality.",
        ],
    }
    return report


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def promote_validation_sentinel(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    promoted_by: str,
    promoted_at: str,
) -> str:
    """Promote one decided reviewed span into the immutable sentinel foundation."""
    promoted_by = promoted_by.strip()
    if not promoted_by:
        raise ValueError("sentinel promoter is required")
    promoted_at = _aware_datetime(promoted_at).isoformat(timespec="microseconds")
    row = conn.execute(
        """
        SELECT i.event_id,i.media_id,i.start_sample,i.end_sample,i.sample_rate,
               i.sampling_metadata_json,m.sha256,r.insect_presence,r.chicken_presence,
               r.signal_quality,r.review_id,p.protocol_version
        FROM commons_validation_items AS i
        JOIN commons_media AS m ON m.media_id=i.media_id
        JOIN commons_validation_reviews AS r ON r.item_id=i.item_id
        JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
        WHERE i.item_id=? AND i.state='completed'
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("sentinel promotion requires a completed validation review")
    if str(row[11]) != PROTOCOL_VERSION:
        raise ValueError("validation item belongs to an inactive validation protocol")
    if "uncertain" in {str(row[7]), str(row[8])}:
        raise ValueError("uncertain validation reviews cannot become sentinels")
    metadata = json.loads(str(row[5]))
    expected_context = {
        "event_id": str(row[0]),
        "media_id": str(row[1]),
        "start_sample": int(row[2]),
        "end_sample": int(row[3]),
        "sample_rate": int(row[4]),
        "model_context": metadata["model_context"],
    }
    labels = {
        "insect_presence": str(row[7]),
        "chicken_presence": str(row[8]),
        "signal_quality": str(row[9]),
        "review_id": str(row[10]),
        "training_eligible": False,
    }
    sentinel_id = _stable_id("vsn", item_id)
    existing = conn.execute(
        "SELECT item_id FROM commons_validation_sentinels WHERE sentinel_id=?",
        (sentinel_id,),
    ).fetchone()
    if existing is not None:
        if str(existing[0]) != item_id:
            raise ValueError("sentinel identity collision")
        return sentinel_id
    conn.execute(
        """
        INSERT INTO commons_validation_sentinels(
            sentinel_id,item_id,event_id,media_id,expected_media_sha256,
            expected_context_json,label_json,promoted_by,promoted_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            sentinel_id,
            item_id,
            str(row[0]),
            str(row[1]),
            str(row[6]),
            _canonical_json(expected_context),
            _canonical_json(labels),
            promoted_by,
            promoted_at,
        ),
    )
    conn.commit()
    return sentinel_id


def verify_validation_sentinels(
    conn: sqlite3.Connection, *, checked_at: str | None = None
) -> dict[str, int]:
    """Append artifact/context checks for every active promoted sentinel."""
    checked = _aware_datetime(checked_at or datetime.now(timezone.utc)).isoformat(timespec="microseconds")
    rows = conn.execute(
        """
        SELECT s.sentinel_id,s.expected_media_sha256,s.expected_context_json,
               m.path,m.sha256,i.event_id,i.media_id,i.start_sample,i.end_sample,
               i.sample_rate,i.sampling_metadata_json
        FROM commons_validation_sentinels AS s
        JOIN commons_media AS m ON m.media_id=s.media_id
        JOIN commons_validation_items AS i ON i.item_id=s.item_id
        WHERE s.active=1 ORDER BY s.sentinel_id
        """
    ).fetchall()
    counts = {"active": len(rows), "pass": 0, "drift": 0, "missing": 0}
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            sentinel_id = str(row[0])
            expected_sha = str(row[1])
            expected_context = json.loads(str(row[2]))
            path = Path(str(row[3]))
            current_metadata = json.loads(str(row[10]))
            current_context = {
                "event_id": str(row[5]),
                "media_id": str(row[6]),
                "start_sample": int(row[7]),
                "end_sample": int(row[8]),
                "sample_rate": int(row[9]),
                "model_context": current_metadata["model_context"],
            }
            status = "pass"
            error: str | None = None
            actual_sha: str | None = None
            if path.is_symlink() or not path.is_file():
                status = "missing"
                error = "sentinel media unavailable or symlinked"
            else:
                actual_sha = _sha256_path(path)
                if actual_sha != expected_sha or str(row[4]) != expected_sha:
                    status = "drift"
                    error = "sentinel media hash drift"
                elif current_context != expected_context:
                    status = "drift"
                    error = "sentinel span or model context drift"
            observed = {
                "path": str(path),
                "actual_media_sha256": actual_sha,
                "database_media_sha256": str(row[4]),
                "expected_media_sha256": expected_sha,
                "current_context": current_context,
                "fresh_audio_rescore_performed": False,
            }
            check_id = _stable_id("vsc", f"{sentinel_id}|{checked}")
            conn.execute(
                """
                INSERT OR IGNORE INTO commons_validation_sentinel_checks(
                    check_id,sentinel_id,checked_at,status,observed_json,error
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    check_id,
                    sentinel_id,
                    checked,
                    status,
                    _canonical_json(observed),
                    error,
                ),
            )
            counts[status] += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts
