import io
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import wave
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.schema import SCHEMA_VERSION, migrate


def populate_validation_frame(
    conn: sqlite3.Connection,
    *,
    count: int = 60,
    reverse_scores: bool = False,
    score_overrides: dict[tuple[int, str], float] | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO commons_sites(
            site_id,name,public_region,privacy_level
        ) VALUES ('site-validation','Validation site','test region','private')
        """
    )
    base = datetime(2026, 7, 1, 4, tzinfo=timezone.utc)
    for index in range(count):
        event_id = f"evt-validation-{index:03d}"
        media_id = f"med-validation-{index:03d}"
        recording_id = f"rec-validation-{index:03d}"
        observed = base + timedelta(days=index % 12, hours=(index * 5) % 24)
        conn.execute(
            """
            INSERT INTO commons_events(
                event_id,idempotency_key,event_type,started_at,timezone,
                site_id,source,summary,privacy_level
            ) VALUES (?,?,'acoustic_recording',?,'UTC','site-validation',
                      'field_listener','validation fixture','private')
            """,
            (event_id, f"key-{event_id}", observed.isoformat()),
        )
        conn.execute(
            """
            INSERT INTO commons_media(
                media_id,event_id,idempotency_key,media_type,path,sha256,
                byte_size,mime_type,captured_at,privacy_level
            ) VALUES (?,?,?,'audio',?,?,960044,'audio/wav',?,'private')
            """,
            (
                media_id,
                event_id,
                f"key-{media_id}",
                f"/tmp/{recording_id}.wav",
                f"{index + 1:064x}"[-64:],
                observed.isoformat(),
            ),
        )
        phase = index % 20
        insect_base = 0.60 + phase * 0.02
        chicken_base = 0.98 - phase * 0.02
        for span_index, start in enumerate((0, 160000, 320000)):
            for bundle_id, model_slug, class_name, score in (
                (
                    "bundle-insect",
                    "insect-fixture",
                    "insect_present",
                    min(0.999999, insect_base + span_index * 0.004),
                ),
                (
                    "bundle-chicken",
                    "chicken-fixture",
                    "chicken_vocalization_present",
                    max(0.000001, chicken_base - span_index * 0.004),
                ),
            ):
                if reverse_scores:
                    score = max(0.000001, min(0.999999, 1.6 - score))
                if score_overrides is not None:
                    score = score_overrides.get((index, class_name), score)
                conn.execute(
                    """
                    INSERT INTO commons_acoustic_windows(
                        window_id,event_id,media_id,source_recording_id,
                        bundle_id,model_slug,class_name,start_sample,end_sample,
                        sample_rate,score,raw_score,threshold,crosses_threshold,
                        score_semantics,preprocess_recipe_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,32000,?,?,0.8,?,
                              'ranking','recipe-v1')
                    """,
                    (
                        f"win-{index:03d}-{span_index}-{class_name}",
                        event_id,
                        media_id,
                        recording_id,
                        bundle_id,
                        model_slug,
                        class_name,
                        start,
                        start + 160000,
                        score,
                        score * 2 - 1,
                        int(score >= 0.8),
                    ),
                )
    conn.commit()


class ValidationSchemaTest(unittest.TestCase):
    def test_schema_version_6_adds_validation_tables_and_guards(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertGreaterEqual(SCHEMA_VERSION, 6)
            self.assertGreaterEqual(SCHEMA_VERSION, 7)
            self.assertTrue(
                {
                    "commons_validation_packets",
                    "commons_validation_items",
                    "commons_validation_reviews",
                    "commons_validation_sentinels",
                    "commons_validation_sentinel_checks",
                }.issubset(tables)
            )
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            }
            self.assertTrue(
                {
                    "commons_guard_validation_packet_manifest_update",
                    "commons_guard_validation_reviews_update",
                    "commons_guard_validation_reviews_delete",
                    "commons_guard_validation_sentinel_checks_update",
                    "commons_guard_validation_sentinel_checks_delete",
                    "commons_guard_validation_packets_delete",
                    "commons_guard_validation_items_delete",
                    "commons_guard_validation_sentinels_update",
                    "commons_guard_validation_sentinels_delete",
                }.issubset(triggers)
            )
            item_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(commons_validation_items)")
            }
            self.assertIn("source_recording_id", item_columns)
            self.assertEqual(
                conn.execute(
                    "SELECT MAX(version) FROM commons_schema_versions"
                ).fetchone()[0],
                SCHEMA_VERSION,
            )
            conn.close()

    def test_validation_review_can_join_an_outer_transaction_without_training_promotion(self):
        from commons_lab.acoustic import record_human_acoustic_review

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            conn.execute(
                """
                INSERT INTO commons_sites(
                    site_id,name,public_region,privacy_level
                ) VALUES ('site-1','Test site','test region','private')
                """
            )
            conn.execute(
                """
                INSERT INTO commons_events(
                    event_id,idempotency_key,event_type,started_at,timezone,
                    site_id,source,summary,privacy_level
                ) VALUES ('evt-1','evt-key','acoustic_recording',
                          '2026-07-16T12:00:00+00:00','UTC','site-1',
                          'field_listener','fixture','private')
                """
            )
            conn.execute(
                """
                INSERT INTO commons_media(
                    media_id,event_id,idempotency_key,media_type,path,sha256,
                    byte_size,mime_type,captured_at,privacy_level
                ) VALUES ('med-1','evt-1','med-key','audio','/tmp/fixture.wav',
                          ?,100,'audio/wav','2026-07-16T12:00:00+00:00','private')
                """,
                ("a" * 64,),
            )
            conn.execute(
                """
                INSERT INTO commons_acoustic_windows(
                    window_id,event_id,media_id,source_recording_id,bundle_id,
                    model_slug,class_name,start_sample,end_sample,sample_rate,
                    score,raw_score,threshold,crosses_threshold,score_semantics,
                    preprocess_recipe_id
                ) VALUES ('win-1','evt-1','med-1','rec-1','bun-1','model-1',
                          'insect_present',0,160000,32000,0.8,1.2,0.9,0,
                          'ranking','recipe-1')
                """
            )
            conn.commit()

            conn.execute("BEGIN IMMEDIATE")
            assertion_id = record_human_acoustic_review(
                conn,
                event_id="evt-1",
                media_id="med-1",
                bundle_id="bun-1",
                class_name="insect_present",
                present=None,
                certainty="uncertain",
                reviewer="human:test",
                start_sample=0,
                end_sample=160000,
                reviewed_at="2026-07-16T12:05:00+00:00",
                training_eligible=False,
                review_context={
                    "validation_packet_id": "vpk-1",
                    "validation_item_id": "vit-1",
                },
                manage_transaction=False,
                complete_calibration_queue=False,
            )
            value = json.loads(
                conn.execute(
                    "SELECT value_json FROM commons_assertions WHERE assertion_id=?",
                    (assertion_id,),
                ).fetchone()[0]
            )
            self.assertIsNone(value["present"])
            self.assertFalse(value["training_eligible"])
            self.assertEqual(value["validation_item_id"], "vit-1")
            self.assertEqual(
                conn.execute(
                    "SELECT review_state FROM commons_events WHERE event_id='evt-1'"
                ).fetchone()[0],
                "reviewed",
            )
            conn.rollback()
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_assertions"
                ).fetchone()[0],
                0,
            )
            conn.close()


class WeeklyPacketTest(unittest.TestCase):
    def test_packet_is_deterministic_balanced_blinded_and_parent_unique(self):
        from commons_lab.validation import generate_weekly_packet

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn)
            now = datetime(2026, 7, 16, 16, tzinfo=timezone.utc)

            first = generate_weekly_packet(conn, now=now)
            replay = generate_weekly_packet(conn, now=now)

            self.assertTrue(first.created)
            self.assertEqual(first.item_count, 24)
            self.assertFalse(replay.created)
            self.assertEqual(replay.packet_id, first.packet_id)
            packet = conn.execute(
                """
                SELECT protocol_version,week_start,timezone,target_count,
                       manifest_sha256,manifest_json
                FROM commons_validation_packets WHERE packet_id=?
                """,
                (first.packet_id,),
            ).fetchone()
            self.assertEqual(packet[0], "weekly_blinded_v4")
            self.assertEqual(packet[1], "2026-07-13")
            self.assertEqual(packet[2], "America/New_York")
            self.assertEqual(packet[3], 24)
            import hashlib

            self.assertEqual(
                packet[4], hashlib.sha256(packet[5].encode("utf-8")).hexdigest()
            )
            rows = conn.execute(
                """
                SELECT item_id,position,event_id,source_recording_id,lane,source_item_id,
                       primary_class_name,sampling_metadata_json
                FROM commons_validation_items WHERE packet_id=?
                ORDER BY position
                """,
                (first.packet_id,),
            ).fetchall()
            self.assertEqual(
                Counter(row[4] for row in rows),
                {
                    "model_positive": 8,
                    "boundary": 8,
                    "random_control": 6,
                    "blind_repeat": 2,
                },
            )
            for lane in ("model_positive", "boundary"):
                self.assertEqual(
                    Counter(row[6] for row in rows if row[4] == lane),
                    {
                        "insect_present": 4,
                        "chicken_vocalization_present": 4,
                    },
                )
            boundary_sides = Counter(
                (row[6], json.loads(row[7])["boundary_side"])
                for row in rows
                if row[4] == "boundary"
            )
            self.assertEqual(
                boundary_sides,
                {
                    ("insect_present", "above"): 2,
                    ("insect_present", "below"): 2,
                    ("chicken_vocalization_present", "above"): 2,
                    ("chicken_vocalization_present", "below"): 2,
                },
            )
            unique_rows = [row for row in rows if row[4] != "blind_repeat"]
            self.assertEqual(len({row[3] for row in unique_rows}), 22)
            by_id = {row[0]: row for row in rows}
            repeats = [row for row in rows if row[4] == "blind_repeat"]
            for repeated in repeats:
                self.assertIn(repeated[5], by_id)
                source = by_id[repeated[5]]
                self.assertEqual(repeated[2], source[2])
                self.assertEqual(repeated[3], source[3])
                self.assertGreater(repeated[1] - source[1], 1)
            for row in rows:
                metadata = json.loads(row[7])
                self.assertIn("model_context", metadata)
                if row[4] == "random_control":
                    self.assertEqual(
                        metadata["selection"], "uniform_full_frame_score_independent"
                    )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM commons_validation_items WHERE packet_id=?",
                    (first.packet_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM commons_validation_packets WHERE packet_id=?",
                    (first.packet_id,),
                )
            conn.close()

    def test_later_week_prefers_unused_parent_recordings(self):
        from commons_lab.validation import generate_weekly_packet

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn, count=60)
            first = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            second = generate_weekly_packet(
                conn, now=datetime(2026, 7, 23, 16, tzinfo=timezone.utc)
            )
            self.assertTrue(second.created)
            first_events = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT source_recording_id FROM commons_validation_items
                    WHERE packet_id=? AND lane NOT IN ('blind_repeat','random_control')
                    """,
                    (first.packet_id,),
                )
            }
            second_events = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT source_recording_id FROM commons_validation_items
                    WHERE packet_id=? AND lane NOT IN ('blind_repeat','random_control')
                    """,
                    (second.packet_id,),
                )
            }
            self.assertTrue(first_events.isdisjoint(second_events))
            conn.close()

    def test_distinct_events_for_one_source_recording_are_one_sampling_unit(self):
        from commons_lab.validation import generate_weekly_packet

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn, count=60)
            conn.execute(
                """
                INSERT INTO commons_events(
                    event_id,idempotency_key,event_type,started_at,timezone,site_id,
                    source,summary,privacy_level
                )
                SELECT 'evt-duplicate-source','key-duplicate-source',event_type,
                       started_at,timezone,site_id,source,summary,privacy_level
                FROM commons_events WHERE event_id='evt-validation-000'
                """
            )
            conn.execute(
                """
                INSERT INTO commons_media(
                    media_id,event_id,idempotency_key,media_type,path,sha256,byte_size,
                    mime_type,captured_at,privacy_level
                )
                SELECT 'med-duplicate-source','evt-duplicate-source','key-med-duplicate',
                       media_type,path,sha256,byte_size,mime_type,captured_at,privacy_level
                FROM commons_media WHERE media_id='med-validation-000'
                """
            )
            conn.execute(
                """
                INSERT INTO commons_acoustic_windows(
                    window_id,event_id,media_id,source_recording_id,bundle_id,model_slug,
                    class_name,start_sample,end_sample,sample_rate,score,raw_score,
                    threshold,crosses_threshold,score_semantics,preprocess_recipe_id
                )
                SELECT 'dup-'||window_id,'evt-duplicate-source','med-duplicate-source',
                       source_recording_id,bundle_id,model_slug,class_name,start_sample+480000,
                       end_sample+480000,sample_rate,score,raw_score,threshold,crosses_threshold,
                       score_semantics,preprocess_recipe_id
                FROM commons_acoustic_windows WHERE event_id='evt-validation-000'
                """
            )
            conn.commit()
            packet = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            self.assertTrue(packet.created)
            unique_recordings = conn.execute(
                """
                SELECT COUNT(DISTINCT source_recording_id)
                FROM commons_validation_items
                WHERE packet_id=? AND lane!='blind_repeat'
                """,
                (packet.packet_id,),
            ).fetchone()[0]
            self.assertEqual(unique_recordings, 22)
            conn.close()

    def test_existing_packet_replay_rejects_a_missing_manifest_item(self):
        from commons_lab.validation import generate_weekly_packet

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn)
            packet = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            conn.execute("DROP TRIGGER commons_guard_validation_items_delete")
            conn.execute(
                """
                DELETE FROM commons_validation_items
                WHERE item_id=(
                    SELECT item_id FROM commons_validation_items
                    WHERE packet_id=? AND lane!='blind_repeat'
                      AND item_id NOT IN (
                          SELECT source_item_id FROM commons_validation_items
                          WHERE source_item_id IS NOT NULL
                      )
                    LIMIT 1
                )
                """,
                (packet.packet_id,),
            )
            conn.commit()
            with self.assertRaisesRegex(RuntimeError, "manifest"):
                generate_weekly_packet(
                    conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
                )
            conn.close()

    def test_insufficient_sampling_frame_is_recorded_without_partial_packet(self):
        from commons_lab.validation import generate_weekly_packet

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn, count=10)
            result = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            self.assertFalse(result.created)
            self.assertEqual(result.item_count, 0)
            self.assertIn("22 unique", result.reason)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_validation_packets"
                ).fetchone()[0],
                0,
            )
            conn.close()

    def test_readiness_uses_the_same_global_allocation_plan_as_generation(self):
        from commons_lab.validation import (
            PROTOCOL_VERSION,
            generate_weekly_packet,
            validation_sampling_readiness,
        )

        now = datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
        seed = hashlib.sha256(
            f"{PROTOCOL_VERSION}|America/New_York|2026-07-13".encode()
        ).hexdigest()
        control_indices = sorted(
            range(22),
            key=lambda index: hashlib.sha256(
                f"{seed}|random-control|recording-{index:03d}".encode()
            ).hexdigest(),
        )[:6]
        scarce_below = set(control_indices[:2])
        overrides = {
            (index, class_name): (0.7 if index in scarce_below else 0.9)
            for index in range(22)
            for class_name in (
                "insect_present",
                "chicken_vocalization_present",
            )
        }
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn, count=22, score_overrides=overrides)
            readiness = validation_sampling_readiness(conn, now=now)
            result = generate_weekly_packet(conn, now=now)
            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["reason"], result.reason)
            self.assertIn("boundary-below", result.reason or "")
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_validation_packets"
                ).fetchone()[0],
                0,
            )
            conn.close()


    def test_random_controls_are_selected_before_score_driven_lanes(self):
        from commons_lab.validation import (
            PROTOCOL_VERSION,
            _random_controls,
            _sampling_frame,
            generate_weekly_packet,
        )

        self.assertEqual(PROTOCOL_VERSION, "weekly_blinded_v4")
        control_sets = []
        with tempfile.TemporaryDirectory() as td:
            for index in range(2):
                conn = sqlite3.connect(Path(td) / f"archive-{index}.db")
                migrate(conn)
                populate_validation_frame(conn, count=60, reverse_scores=bool(index))
                frame = _sampling_frame(conn)
                baseline_used: set[str] = set()
                baseline = _random_controls(
                    frame,
                    used_now=baseline_used,
                    seed=hashlib.sha256(
                        b"weekly_blinded_v4|America/New_York|2026-07-13"
                    ).hexdigest(),
                )
                baseline_recordings = {
                    candidate.source_recording_id for candidate in baseline
                }
                expected_recordings = set(
                    sorted(
                        {candidate.source_recording_id for candidate in frame},
                        key=lambda recording_id: hashlib.sha256(
                            f"{hashlib.sha256(b'weekly_blinded_v4|America/New_York|2026-07-13').hexdigest()}|random-control|{recording_id}".encode()
                        ).hexdigest(),
                    )[:6]
                )
                self.assertEqual(baseline_recordings, expected_recordings)
                history_recordings = (
                    baseline_recordings
                    if index == 0
                    else {
                        candidate.source_recording_id
                        for candidate in frame
                        if candidate.source_recording_id not in baseline_recordings
                    }
                )
                history_recordings = set(sorted(history_recordings)[:6])
                conn.execute(
                    """
                    INSERT INTO commons_validation_packets(
                        packet_id,protocol_version,week_start,timezone,sampling_seed,
                        target_count,state,manifest_sha256,manifest_json,created_at
                    ) VALUES (?,?,?,'America/New_York','history',6,'ready',?,?,?)
                    """,
                    (
                        f"history-{index}",
                        "historical-test",
                        "2026-07-06",
                        f"{index + 1:064x}",
                        "{}",
                        "2026-07-06T12:00:00+00:00",
                    ),
                )
                for position, recording_id in enumerate(
                    sorted(history_recordings), start=1
                ):
                    event_id, media_id = conn.execute(
                        """
                        SELECT event_id,media_id FROM commons_acoustic_windows
                        WHERE source_recording_id=? ORDER BY window_id LIMIT 1
                        """,
                        (recording_id,),
                    ).fetchone()
                    conn.execute(
                        """
                        INSERT INTO commons_validation_items(
                            item_id,packet_id,position,event_id,media_id,source_recording_id,start_sample,
                            end_sample,sample_rate,lane,sampling_metadata_json,state,created_at
                        ) VALUES (?,?,?,?,?,?,0,160000,32000,'random_control','{}','pending',?)
                        """,
                        (
                            f"history-item-{index}-{position}",
                            f"history-{index}",
                            position,
                            event_id,
                            media_id,
                            recording_id,
                            "2026-07-06T12:00:00+00:00",
                        ),
                    )
                conn.commit()
                packet = generate_weekly_packet(
                    conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
                )
                self.assertTrue(packet.created)
                control_sets.append(
                    {
                        row[0]
                        for row in conn.execute(
                            """
                            SELECT source_recording_id FROM commons_validation_items
                            WHERE packet_id=? AND lane='random_control'
                            """,
                            (packet.packet_id,),
                        )
                    }
                )
                conn.close()
        self.assertEqual(control_sets[0], control_sets[1])


class ValidationReviewTest(unittest.TestCase):
    def _packet(self, conn: sqlite3.Connection):
        from commons_lab.validation import generate_weekly_packet

        populate_validation_frame(conn)
        return generate_weekly_packet(
            conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
        )

    def test_exact_wav_window_preserves_format_and_rejects_invalid_span(self):
        from commons_lab.validation import wav_span_bytes

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.wav"
            with wave.open(str(path), "wb") as target:
                target.setnchannels(2)
                target.setsampwidth(2)
                target.setframerate(32000)
                target.writeframes(b"\x01\x00\x02\x00" * 480000)
            payload = wav_span_bytes(
                path, start_sample=160000, end_sample=320000,
                span_sample_rate=32000
            )
            with wave.open(io.BytesIO(payload), "rb") as sliced:
                self.assertEqual(sliced.getnchannels(), 2)
                self.assertEqual(sliced.getsampwidth(), 2)
                self.assertEqual(sliced.getframerate(), 32000)
                self.assertEqual(sliced.getnframes(), 160000)
            with self.assertRaisesRegex(ValueError, "outside WAV"):
                wav_span_bytes(
                    path, start_sample=400000, end_sample=640000,
                    span_sample_rate=32000
                )

            source_48k = Path(td) / "source-48k.wav"
            with wave.open(str(source_48k), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(48000)
                target.writeframes(b"\x03\x00" * (15 * 48000))
            converted = wav_span_bytes(
                source_48k,
                start_sample=160000,
                end_sample=320000,
                span_sample_rate=32000,
            )
            with wave.open(io.BytesIO(converted), "rb") as sliced:
                self.assertEqual(sliced.getframerate(), 48000)
                self.assertEqual(sliced.getnframes(), 240000)

    def test_review_appends_two_training_ineligible_assertions_atomically(self):
        from commons_lab.validation import record_validation_review

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            packet = self._packet(conn)
            item = conn.execute(
                """
                SELECT item_id,event_id,primary_bundle_id FROM commons_validation_items
                WHERE packet_id=? AND lane NOT IN ('blind_repeat','random_control') ORDER BY position LIMIT 1
                """,
                (packet.packet_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO commons_review_queue(
                    queue_id,event_id,bundle_id,class_name,score_band,reason
                ) VALUES ('queue-keep',?,?, 'insect_present','test','fixture')
                """,
                (item[1], item[2] or "bundle-insect"),
            )
            conn.commit()

            result = record_validation_review(
                conn,
                item_id=item[0],
                reviewer="human:test",
                insect_presence="present",
                chicken_presence="absent",
                signal_quality="clear",
                confounders=["bird_overlap"],
                notes="Audible insect; no chicken vocalization.",
                review_seconds=12.5,
                reviewed_at="2026-07-16T16:10:00+00:00",
            )
            self.assertEqual(len(result.assertion_ids), 2)
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM commons_validation_items WHERE item_id=?",
                    (item[0],),
                ).fetchone()[0],
                "completed",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM commons_validation_packets WHERE packet_id=?",
                    (packet.packet_id,),
                ).fetchone()[0],
                "in_progress",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM commons_review_queue WHERE queue_id='queue-keep'"
                ).fetchone()[0],
                "pending",
            )
            values = [
                json.loads(row[0])
                for row in conn.execute(
                    """
                    SELECT value_json FROM commons_assertions
                    WHERE assertion_id IN (?,?) ORDER BY subject
                    """,
                    result.assertion_ids,
                )
            ]
            self.assertEqual(len(values), 2)
            self.assertTrue(all(value["training_eligible"] is False for value in values))
            self.assertTrue(all(value["validation_item_id"] == item[0] for value in values))
            with self.assertRaisesRegex(ValueError, "already reviewed"):
                record_validation_review(
                    conn,
                    item_id=item[0],
                    reviewer="human:test",
                    insect_presence="present",
                    chicken_presence="absent",
                    signal_quality="clear",
                    reviewed_at="2026-07-16T16:11:00+00:00",
                )
            conn.close()

    def test_hidden_repeat_is_an_independent_blinded_judgment(self):
        from commons_lab.validation import record_validation_review

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            packet = self._packet(conn)
            repeated = conn.execute(
                """
                SELECT item_id,source_item_id FROM commons_validation_items
                WHERE packet_id=? AND lane='blind_repeat' ORDER BY position LIMIT 1
                """,
                (packet.packet_id,),
            ).fetchone()
            first = record_validation_review(
                conn,
                item_id=repeated[1],
                reviewer="human:test",
                insect_presence="present",
                chicken_presence="absent",
                signal_quality="distant",
                reviewed_at="2026-07-16T16:10:00+00:00",
            )
            second = record_validation_review(
                conn,
                item_id=repeated[0],
                reviewer="human:test",
                insect_presence="present",
                chicken_presence="absent",
                signal_quality="distant",
                reviewed_at="2026-07-16T16:20:00+00:00",
            )
            self.assertTrue(set(first.assertion_ids).isdisjoint(second.assertion_ids))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_validation_reviews").fetchone()[0],
                2,
            )
            conn.close()

    def test_second_assertion_failure_rolls_back_entire_review(self):
        from commons_lab.validation import record_validation_review

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            packet = self._packet(conn)
            item_id = conn.execute(
                """
                SELECT item_id FROM commons_validation_items
                WHERE packet_id=? ORDER BY position LIMIT 1
                """,
                (packet.packet_id,),
            ).fetchone()[0]
            with patch(
                "commons_lab.validation.record_human_acoustic_review",
                side_effect=["ast-first", RuntimeError("second assertion failed")],
            ):
                with self.assertRaisesRegex(RuntimeError, "second assertion failed"):
                    record_validation_review(
                        conn,
                        item_id=item_id,
                        reviewer="human:test",
                        insect_presence="present",
                        chicken_presence="absent",
                        signal_quality="clear",
                        reviewed_at="2026-07-16T16:10:00+00:00",
                    )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_validation_reviews").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM commons_validation_items WHERE item_id=?",
                    (item_id,),
                ).fetchone()[0],
                "pending",
            )
            conn.close()


    def test_review_rejects_an_item_from_an_inactive_protocol(self):
        from commons_lab.validation import record_validation_review

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            packet = self._packet(conn)
            item_id = conn.execute(
                "SELECT item_id FROM commons_validation_items WHERE packet_id=? ORDER BY position LIMIT 1",
                (packet.packet_id,),
            ).fetchone()[0]
            with patch(
                "commons_lab.validation.PROTOCOL_VERSION", "weekly_blinded_future"
            ):
                with self.assertRaisesRegex(ValueError, "inactive validation protocol"):
                    record_validation_review(
                        conn,
                        item_id=item_id,
                        reviewer="human:test",
                        insect_presence="absent",
                        chicken_presence="absent",
                        signal_quality="clear",
                        reviewed_at="2026-07-16T16:10:00+00:00",
                    )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_validation_reviews").fetchone()[0],
                0,
            )
            conn.close()


class ValidationMetricsAndSentinelTest(unittest.TestCase):
    def test_wilson_interval_and_report_preserve_scientific_limits(self):
        from commons_lab.validation import (
            PROTOCOL_VERSION,
            generate_weekly_packet,
            record_validation_review,
            validation_report,
            wilson_interval,
        )

        low, high = wilson_interval(8, 10)
        self.assertAlmostEqual(low, 0.4902, places=3)
        self.assertAlmostEqual(high, 0.9433, places=3)
        self.assertEqual(wilson_interval(0, 0), (None, None))

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            populate_validation_frame(conn)
            packet = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            items = conn.execute(
                """
                SELECT item_id,lane,primary_class_name,source_item_id
                FROM commons_validation_items WHERE packet_id=? ORDER BY position
                """,
                (packet.packet_id,),
            ).fetchall()
            insect_positive = [row for row in items if row[1] == "model_positive" and row[2] == "insect_present"]
            chicken_positive = [row for row in items if row[1] == "model_positive" and row[2] == "chicken_vocalization_present"]
            controls = [row for row in items if row[1] == "random_control"]
            by_id = {row[0]: row for row in items}
            repeat = next(
                row
                for row in items
                if row[1] == "blind_repeat" and by_id[row[3]][1] != "random_control"
            )
            source_id = repeat[3]
            selected = [
                (insect_positive[0][0], "present", "absent"),
                (insect_positive[1][0], "present", "absent"),
                (insect_positive[2][0], "absent", "absent"),
                (insect_positive[3][0], "uncertain", "absent"),
                (chicken_positive[0][0], "absent", "present"),
                (chicken_positive[1][0], "absent", "absent"),
                (controls[0][0], "present", "absent"),
                (controls[1][0], "absent", "absent"),
            ]
            if source_id not in {item[0] for item in selected}:
                selected.append((source_id, "present", "absent"))
            source_label = next(item for item in selected if item[0] == source_id)
            selected.append((repeat[0], source_label[1], source_label[2]))
            for index, (item_id, insect, chicken) in enumerate(selected):
                record_validation_review(
                    conn,
                    item_id=item_id,
                    reviewer="human:test",
                    insect_presence=insect,
                    chicken_presence=chicken,
                    signal_quality="clear",
                    review_seconds=10 + index,
                    reviewed_at=(
                        datetime(2026, 7, 16, 16, 10, tzinfo=timezone.utc)
                        + timedelta(minutes=index)
                    ).isoformat(),
                )
            report = validation_report(conn, packet_id=packet.packet_id)
            insect = report["performance"]["insect_present"]["model_positive"]
            self.assertEqual(insect["decided"], 3)
            self.assertEqual(insect["present"], 2)
            self.assertEqual(insect["uncertain"], 1)
            self.assertAlmostEqual(insect["empirical_positive_rate"], 2 / 3)
            self.assertEqual(
                insect["interval_scope"],
                "descriptive_binomial_interval_for_realized_sample_only",
            )
            random_insect = report["performance"]["insect_present"]["random_control"]
            self.assertEqual(random_insect["decided"], 2)
            self.assertEqual(random_insect["present"], 1)
            self.assertEqual(report["repeat_agreement"]["paired_items"], 1)
            self.assertEqual(report["repeat_agreement"]["insect_exact_agreement"], 1.0)
            self.assertGreater(report["coverage"]["unique_recordings"], 0)
            self.assertGreater(report["review_burden"]["total_seconds"], 0)
            joined_limits = " ".join(report["limitations"]).lower()
            self.assertIn("recall", joined_limits)
            self.assertIn("probabil", joined_limits)
            self.assertIn("design-based", joined_limits)
            cumulative_before = validation_report(conn)
            source_item = conn.execute(
                """
                SELECT event_id,media_id,source_recording_id,start_sample,end_sample,
                       sample_rate,lane,primary_class_name,primary_bundle_id,
                       sampling_metadata_json
                FROM commons_validation_items WHERE item_id=?
                """,
                (selected[0][0],),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO commons_validation_packets(
                    packet_id,protocol_version,week_start,timezone,sampling_seed,
                    target_count,state,manifest_sha256,manifest_json,created_at
                ) VALUES ('packet-reused-parent',?,'2026-07-20','America/New_York',
                          'reuse',1,'ready',?,'{}','2026-07-20T12:00:00+00:00')
                """,
                (PROTOCOL_VERSION, hashlib.sha256(b"{}").hexdigest()),
            )
            duplicate_item_id = "vit_aaaaaaaaaaaaaaaaaaaaaaaa"
            conn.execute(
                """
                INSERT INTO commons_validation_items(
                    item_id,packet_id,position,event_id,media_id,source_recording_id,
                    start_sample,end_sample,sample_rate,lane,primary_class_name,
                    primary_bundle_id,state,sampling_metadata_json,created_at
                ) VALUES (?,'packet-reused-parent',1,?,?,?,?,?,?,?,?,?,'pending',?,
                          '2026-07-20T12:00:00+00:00')
                """,
                (duplicate_item_id, *source_item),
            )
            conn.commit()
            record_validation_review(
                conn,
                item_id=duplicate_item_id,
                reviewer="human:test",
                insect_presence=selected[0][1],
                chicken_presence=selected[0][2],
                signal_quality="clear",
                reviewed_at="2026-07-20T12:10:00+00:00",
            )
            cumulative_after = validation_report(conn)
            self.assertEqual(
                cumulative_after["reviewed_items"],
                cumulative_before["reviewed_items"] + 1,
            )
            self.assertEqual(
                cumulative_after["analysis_parent_recordings"],
                cumulative_before["analysis_parent_recordings"],
            )
            conn.close()

    def test_promoted_sentinel_detects_byte_drift_and_appends_checks(self):
        from commons_lab.validation import (
            generate_weekly_packet,
            promote_validation_sentinel,
            record_validation_review,
            verify_validation_sentinels,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            populate_validation_frame(conn)
            packet = generate_weekly_packet(
                conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            )
            item = conn.execute(
                """
                SELECT i.item_id,i.media_id FROM commons_validation_items AS i
                WHERE i.packet_id=? AND i.lane!='blind_repeat' ORDER BY i.position LIMIT 1
                """,
                (packet.packet_id,),
            ).fetchone()
            audio = root / "sentinel.wav"
            with wave.open(str(audio), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(32000)
                target.writeframes(b"\x00\x00" * 480000)
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            conn.execute(
                "UPDATE commons_media SET path=?,sha256=?,byte_size=? WHERE media_id=?",
                (str(audio), digest, audio.stat().st_size, item[1]),
            )
            conn.commit()
            record_validation_review(
                conn,
                item_id=item[0],
                reviewer="human:test",
                insect_presence="present",
                chicken_presence="absent",
                signal_quality="clear",
                reviewed_at="2026-07-16T16:10:00+00:00",
            )
            sentinel_id = promote_validation_sentinel(
                conn,
                item_id=item[0],
                promoted_by="human:test",
                promoted_at="2026-07-16T16:20:00+00:00",
            )
            first = verify_validation_sentinels(
                conn, checked_at="2026-07-16T16:30:00+00:00"
            )
            self.assertEqual(first["pass"], 1)
            audio.write_bytes(audio.read_bytes() + b"drift")
            second = verify_validation_sentinels(
                conn, checked_at="2026-07-16T16:40:00+00:00"
            )
            self.assertEqual(second["drift"], 1)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_validation_sentinel_checks WHERE sentinel_id=?",
                    (sentinel_id,),
                ).fetchone()[0],
                2,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_validation_sentinel_checks SET status='pass'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_validation_sentinels SET expected_media_sha256=? WHERE sentinel_id=?",
                    ("0" * 64, sentinel_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM commons_validation_sentinels WHERE sentinel_id=?",
                    (sentinel_id,),
                )
            conn.close()


class ValidationAutomationTest(unittest.TestCase):
    def test_ready_frame_enqueues_and_runs_one_weekly_cpu_job(self):
        from commons_lab.factory import FactoryConfig, enqueue_cycle, run_jobs
        from commons_lab.jobs import JOB_ENERGY_CLASS

        self.assertEqual(JOB_ENERGY_CLASS["weekly_validation_packet"], "scheduled_cpu")
        self.assertEqual(JOB_ENERGY_CLASS["validation_sentinel_check"], "scheduled_cpu")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            populate_validation_frame(conn)
            config = FactoryConfig(
                field_db_path=root / "missing-field.sqlite3",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
            )
            now = datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
            first = enqueue_cycle(conn, config=config, now=now)
            job_types = {
                row[0] for row in conn.execute("SELECT job_type FROM commons_jobs")
            }
            self.assertIn("weekly_validation_packet", job_types)
            outcomes = run_jobs(
                conn,
                config=config,
                worker_id="cpu:test",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=10,
                clock=lambda: now,
            )
            validation = [
                outcome for outcome in outcomes
                if outcome.job_type == "weekly_validation_packet"
            ]
            self.assertEqual(len(validation), 1)
            self.assertEqual(validation[0].state, "success")
            result = validation[0].result
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["item_count"], 24)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_validation_packets").fetchone()[0],
                1,
            )
            replay = enqueue_cycle(conn, config=config, now=now)
            self.assertEqual(replay.created, 0)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_jobs WHERE job_type='weekly_validation_packet'"
                ).fetchone()[0],
                1,
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
