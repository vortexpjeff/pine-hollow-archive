import fcntl
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.automation import (
    QualityResult,
    finish_run,
    metrics_from_rgb,
    record_quality_measurements,
    start_run,
)
from commons_lab.ingest import ingest_media, register_deployment, register_sensor
from commons_lab.pipeline import capture_window_frame
from commons_lab.schema import migrate


class CommonsAutomationTest(unittest.TestCase):
    def make_event(self, root: Path):
        conn = sqlite3.connect(root / "archive.db")
        migrate(conn)
        register_sensor(
            conn,
            sensor_id="camera",
            name="Camera",
            sensor_type="rgb_camera",
        )
        register_deployment(
            conn,
            deployment_id="view",
            sensor_id="camera",
            site_id="private-site",
            purpose="automation test",
        )
        media = root / "frame.jpg"
        media.write_bytes(b"frame")
        result = ingest_media(
            conn,
            path=media,
            event_type="fixed_camera_frame",
            source="window_camera",
            site_id="private-site",
            deployment_id="view",
            captured_at="2026-07-14T12:00:00-04:00",
            timezone="America/New_York",
            media_type="image",
            privacy_level="private",
        )
        return conn, result

    def test_small_rgb_quality_metrics_are_transparent(self):
        # black, white, green, and a mid-gray pixel
        rgb = bytes(
            [
                0,
                0,
                0,
                255,
                255,
                255,
                0,
                255,
                0,
                128,
                128,
                128,
            ]
        )
        result = metrics_from_rgb(rgb, width=2, height=2)

        self.assertAlmostEqual(result.dark_fraction, 0.25)
        self.assertAlmostEqual(result.bright_fraction, 0.25)
        self.assertGreater(result.green_chromatic_coordinate, 0.4)
        self.assertGreater(result.edge_energy, 0.0)
        self.assertEqual(result.quality_state, "accepted")

    def test_dark_frame_is_degraded_not_deleted(self):
        result = metrics_from_rgb(bytes([0, 0, 0] * 16), width=4, height=4)
        self.assertEqual(result.quality_state, "degraded")
        self.assertEqual(result.dark_fraction, 1.0)

    def test_quality_measurements_are_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            conn, event = self.make_event(Path(td))
            quality = QualityResult(
                mean_luma=0.5,
                bright_fraction=0.1,
                dark_fraction=0.05,
                green_chromatic_coordinate=0.36,
                excess_green=0.08,
                edge_energy=0.12,
                quality_state="accepted",
            )
            for _ in range(2):
                record_quality_measurements(
                    conn,
                    event_id=event.event_id,
                    sensor_id="camera",
                    observed_at="2026-07-14T12:00:00-04:00",
                    quality=quality,
                )

            rows = conn.execute(
                "SELECT phenomenon, quality_flag FROM commons_measurements "
                "WHERE event_id=? ORDER BY phenomenon",
                (event.event_id,),
            ).fetchall()
            self.assertEqual(len(rows), 7)
            self.assertTrue(all(flag == "accepted" for _, flag in rows))
            conn.close()

    def test_shared_pipeline_lock_skips_all_capture_entrypoints(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lock_path = root / "camera.lock"
            with lock_path.open("w") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                outcome = capture_window_frame(
                    db_path=root / "archive.db",
                    data_root=root / "private",
                    trigger_type="test",
                    lock_path=lock_path,
                )
            self.assertEqual(outcome.status, "skipped")
            self.assertEqual(outcome.reason, "capture already running")
            self.assertIsNone(outcome.run_id)
            self.assertFalse((root / "archive.db").exists())

    def test_disk_guard_records_skip_without_camera_capture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outcome = capture_window_frame(
                db_path=root / "archive.db",
                data_root=root / "private",
                trigger_type="test",
                min_free_bytes=10**30,
            )
            self.assertEqual(outcome.status, "skipped")
            self.assertIsNone(outcome.event_id)
            conn = sqlite3.connect(root / "archive.db")
            self.assertEqual(
                conn.execute("SELECT status, error FROM commons_runs").fetchone(),
                ("skipped", "minimum free-space guard"),
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM commons_events").fetchone()[0], 0)
            conn.close()

    def test_run_ledger_records_success_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite3.connect(Path(td) / "archive.db")
            migrate(conn)
            first = start_run(
                conn,
                pipeline="window_camera_capture",
                started_at="2026-07-14T12:00:00-04:00",
                metadata={"trigger": "test"},
            )
            finish_run(
                conn,
                run_id=first,
                status="success",
                completed_at="2026-07-14T12:00:03-04:00",
            )
            second = start_run(
                conn,
                pipeline="window_camera_capture",
                started_at="2026-07-14T12:30:00-04:00",
            )
            finish_run(
                conn,
                run_id=second,
                status="failed",
                completed_at="2026-07-14T12:30:01-04:00",
                error="camera busy",
            )

            rows = conn.execute(
                "SELECT status, error FROM commons_runs ORDER BY started_at"
            ).fetchall()
            self.assertEqual(rows, [("success", None), ("failed", "camera busy")])
            conn.close()


if __name__ == "__main__":
    unittest.main()
