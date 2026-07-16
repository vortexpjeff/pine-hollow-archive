import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.schema import SCHEMA_VERSION, migrate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_field_fixture(root: Path, *, score: float = 0.995) -> dict[str, object]:
    from commons_lab.acoustic import bundle_id_from_directory

    bundle = root / "bundle"
    bundle.mkdir()
    model = {
        "bundle_schema_version": 1,
        "class_name": "chicken_vocalization_present",
        "event_threshold": 0.9999,
        "feature_dimension": 1536,
        "model_slug": "chickennet-test",
        "perch_model_tree_sha256": "a" * 64,
        "preprocess_recipe_id": "ffmpeg-mono-32khz-f32le-5s-nonoverlap-v1",
        "score_semantics": "uncalibrated_case_control_ranking_score",
        "runtime_event_config": {"sample_rate": 32000, "merge_gap_samples": 0},
    }
    (bundle / "model.json").write_text(
        json.dumps(model, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    (bundle / "weights.npz").write_bytes(b"fixture-weights")
    checksums = {
        name: _sha256(bundle / name) for name in ("model.json", "weights.npz")
    }
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)),
        encoding="utf-8",
    )
    bundle_id = bundle_id_from_directory(bundle).bundle_id

    review = root / "review"
    events = review / "events"
    events.mkdir(parents=True)
    placeholder = events / "placeholder.wav"
    placeholder.write_bytes(b"RIFF" + b"field-audio" * 128)
    recording_id = _sha256(placeholder)
    audio = placeholder.rename(events / f"{recording_id}.wav")
    source_event_id = hashlib.sha256(b"field-source-event").hexdigest()
    windows = [
        (0, 160000, 0.25, -1.1),
        (160000, 320000, score, 5.3),
        (320000, 480000, 0.1, -2.2),
    ]
    sidecar = {
        "recording_id": recording_id,
        "review_state": "unreviewed",
        "bundles": [
            {
                "bundle_id": bundle_id,
                "class_name": model["class_name"],
                "events": [source_event_id],
                "scores": [item[2] for item in windows],
            }
        ],
    }
    audio.with_suffix(".json").write_text(
        json.dumps(sidecar, sort_keys=True), encoding="utf-8"
    )

    field_db = root / "field.sqlite3"
    source = sqlite3.connect(field_db)
    source.executescript(
        """
        CREATE TABLE recordings(
            recording_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL,
            source_bytes INTEGER NOT NULL, captured_at TEXT NOT NULL,
            source_name TEXT, committed_at TEXT, metadata_json TEXT NOT NULL
        );
        CREATE TABLE scores(
            recording_id TEXT NOT NULL, bundle_id TEXT NOT NULL,
            start_sample INTEGER NOT NULL, end_sample INTEGER NOT NULL,
            score REAL NOT NULL, raw_score REAL NOT NULL,
            PRIMARY KEY(recording_id, bundle_id, start_sample)
        );
        CREATE TABLE events(
            event_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL,
            bundle_id TEXT NOT NULL, start_sample INTEGER NOT NULL,
            end_sample INTEGER NOT NULL, score REAL NOT NULL,
            raw_score REAL NOT NULL, window_count INTEGER NOT NULL,
            review_state TEXT NOT NULL, review_label TEXT
        );
        """
    )
    metadata = {
        "recording_id": recording_id,
        "source_sha256": recording_id,
        "source_bytes": audio.stat().st_size,
        "captured_at": "2026-07-16T12:00:00+00:00",
        "source_name": "2026-07-16-birdnet-08:00:00.wav",
        "producer_sequence": 42,
    }
    source.execute(
        "INSERT INTO recordings VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        (
            recording_id,
            recording_id,
            audio.stat().st_size,
            metadata["captured_at"],
            metadata["source_name"],
            json.dumps(metadata, sort_keys=True),
        ),
    )
    source.executemany(
        "INSERT INTO scores VALUES (?, ?, ?, ?, ?, ?)",
        [(recording_id, bundle_id, *window) for window in windows],
    )
    source.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'unreviewed', NULL)",
        (source_event_id, recording_id, bundle_id, 160000, 320000, score, 5.3),
    )
    source.commit()
    source.close()
    return {
        "audio": audio,
        "bundle": bundle,
        "bundle_id": bundle_id,
        "class_name": model["class_name"],
        "field_db": field_db,
        "recording_id": recording_id,
        "review": review,
        "source_event_id": source_event_id,
    }


class DataFactorySchemaTest(unittest.TestCase):
    def test_phase_1_to_3_schema_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "archive.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE clips(id INTEGER PRIMARY KEY, filename TEXT NOT NULL)"
            )
            conn.execute("INSERT INTO clips VALUES (1, 'legacy.wav')")
            conn.commit()

            migrate(conn)
            migrate(conn)

            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {
                    "commons_acoustic_windows",
                    "commons_event_links",
                    "commons_review_queue",
                    "commons_jobs",
                    "commons_job_transitions",
                    "commons_research_records",
                }.issubset(tables)
            )
            self.assertGreaterEqual(SCHEMA_VERSION, 4)
            self.assertEqual(
                conn.execute("SELECT filename FROM clips WHERE id=1").fetchone()[0],
                "legacy.wav",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT MAX(version) FROM commons_schema_versions"
                ).fetchone()[0],
                SCHEMA_VERSION,
            )
            conn.close()

    def test_systemd_unit_limits_writes_to_runtime_artifacts(self):
        unit = (
            ROOT / "deploy/systemd/pine-hollow-data-factory.service"
        ).read_text(encoding="utf-8")
        repository = "/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive"
        self.assertIn(f"ReadOnlyPaths={repository}", unit)
        self.assertNotIn(f"ReadWritePaths={repository} ", unit)
        self.assertIn(f"{repository}/private/commons_lab", unit)
        self.assertNotIn(f"{repository}/archive.db-wal", unit)
        self.assertNotIn(f"{repository}/archive.db-shm", unit)

    def test_cli_config_preserves_source_symlinks_for_strict_validation(self):
        import argparse

        from scripts.run_data_factory import make_config

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real_source = root / "real-source"
            real_source.mkdir()
            linked_source = root / "linked-source"
            linked_source.symlink_to(real_source, target_is_directory=True)
            args = argparse.Namespace(
                field_db=linked_source / "events.sqlite3",
                review_dir=linked_source,
                bundle=[linked_source],
                observatory=linked_source / "observatory.json",
                data_root=linked_source,
                camera_tolerance_seconds=1200,
                observatory_tolerance_seconds=1800,
                nvidia_smi=Path("/usr/bin/nvidia-smi"),
            )
            config = make_config(args)
            self.assertEqual(config.review_dir, linked_source.absolute())
            self.assertTrue(config.review_dir.is_symlink())
            with self.assertRaisesRegex(ValueError, "symlink"):
                from commons_lab.factory import _field_watermark

                _field_watermark(config)

    def test_append_only_factory_records_reject_update_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            conn.execute(
                """
                INSERT INTO commons_research_records(
                    record_id, recorded_at, record_type, title, body,
                    sources_json, metadata_json
                ) VALUES ('rec-1', '2026-07-16T12:00:00Z', 'decision',
                          'Keep evidence immutable', 'Decision body', '[]', '{}')
                """
            )
            conn.commit()

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_research_records SET title='changed' "
                    "WHERE record_id='rec-1'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM commons_research_records WHERE record_id='rec-1'"
                )
            conn.close()


class AcousticImportTest(unittest.TestCase):
    def test_import_is_strict_private_exact_and_idempotent(self):
        from commons_lab.acoustic import import_field_evidence

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)

            first = import_field_evidence(
                conn,
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=[fixture["bundle"]],
            )
            second = import_field_evidence(
                conn,
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=[fixture["bundle"]],
            )

            self.assertEqual(first.imported, 1)
            self.assertEqual(second.imported, 0)
            self.assertEqual(second.existing, 1)
            event = conn.execute(
                "SELECT event_id, privacy_level, review_state, publication_state "
                "FROM commons_events WHERE event_type='acoustic_recording'"
            ).fetchone()
            self.assertEqual(event[1:], ("private", "unreviewed", "blocked"))
            media = conn.execute(
                "SELECT media_id, sha256, path FROM commons_media WHERE event_id=?",
                (event[0],),
            ).fetchone()
            self.assertEqual(media[1], fixture["recording_id"])
            self.assertEqual(Path(media[2]), fixture["audio"].resolve())
            windows = conn.execute(
                """
                SELECT start_sample, end_sample, sample_rate, score, threshold,
                       crosses_threshold, source_event_id
                FROM commons_acoustic_windows ORDER BY start_sample
                """
            ).fetchall()
            self.assertEqual(len(windows), 3)
            self.assertEqual(windows[1][0:3], (160000, 320000, 32000))
            self.assertAlmostEqual(windows[1][3], 0.995)
            self.assertAlmostEqual(windows[1][4], 0.9999)
            self.assertEqual(windows[1][5], 0)
            self.assertEqual(windows[1][6], fixture["source_event_id"])
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_assertions "
                    "WHERE source_type='model' AND event_id=?",
                    (event[0],),
                ).fetchone()[0],
                1,
            )
            conn.close()

    def test_hash_mismatch_fails_before_acoustic_event_is_created(self):
        from commons_lab.acoustic import FieldEvidenceError, import_field_evidence

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            fixture["audio"].write_bytes(fixture["audio"].read_bytes() + b"tampered")
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)

            with self.assertRaises(FieldEvidenceError):
                import_field_evidence(
                    conn,
                    field_db_path=fixture["field_db"],
                    review_dir=fixture["review"],
                    bundle_dirs=[fixture["bundle"]],
                )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_events "
                    "WHERE event_type='acoustic_recording'"
                ).fetchone()[0],
                0,
            )
            conn.close()

    def test_replay_rejects_changed_score_under_existing_window_identity(self):
        from commons_lab.acoustic import FieldEvidenceError, import_field_evidence

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root, score=0.995)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            import_field_evidence(
                conn,
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=[fixture["bundle"]],
            )

            source = sqlite3.connect(fixture["field_db"])
            source.execute(
                "UPDATE scores SET score=0.996 WHERE start_sample=160000"
            )
            source.execute("UPDATE events SET score=0.996")
            source.commit()
            source.close()
            sidecar_path = Path(fixture["audio"]).with_suffix(".json")
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["bundles"][0]["scores"][1] = 0.996
            sidecar_path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")

            with self.assertRaisesRegex(FieldEvidenceError, "archived acoustic window"):
                import_field_evidence(
                    conn,
                    field_db_path=fixture["field_db"],
                    review_dir=fixture["review"],
                    bundle_dirs=[fixture["bundle"]],
                )
            self.assertAlmostEqual(
                conn.execute(
                    "SELECT score FROM commons_acoustic_windows WHERE start_sample=160000"
                ).fetchone()[0],
                0.995,
            )
            conn.close()

    def test_recording_import_rolls_back_media_when_window_stage_fails(self):
        from unittest.mock import patch

        from commons_lab.acoustic import import_field_evidence

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            with patch(
                "commons_lab.acoustic._source_event_for_window",
                side_effect=RuntimeError("injected window-stage failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    import_field_evidence(
                        conn,
                        field_db_path=fixture["field_db"],
                        review_dir=fixture["review"],
                        bundle_dirs=[fixture["bundle"]],
                    )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_events "
                    "WHERE event_type='acoustic_recording'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_media").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_acoustic_windows").fetchone()[0],
                0,
            )
            conn.close()

    def test_human_review_is_append_only_and_queue_is_score_stratified(self):
        from commons_lab.acoustic import (
            import_field_evidence,
            populate_calibration_queue,
            record_human_acoustic_review,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            import_field_evidence(
                conn,
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=[fixture["bundle"]],
            )
            event_id, media_id = conn.execute(
                """
                SELECT e.event_id, m.media_id FROM commons_events e
                JOIN commons_media m ON m.event_id=e.event_id
                WHERE e.event_type='acoustic_recording'
                """
            ).fetchone()
            queued = populate_calibration_queue(
                conn,
                bundle_id=fixture["bundle_id"],
                class_name=fixture["class_name"],
                per_band=10,
            )
            queued_again = populate_calibration_queue(
                conn,
                bundle_id=fixture["bundle_id"],
                class_name=fixture["class_name"],
                per_band=10,
            )
            self.assertEqual((queued, queued_again), (1, 0))
            self.assertEqual(
                conn.execute("SELECT score_band FROM commons_review_queue").fetchone()[0],
                "0.99_to_0.999",
            )

            with self.assertRaisesRegex(ValueError, "class does not match"):
                record_human_acoustic_review(
                    conn,
                    event_id=event_id,
                    media_id=media_id,
                    bundle_id=fixture["bundle_id"],
                    class_name="invented_class",
                    present=True,
                    certainty="confirmed",
                    reviewer="human:test",
                    start_sample=160000,
                    end_sample=320000,
                    reviewed_at="2026-07-16T13:00:00Z",
                )
            with self.assertRaisesRegex(ValueError, "timezone"):
                record_human_acoustic_review(
                    conn,
                    event_id=event_id,
                    media_id=media_id,
                    bundle_id=fixture["bundle_id"],
                    class_name=fixture["class_name"],
                    present=True,
                    certainty="confirmed",
                    reviewer="human:test",
                    start_sample=160000,
                    end_sample=320000,
                    reviewed_at="2026-07-16T13:00:00",
                )

            first = record_human_acoustic_review(
                conn,
                event_id=event_id,
                media_id=media_id,
                bundle_id=fixture["bundle_id"],
                class_name=fixture["class_name"],
                present=True,
                certainty="confirmed",
                reviewer="human:test",
                start_sample=160000,
                end_sample=320000,
                reviewed_at="2026-07-16T13:00:00Z",
            )
            with self.assertRaisesRegex(ValueError, "same review lineage"):
                record_human_acoustic_review(
                    conn,
                    event_id=event_id,
                    media_id=media_id,
                    bundle_id=fixture["bundle_id"],
                    class_name=fixture["class_name"],
                    present=True,
                    certainty="confirmed",
                    reviewer="human:test",
                    start_sample=0,
                    end_sample=320000,
                    reviewed_at="2026-07-16T13:01:00Z",
                    supersedes_assertion_id=first,
                )
            second = record_human_acoustic_review(
                conn,
                event_id=event_id,
                media_id=media_id,
                bundle_id=fixture["bundle_id"],
                class_name=fixture["class_name"],
                present=False,
                certainty="confirmed",
                reviewer="human:test",
                start_sample=160000,
                end_sample=320000,
                reviewed_at="2026-07-16T13:05:00Z",
                supersedes_assertion_id=first,
            )
            self.assertNotEqual(first, second)
            assertions = conn.execute(
                "SELECT assertion_id, value_json FROM commons_assertions "
                "WHERE source_type='human' ORDER BY created_at, assertion_id"
            ).fetchall()
            self.assertEqual(len(assertions), 2)
            self.assertEqual(json.loads(assertions[1][1])["supersedes_assertion_id"], first)
            self.assertEqual(
                conn.execute(
                    "SELECT review_state FROM commons_events WHERE event_id=?",
                    (event_id,),
                ).fetchone()[0],
                "reviewed",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_assertions SET authority='candidate' "
                    "WHERE assertion_id=?",
                    (first,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM commons_assertions WHERE assertion_id=?",
                    (first,),
                )
            conn.close()


class TemporalContextTest(unittest.TestCase):
    def _event(
        self,
        conn: sqlite3.Connection,
        root: Path,
        *,
        name: str,
        event_type: str,
        captured_at: str,
        site_id: str = "pine-hollow-private",
    ) -> str:
        from commons_lab.ingest import ingest_media, register_site

        register_site(conn, site_id=site_id, name=site_id, privacy_level="private")
        media = root / f"{name}.dat"
        media.write_bytes(name.encode("utf-8"))
        return ingest_media(
            conn,
            path=media,
            event_type=event_type,
            source="test",
            site_id=site_id,
            deployment_id=None,
            captured_at=captured_at,
            timezone="UTC",
            media_type="data",
            privacy_level="private",
        ).event_id

    def test_nearest_context_is_site_bound_toleranced_noncausal_and_idempotent(self):
        from commons_lab.context import link_nearest_context

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            acoustic = self._event(
                conn,
                root,
                name="acoustic",
                event_type="acoustic_recording",
                captured_at="2026-07-16T12:00:00Z",
            )
            nearest = self._event(
                conn,
                root,
                name="camera-nearest",
                event_type="fixed_camera_frame",
                captured_at="2026-07-16T11:59:30+00:00",
            )
            self._event(
                conn,
                root,
                name="camera-farther",
                event_type="fixed_camera_frame",
                captured_at="2026-07-16T12:02:00Z",
            )
            self._event(
                conn,
                root,
                name="camera-other-site",
                event_type="fixed_camera_frame",
                captured_at="2026-07-16T12:00:01Z",
                site_id="other-private-site",
            )

            first = link_nearest_context(
                conn,
                source_event_type="acoustic_recording",
                target_event_type="fixed_camera_frame",
                relation="nearest_visual_context",
                tolerance_seconds=180,
            )
            second = link_nearest_context(
                conn,
                source_event_type="acoustic_recording",
                target_event_type="fixed_camera_frame",
                relation="nearest_visual_context",
                tolerance_seconds=180,
            )
            self.assertEqual((first, second), (1, 0))
            link = conn.execute(
                """
                SELECT source_event_id, target_event_id, offset_seconds,
                       relation, method, metadata_json
                FROM commons_event_links
                """
            ).fetchone()
            self.assertEqual(link[0:2], (acoustic, nearest))
            self.assertEqual(link[2], -30.0)
            self.assertEqual(link[3], "nearest_visual_context")
            self.assertEqual(link[4], "nearest_aware_timestamp_v1")
            self.assertFalse(json.loads(link[5])["causal_claim"])
            closer = self._event(
                conn,
                root,
                name="camera-new-closer",
                event_type="fixed_camera_frame",
                captured_at="2026-07-16T12:00:10Z",
            )
            third = link_nearest_context(
                conn,
                source_event_type="acoustic_recording",
                target_event_type="fixed_camera_frame",
                relation="nearest_visual_context",
                tolerance_seconds=180,
            )
            self.assertEqual(third, 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_event_links").fetchone()[0],
                2,
            )
            current = conn.execute(
                """
                SELECT target_event_id, offset_seconds
                FROM commons_current_event_links
                WHERE source_event_id=? AND relation='nearest_visual_context'
                """,
                (acoustic,),
            ).fetchone()
            self.assertEqual(current, (closer, 10.0))
            conn.close()

    def test_observatory_snapshot_is_copied_immutably_and_replay_safe(self):
        from commons_lab.context import ingest_observatory_snapshot

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            source = root / "observatory.json"
            source.write_text(
                json.dumps(
                    {
                        "updated": "2026-07-16T12:44:52Z",
                        "surface": {"temp_c": 25.1, "humidity_pct": 85},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            original_hash = _sha256(source)
            first = ingest_observatory_snapshot(
                conn, snapshot_path=source, data_root=root / "private"
            )
            second = ingest_observatory_snapshot(
                conn, snapshot_path=source, data_root=root / "private"
            )
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.event_id, second.event_id)
            archived = Path(
                conn.execute(
                    "SELECT path FROM commons_media WHERE media_id=?", (first.media_id,)
                ).fetchone()[0]
            )
            self.assertNotEqual(archived, source.resolve())
            self.assertEqual(_sha256(archived), original_hash)
            source.write_text('{"updated":"later"}', encoding="utf-8")
            self.assertEqual(_sha256(archived), original_hash)
            event = conn.execute(
                "SELECT privacy_level, publication_state FROM commons_events WHERE event_id=?",
                (first.event_id,),
            ).fetchone()
            self.assertEqual(event, ("private", "blocked"))
            conn.close()

    def test_observatory_snapshot_rejects_symlinked_destination_ancestor(self):
        from commons_lab.context import ContextError, ingest_observatory_snapshot

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            source = root / "observatory.json"
            source.write_text(
                json.dumps({"updated": "2026-07-16T12:05:00Z", "temperature": 23}),
                encoding="utf-8",
            )
            data_root = root / "private"
            data_root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (data_root / "observatory_snapshots").symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaisesRegex(ContextError, "symlink"):
                ingest_observatory_snapshot(
                    conn, snapshot_path=source, data_root=data_root
                )
            self.assertEqual(list(outside.iterdir()), [])
            conn.close()

    def test_observatory_snapshot_rejects_symlinked_source(self):
        from commons_lab.context import ContextError, ingest_observatory_snapshot

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            real_source = root / "real-observatory.json"
            real_source.write_text(
                json.dumps({"updated": "2026-07-16T12:05:00Z"}), encoding="utf-8"
            )
            linked_source = root / "observatory.json"
            linked_source.symlink_to(real_source)
            with self.assertRaisesRegex(ContextError, "symlink"):
                ingest_observatory_snapshot(
                    conn, snapshot_path=linked_source, data_root=root / "private"
                )
            conn.close()


class JobLedgerTest(unittest.TestCase):
    def test_enqueue_is_deterministic_and_energy_class_is_allowlisted(self):
        from commons_lab.jobs import enqueue_job

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            first = enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="integrity:2026-07-16",
                parameters={"scope": "archive"},
            )
            second = enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="integrity:2026-07-16",
                parameters={"scope": "archive"},
            )
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.job_id, second.job_id)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_jobs").fetchone()[0], 1
            )
            with self.assertRaises(ValueError):
                enqueue_job(
                    conn,
                    job_type="arbitrary_shell",
                    idempotency_key="unsafe",
                    parameters={"command": "rm -rf /"},
                )
            with self.assertRaises(ValueError):
                enqueue_job(
                    conn,
                    job_type="gpu_environment_probe",
                    idempotency_key="wrong-energy",
                    parameters={},
                    energy_class="scheduled_cpu",
                )
            conn.close()

    def test_lease_excludes_second_worker_and_expiry_is_recoverable(self):
        from commons_lab.jobs import claim_job, enqueue_job

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "archive.db"
            setup = sqlite3.connect(db)
            migrate(setup)
            now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
            enqueue_job(
                setup,
                job_type="sqlite_integrity",
                idempotency_key="lease-test",
                parameters={},
                max_attempts=3,
                now=now,
            )
            setup.close()
            first_conn = sqlite3.connect(db, timeout=10)
            second_conn = sqlite3.connect(db, timeout=10)
            first = claim_job(
                first_conn,
                worker_id="worker-a",
                allowed_energy_classes={"scheduled_cpu"},
                now=now,
                lease_seconds=10,
            )
            blocked = claim_job(
                second_conn,
                worker_id="worker-b",
                allowed_energy_classes={"scheduled_cpu"},
                now=now + timedelta(seconds=5),
                lease_seconds=10,
            )
            recovered = claim_job(
                second_conn,
                worker_id="worker-b",
                allowed_energy_classes={"scheduled_cpu"},
                now=now + timedelta(seconds=11),
                lease_seconds=10,
            )
            self.assertIsNotNone(first)
            self.assertIsNone(blocked)
            self.assertEqual(recovered.job_id, first.job_id)
            self.assertEqual(recovered.attempts, 2)
            transitions = second_conn.execute(
                "SELECT from_state, to_state FROM commons_job_transitions "
                "ORDER BY transitioned_at, rowid"
            ).fetchall()
            self.assertEqual(
                transitions,
                [
                    (None, "queued"),
                    ("queued", "running"),
                    ("running", "queued"),
                    ("queued", "running"),
                ],
            )
            first_conn.close()
            second_conn.close()

    def test_heartbeat_extends_lease_and_expired_owner_cannot_complete(self):
        from commons_lab.jobs import (
            claim_job,
            complete_job,
            enqueue_job,
            heartbeat_job,
        )

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "archive.db"
            conn = sqlite3.connect(db, timeout=10)
            migrate(conn)
            now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
            enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="heartbeat-test",
                parameters={},
                now=now,
            )
            job = claim_job(
                conn,
                worker_id="worker-a",
                allowed_energy_classes={"scheduled_cpu"},
                now=now,
                lease_seconds=10,
            )
            renewed_until = heartbeat_job(
                conn,
                job_id=job.job_id,
                worker_id="worker-a",
                now=now + timedelta(seconds=8),
                lease_seconds=10,
            )
            self.assertEqual(
                renewed_until,
                "2026-07-16T12:00:18.000000+00:00",
            )
            competing = sqlite3.connect(db, timeout=10)
            self.assertIsNone(
                claim_job(
                    competing,
                    worker_id="worker-b",
                    allowed_energy_classes={"scheduled_cpu"},
                    now=now + timedelta(seconds=11),
                )
            )
            complete_job(
                conn,
                job_id=job.job_id,
                worker_id="worker-a",
                result={"ok": True},
                now=now + timedelta(seconds=12),
            )
            competing.close()
            conn.close()

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="expired-completion-test",
                parameters={},
                now=now,
            )
            expired = claim_job(
                conn,
                worker_id="worker-a",
                allowed_energy_classes={"scheduled_cpu"},
                now=now,
                lease_seconds=10,
            )
            with self.assertRaisesRegex(ValueError, "lease has expired"):
                complete_job(
                    conn,
                    job_id=expired.job_id,
                    worker_id="worker-a",
                    result={"ok": True},
                    now=now + timedelta(seconds=11),
                )
            conn.close()

    def test_failure_obeys_retry_cap_and_completion_checks_lease_owner(self):
        from commons_lab.jobs import claim_job, complete_job, enqueue_job, fail_job

        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
            enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="failure-test",
                parameters={},
                max_attempts=1,
                now=now,
            )
            job = claim_job(
                conn,
                worker_id="worker-a",
                allowed_energy_classes={"scheduled_cpu"},
                now=now,
            )
            with self.assertRaises(ValueError):
                complete_job(
                    conn,
                    job_id=job.job_id,
                    worker_id="worker-b",
                    result={"ok": True},
                    now=now,
                )
            terminal = fail_job(
                conn,
                job_id=job.job_id,
                worker_id="worker-a",
                error="fixture failure",
                now=now + timedelta(seconds=1),
            )
            self.assertEqual(terminal, "failed")
            self.assertIsNone(
                claim_job(
                    conn,
                    worker_id="worker-a",
                    allowed_energy_classes={"scheduled_cpu"},
                    now=now + timedelta(seconds=2),
                )
            )
            self.assertEqual(
                conn.execute(
                    "SELECT state, attempts, error FROM commons_jobs"
                ).fetchone(),
                ("failed", 1, "fixture failure"),
            )
            conn.close()


class FactoryIntegrationTest(unittest.TestCase):
    def test_cpu_cycle_is_replay_safe_and_links_imported_context(self):
        from commons_lab.factory import FactoryConfig, enqueue_cycle, run_jobs

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            db = root / "archive.db"
            conn = sqlite3.connect(db)
            migrate(conn)
            TemporalContextTest()._event(
                conn,
                root,
                name="factory-camera",
                event_type="fixed_camera_frame",
                captured_at="2026-07-16T12:00:15Z",
            )
            observatory = root / "observatory.json"
            observatory.write_text(
                json.dumps(
                    {
                        "updated": "2026-07-16T12:05:00Z",
                        "surface": {"temp_c": 25.1},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            config = FactoryConfig(
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=(fixture["bundle"],),
                observatory_path=observatory,
                data_root=root / "private",
                camera_tolerance_seconds=1200,
                observatory_tolerance_seconds=1200,
            )
            now = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            first_enqueued = enqueue_cycle(conn, config=config, now=now)
            Path(fixture["field_db"]).touch()
            second_enqueued = enqueue_cycle(conn, config=config, now=now)
            self.assertEqual(first_enqueued.created, 4)
            self.assertEqual(second_enqueued.created, 0)
            outcomes = run_jobs(
                conn,
                config=config,
                worker_id="cpu-test",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=10,
                clock=lambda: now,
            )
            self.assertEqual(len(outcomes), 4)
            self.assertTrue(all(item.state == "success" for item in outcomes))
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_events WHERE event_type='acoustic_recording'"
                ).fetchone()[0],
                1,
            )
            relations = {
                row[0]
                for row in conn.execute("SELECT relation FROM commons_event_links")
            }
            self.assertEqual(
                relations,
                {"nearest_visual_context", "contemporaneous_environmental_context"},
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_jobs WHERE energy_class='deferrable_gpu'"
                ).fetchone()[0],
                0,
            )
            conn.close()

    def test_gpu_probe_requires_explicit_gpu_worker_and_records_inventory(self):
        from commons_lab.factory import FactoryConfig, run_jobs
        from commons_lab.jobs import enqueue_job

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            fake_smi = root / "nvidia-smi"
            fake_smi.write_text(
                "#!/bin/sh\nprintf 'NVIDIA Test GPU, 24564, 22000, 3, 610.62\\n'\n",
                encoding="utf-8",
            )
            fake_smi.chmod(0o700)
            config = FactoryConfig(
                field_db_path=root / "missing-field.db",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
                nvidia_smi=fake_smi,
            )
            now = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            job = enqueue_job(
                conn,
                job_type="gpu_environment_probe",
                idempotency_key="gpu-probe:test",
                parameters={},
                now=now,
            )
            cpu_outcomes = run_jobs(
                conn,
                config=config,
                worker_id="cpu-test",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=1,
            )
            self.assertEqual(cpu_outcomes, [])
            gpu_outcomes = run_jobs(
                conn,
                config=config,
                worker_id="gpu-test",
                allowed_energy_classes={"deferrable_gpu"},
                max_jobs=1,
                clock=lambda: now,
            )
            self.assertEqual(len(gpu_outcomes), 1)
            self.assertEqual(gpu_outcomes[0].state, "success")
            result = json.loads(
                conn.execute(
                    "SELECT result_json FROM commons_jobs WHERE job_id=?", (job.job_id,)
                ).fetchone()[0]
            )
            self.assertEqual(result["gpus"][0]["name"], "NVIDIA Test GPU")
            self.assertEqual(result["gpus"][0]["memory_free_mib"], 22000)
            conn.close()

    def test_changed_observatory_enqueues_same_cycle_context_join(self):
        from commons_lab.factory import FactoryConfig, enqueue_cycle, run_jobs

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            TemporalContextTest()._event(
                conn,
                root,
                name="acoustic-source",
                event_type="acoustic_recording",
                captured_at="2026-07-16T12:00:00Z",
            )
            observatory = root / "observatory.json"
            observatory.write_text(
                json.dumps({"updated": "2026-07-16T12:00:00Z", "value": 1}),
                encoding="utf-8",
            )
            config = FactoryConfig(
                field_db_path=root / "missing-field.db",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=observatory,
                data_root=root / "private",
            )
            now = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            first = enqueue_cycle(conn, config=config, now=now)
            self.assertEqual(first.created, 3)
            run_jobs(
                conn,
                config=config,
                worker_id="cpu-test",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=10,
                clock=lambda: now,
            )
            settled = enqueue_cycle(
                conn, config=config, now=now + timedelta(minutes=5)
            )
            self.assertEqual(settled.created, 1)
            run_jobs(
                conn,
                config=config,
                worker_id="cpu-test",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=10,
                clock=lambda: now + timedelta(minutes=5),
            )
            observatory.write_text(
                json.dumps({"updated": "2026-07-16T12:10:00Z", "value": 2}),
                encoding="utf-8",
            )
            changed = enqueue_cycle(
                conn, config=config, now=now + timedelta(minutes=10)
            )
            changed_types = {
                row[0]
                for row in conn.execute(
                    "SELECT job_type FROM commons_jobs WHERE state='queued'"
                )
            }
            self.assertEqual(changed.created, 2)
            self.assertEqual(
                changed_types, {"observatory_snapshot", "context_join"}
            )
            conn.close()

    def test_worker_emits_background_heartbeat_during_handler(self):
        import time
        from unittest.mock import patch

        from commons_lab.factory import FactoryConfig, run_jobs
        from commons_lab.jobs import enqueue_job

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db", timeout=30)
            migrate(conn)
            config = FactoryConfig(
                field_db_path=root / "missing-field.db",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
                lease_seconds=2,
                heartbeat_interval_seconds=0.01,
            )
            enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="background-heartbeat-test",
                parameters={},
            )

            def slow_handler(*args, **kwargs):
                time.sleep(0.08)
                return {"ok": True}

            with patch("commons_lab.factory._execute", side_effect=slow_handler):
                outcomes = run_jobs(
                    conn,
                    config=config,
                    worker_id="heartbeat-worker",
                    allowed_energy_classes={"scheduled_cpu"},
                    max_jobs=1,
                )
            self.assertEqual(outcomes[0].state, "success")
            self.assertGreaterEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_job_transitions "
                    "WHERE reason='heartbeat'"
                ).fetchone()[0],
                1,
            )
            conn.close()

    def test_worker_terminal_transition_uses_live_clock_not_cycle_start(self):
        from unittest.mock import Mock, patch

        from commons_lab.factory import FactoryConfig, run_jobs
        from commons_lab.jobs import enqueue_job

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            cycle_start = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            config = FactoryConfig(
                field_db_path=root / "missing-field.db",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
                lease_seconds=1,
                heartbeat_interval_seconds=0.5,
            )
            enqueue_job(
                conn,
                job_type="sqlite_integrity",
                idempotency_key="terminal-live-clock-test",
                parameters={},
                now=cycle_start,
            )
            heartbeat = Mock()
            heartbeat.error = None
            terminal_times = iter(
                [
                    cycle_start,
                    cycle_start + timedelta(seconds=2),
                    cycle_start + timedelta(seconds=2),
                ]
            )
            with (
                patch("commons_lab.factory._LeaseHeartbeat", return_value=heartbeat),
                patch("commons_lab.factory._execute", return_value={"ok": True}),
            ):
                outcomes = run_jobs(
                    conn,
                    config=config,
                    worker_id="expired-worker",
                    allowed_energy_classes={"scheduled_cpu"},
                    max_jobs=1,
                    clock=lambda: next(terminal_times),
                )
            self.assertEqual(outcomes[0].state, "running")
            self.assertIn("lease has expired", outcomes[0].error or "")
            state, completed_at = conn.execute(
                "SELECT state,completed_at FROM commons_jobs"
            ).fetchone()
            self.assertEqual(state, "running")
            self.assertIsNone(completed_at)
            conn.close()

    def test_observatory_gate_and_tolerance_are_part_of_job_contract(self):
        from commons_lab.factory import FactoryConfig, enqueue_cycle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            TemporalContextTest()._event(
                conn,
                root,
                name="old-acoustic",
                event_type="acoustic_recording",
                captured_at="2026-07-16T10:00:00Z",
            )
            observatory = root / "observatory.json"
            observatory.write_text(
                json.dumps({"updated": "2026-07-16T12:00:00Z", "value": 1}),
                encoding="utf-8",
            )
            narrow = FactoryConfig(
                field_db_path=root / "missing-field.db",
                review_dir=root / "missing-review",
                bundle_dirs=(),
                observatory_path=observatory,
                data_root=root / "private",
                observatory_tolerance_seconds=1800,
            )
            now = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            first = enqueue_cycle(conn, config=narrow, now=now)
            queued_types = {
                row[0] for row in conn.execute("SELECT job_type FROM commons_jobs")
            }
            self.assertEqual(first.created, 2)
            self.assertNotIn("observatory_snapshot", queued_types)
            self.assertTrue(
                any("outside acoustic tolerance" in item for item in first.omitted)
            )

            wider = FactoryConfig(
                field_db_path=narrow.field_db_path,
                review_dir=narrow.review_dir,
                bundle_dirs=(),
                observatory_path=observatory,
                data_root=narrow.data_root,
                observatory_tolerance_seconds=3 * 3600,
            )
            adjusted = enqueue_cycle(
                conn, config=wider, now=now + timedelta(minutes=1)
            )
            newly_queued = {
                row[0]
                for row in conn.execute(
                    "SELECT job_type FROM commons_jobs WHERE state='queued'"
                )
            }
            self.assertEqual(adjusted.created, 2)
            self.assertIn("observatory_snapshot", newly_queued)
            self.assertIn("context_join", newly_queued)
            conn.close()

    def test_field_watermark_tracks_retained_ledger_and_audio_mutation(self):
        from commons_lab.factory import FactoryConfig, _field_watermark

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            config = FactoryConfig(
                field_db_path=fixture["field_db"],
                review_dir=fixture["review"],
                bundle_dirs=(Path(fixture["bundle"]),),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
            )
            original = _field_watermark(config)
            source = sqlite3.connect(fixture["field_db"])
            source.execute(
                "UPDATE scores SET score=score + 0.000001 "
                "WHERE recording_id=? AND bundle_id=? AND start_sample=160000",
                (fixture["recording_id"], fixture["bundle_id"]),
            )
            source.commit()
            source.close()
            ledger_changed = _field_watermark(config)
            self.assertNotEqual(original, ledger_changed)

            audio = Path(fixture["audio"])
            before = audio.stat()
            payload = bytearray(audio.read_bytes())
            payload[-1] ^= 1
            audio.write_bytes(payload)
            os.utime(audio, ns=(before.st_atime_ns, before.st_mtime_ns))
            audio_changed = _field_watermark(config)
            self.assertNotEqual(ledger_changed, audio_changed)

    def test_field_watermark_rejects_symlinked_retained_wav(self):
        from commons_lab.factory import FactoryConfig, _field_watermark

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            audio = Path(fixture["audio"])
            real_audio = root / "redirected.wav"
            audio.rename(real_audio)
            audio.symlink_to(real_audio)
            config = FactoryConfig(
                field_db_path=Path(fixture["field_db"]),
                review_dir=Path(fixture["review"]),
                bundle_dirs=(Path(fixture["bundle"]),),
                observatory_path=root / "missing.json",
                data_root=root / "private",
            )
            with self.assertRaisesRegex(ValueError, "symlink"):
                _field_watermark(config)

    def test_import_rejects_symlinked_bundle_and_generic_media(self):
        from commons_lab.acoustic import FieldEvidenceError, import_field_evidence
        from commons_lab.ingest import ingest_media, register_site

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = make_field_fixture(root)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            bundle = Path(fixture["bundle"])
            real_bundle = root / "real-bundle"
            bundle.rename(real_bundle)
            bundle.symlink_to(real_bundle, target_is_directory=True)
            with self.assertRaisesRegex(FieldEvidenceError, "symlink"):
                import_field_evidence(
                    conn,
                    field_db_path=Path(fixture["field_db"]),
                    review_dir=Path(fixture["review"]),
                    bundle_dirs=[bundle],
                )

            register_site(conn, site_id="site-test", name="Test")
            real_media = root / "real-media.bin"
            real_media.write_bytes(b"evidence")
            linked_media = root / "linked-media.bin"
            linked_media.symlink_to(real_media)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ingest_media(
                    conn,
                    path=linked_media,
                    event_type="test",
                    source="test",
                    site_id="site-test",
                    deployment_id=None,
                    captured_at="2026-07-16T12:00:00+00:00",
                    timezone="UTC",
                    media_type="binary",
                )
            conn.close()

    def test_incident_ledgers_are_preserved_without_fake_media_events(self):
        from commons_lab.factory import FactoryConfig, enqueue_cycle, run_jobs

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "field-source"
            incidents = source_root / "incidents"
            incidents.mkdir(parents=True)
            (incidents / "losses.jsonl").write_text(
                '{"sha256":"abc","lost":true}\n'
                '{"sha256":"def","lost":true}\n',
                encoding="utf-8",
            )
            (incidents / "summary.json").write_text(
                json.dumps({"lost_count": 2}), encoding="utf-8"
            )
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            config = FactoryConfig(
                field_db_path=source_root / "events.sqlite3",
                review_dir=source_root / "review",
                bundle_dirs=(),
                observatory_path=root / "missing-observatory.json",
                data_root=root / "private",
            )
            now = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
            first = enqueue_cycle(conn, config=config, now=now)
            self.assertEqual(first.created, 3)
            outcomes = run_jobs(
                conn,
                config=config,
                worker_id="incident-worker",
                allowed_energy_classes={"scheduled_cpu"},
                max_jobs=10,
                clock=lambda: now,
            )
            incident_result = next(
                outcome.result
                for outcome in outcomes
                if outcome.job_type == "field_incident_import"
            )
            self.assertEqual(
                incident_result,
                {"discovered": 2, "copied": 2, "records_appended": 2},
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM commons_research_records "
                    "WHERE record_type='incident'"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_media").fetchone()[0], 0
            )
            self.assertEqual(
                len(list((root / "private" / "field_incidents").iterdir())), 2
            )
            replay = enqueue_cycle(
                conn, config=config, now=now + timedelta(minutes=10)
            )
            self.assertEqual(replay.created, 0)
            conn.close()


if __name__ == "__main__":
    unittest.main()
