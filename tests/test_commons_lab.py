import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.ingest import (
    ingest_media,
    register_deployment,
    register_sensor,
    register_site,
)
from commons_lab.schema import SCHEMA_VERSION, migrate


class CommonsLabSchemaTest(unittest.TestCase):
    def make_legacy_db(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE clips (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO clips VALUES (1, 'legacy.wav', 'birdnet')")
        conn.commit()
        return conn

    def test_migration_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "archive.db"
            conn = self.make_legacy_db(db_path)

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
                    "commons_schema_versions",
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
                    "commons_legacy_links",
                    "commons_runs",
                }.issubset(tables)
            )
            self.assertEqual(
                conn.execute("SELECT filename, source FROM clips WHERE id=1").fetchone(),
                ("legacy.wav", "birdnet"),
            )
            self.assertEqual(
                conn.execute(
                    "SELECT MAX(version) FROM commons_schema_versions"
                ).fetchone()[0],
                SCHEMA_VERSION,
            )
            conn.close()

    def test_camera_ingest_records_private_provenance_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "archive.db"
            media_path = root / "window.jpg"
            media_path.write_bytes(b"private-camera-frame")
            conn = sqlite3.connect(db_path)
            migrate(conn)

            register_sensor(
                conn,
                sensor_id="emeet-window-camera",
                name="Window Camera",
                sensor_type="rgb_camera",
                manufacturer="EMEET",
                model="SmartCam Nova 4K",
                host="Athena-Windows",
                privacy_default="private",
            )
            register_deployment(
                conn,
                deployment_id="window-view-v1",
                sensor_id="emeet-window-camera",
                site_id="pine-hollow-private",
                purpose="fixed window environmental observation",
                orientation={"raw_orientation": "upside_down", "rotation_applied_deg": 180},
                privacy_default="private",
            )

            first = ingest_media(
                conn,
                path=media_path,
                event_type="fixed_camera_frame",
                source="window_camera",
                site_id="pine-hollow-private",
                deployment_id="window-view-v1",
                captured_at="2026-07-14T12:00:00-04:00",
                timezone="America/New_York",
                media_type="image",
                mime_type="image/jpeg",
                privacy_level="private",
                transform={"rotation_deg": 180, "normalized_orientation": True},
            )
            legacy_key = "|".join(
                [
                    "window-view-v1",
                    "2026-07-14T12:00:00-04:00",
                    "fixed_camera_frame",
                    first.sha256,
                ]
            )
            conn.execute(
                "UPDATE commons_events SET idempotency_key=? WHERE event_id=?",
                (legacy_key, first.event_id),
            )
            conn.commit()
            second = ingest_media(
                conn,
                path=media_path,
                event_type="fixed_camera_frame",
                source="window_camera",
                site_id="pine-hollow-private",
                deployment_id="window-view-v1",
                captured_at="2026-07-14T12:00:00-04:00",
                timezone="America/New_York",
                media_type="image",
                mime_type="image/jpeg",
                privacy_level="private",
                transform={"rotation_deg": 180, "normalized_orientation": True},
            )

            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual(first.media_id, second.media_id)
            self.assertEqual(first.sha256, second.sha256)
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            event = conn.execute(
                "SELECT privacy_level, review_state, publication_state "
                "FROM commons_events WHERE event_id=?",
                (first.event_id,),
            ).fetchone()
            self.assertEqual(event, ("private", "unreviewed", "blocked"))
            media = conn.execute(
                "SELECT sha256, byte_size, transform_json, privacy_level "
                "FROM commons_media WHERE media_id=?",
                (first.media_id,),
            ).fetchone()
            self.assertEqual(len(media[0]), 64)
            self.assertEqual(media[1], len(b"private-camera-frame"))
            self.assertEqual(json.loads(media[2])["rotation_deg"], 180)
            self.assertEqual(media[3], "private")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_events").fetchone()[0], 1
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM commons_media").fetchone()[0], 1
            )
            conn.close()
    def test_concurrent_ingest_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "archive.db"
            media_path = root / "frame.jpg"
            media_path.write_bytes(b"one-physical-frame")
            setup = sqlite3.connect(db_path)
            migrate(setup)
            register_sensor(
                setup,
                sensor_id="camera",
                name="Camera",
                sensor_type="rgb_camera",
            )
            register_deployment(
                setup,
                deployment_id="view",
                sensor_id="camera",
                site_id="private-site",
                purpose="concurrency test",
            )
            setup.close()
            barrier = threading.Barrier(8)

            def worker():
                conn = sqlite3.connect(db_path, timeout=10)
                barrier.wait()
                try:
                    return ingest_media(
                        conn,
                        path=media_path,
                        event_type="fixed_camera_frame",
                        source="window_camera",
                        site_id="private-site",
                        deployment_id="view",
                        captured_at="2026-07-14T12:00:00-04:00",
                        timezone="America/New_York",
                        media_type="image",
                        privacy_level="private",
                    )
                finally:
                    conn.close()

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: worker(), range(8)))

            check = sqlite3.connect(db_path)
            self.assertEqual(check.execute("SELECT COUNT(*) FROM commons_events").fetchone()[0], 1)
            self.assertEqual(check.execute("SELECT COUNT(*) FROM commons_media").fetchone()[0], 1)
            self.assertEqual(len({result.event_id for result in results}), 1)
            self.assertEqual(len({result.media_id for result in results}), 1)
            self.assertEqual(sum(result.created for result in results), 1)
            check.close()

    def test_deployment_site_mismatch_is_rejected_by_api_and_database(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            register_site(conn, site_id="site-a", name="Site A")
            register_site(conn, site_id="site-b", name="Site B")
            register_sensor(
                conn,
                sensor_id="camera",
                name="Camera",
                sensor_type="rgb_camera",
            )
            register_deployment(
                conn,
                deployment_id="view-a",
                sensor_id="camera",
                site_id="site-a",
                purpose="site A view",
            )
            media = root / "frame.jpg"
            media.write_bytes(b"site-bound-evidence")

            with self.assertRaises(ValueError):
                ingest_media(
                    conn,
                    path=media,
                    event_type="fixed_camera_frame",
                    source="window_camera",
                    site_id="site-b",
                    deployment_id="view-a",
                    captured_at="2026-07-14T12:00:00-04:00",
                    timezone="America/New_York",
                    media_type="image",
                )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM commons_events").fetchone()[0], 0)

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO commons_events(
                        event_id, idempotency_key, event_type, started_at,
                        timezone, site_id, deployment_id, source
                    ) VALUES (
                        'bad-event', 'bad-key', 'fixed_camera_frame',
                        '2026-07-14T12:00:00-04:00', 'America/New_York',
                        'site-b', 'view-a', 'direct-sql'
                    )
                    """
                )
            conn.close()

    def test_undeployed_evidence_is_namespaced_by_site_and_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            register_site(conn, site_id="site-a", name="Site A", privacy_level="private")
            register_site(conn, site_id="site-b", name="Site B", privacy_level="private")
            media = root / "shared.jpg"
            media.write_bytes(b"identical-evidence")
            common = {
                "conn": conn,
                "path": media,
                "event_type": "manual_field_image",
                "deployment_id": None,
                "captured_at": "2026-07-14T12:00:00-04:00",
                "timezone": "America/New_York",
                "media_type": "image",
                "privacy_level": "private",
            }

            first = ingest_media(site_id="site-a", source="field_app", **common)
            second = ingest_media(site_id="site-b", source="field_app", **common)
            third = ingest_media(site_id="site-a", source="manual_import", **common)

            self.assertEqual(conn.execute("SELECT COUNT(*) FROM commons_events").fetchone()[0], 3)
            self.assertEqual(len({first.event_id, second.event_id, third.event_id}), 3)
            self.assertEqual(len({first.media_id, second.media_id, third.media_id}), 3)
            conn.close()

    def test_private_event_cannot_be_marked_publicly_approved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            register_sensor(
                conn,
                sensor_id="camera",
                name="Camera",
                sensor_type="rgb_camera",
                privacy_default="private",
            )
            register_deployment(
                conn,
                deployment_id="private-view",
                sensor_id="camera",
                site_id="private-site",
                purpose="private test",
                privacy_default="private",
            )
            media = root / "frame.jpg"
            media.write_bytes(b"frame")
            result = ingest_media(
                conn,
                path=media,
                event_type="fixed_camera_frame",
                source="window_camera",
                site_id="private-site",
                deployment_id="private-view",
                captured_at="2026-07-14T12:00:00-04:00",
                timezone="America/New_York",
                media_type="image",
                privacy_level="private",
            )

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_events SET publication_state='approved' WHERE event_id=?",
                    (result.event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO commons_publications(
                        publication_id, event_id, surface, state
                    ) VALUES ('pub_private', ?, 'website', 'published')
                    """,
                    (result.event_id,),
                )
            conn.close()
    def test_published_record_must_be_withdrawn_before_event_is_downgraded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = sqlite3.connect(root / "archive.db")
            migrate(conn)
            register_sensor(
                conn,
                sensor_id="public-sensor",
                name="Public Sensor",
                sensor_type="weather",
                privacy_default="public",
            )
            register_deployment(
                conn,
                deployment_id="public-deployment",
                sensor_id="public-sensor",
                site_id="public-site",
                purpose="public aggregate test",
                privacy_default="public",
            )
            media = root / "public.json"
            media.write_text("{}")
            result = ingest_media(
                conn,
                path=media,
                event_type="public_test",
                source="test",
                site_id="public-site",
                deployment_id="public-deployment",
                captured_at="2026-07-14T12:00:00-04:00",
                timezone="America/New_York",
                media_type="data",
                privacy_level="public",
            )
            conn.execute(
                "UPDATE commons_events SET publication_state='approved' WHERE event_id=?",
                (result.event_id,),
            )
            conn.execute(
                """
                INSERT INTO commons_publications(
                    publication_id, event_id, surface, state
                ) VALUES ('pub_public', ?, 'test', 'published')
                """,
                (result.event_id,),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE commons_events SET publication_state='blocked' WHERE event_id=?",
                    (result.event_id,),
                )
            conn.execute(
                "UPDATE commons_publications SET state='withdrawn' WHERE publication_id='pub_public'"
            )
            conn.execute(
                "UPDATE commons_events SET publication_state='blocked' WHERE event_id=?",
                (result.event_id,),
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
