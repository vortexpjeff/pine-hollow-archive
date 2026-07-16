import hashlib
import io
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import wave
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.schema import migrate
from test_factory_validation import populate_validation_frame


class ValidationDeskTest(unittest.TestCase):
    def _fixture(self, root: Path):
        from commons_lab.validation import generate_weekly_packet

        db_path = root / "archive.db"
        conn = sqlite3.connect(db_path)
        migrate(conn)
        populate_validation_frame(conn)
        audio = root / "field.wav"
        with wave.open(str(audio), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(32000)
            target.writeframes(b"\x01\x00" * 480000)
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        conn.execute(
            "UPDATE commons_media SET path=?,sha256=?,byte_size=?",
            (str(audio), digest, audio.stat().st_size),
        )
        conn.commit()
        packet = generate_weekly_packet(
            conn, now=datetime(2026, 7, 16, 16, tzinfo=timezone.utc)
        )
        item_id = conn.execute(
            """
            SELECT item_id FROM commons_validation_items
            WHERE packet_id=? ORDER BY position LIMIT 1
            """,
            (packet.packet_id,),
        ).fetchone()[0]
        return conn, db_path, packet.packet_id, item_id, audio

    def test_pending_page_is_blind_audio_is_verified_and_reveal_is_post_review(self):
        from commons_lab.validation import record_validation_review
        from scripts.run_validation_desk import (
            render_review_page,
            render_reveal_page,
            verified_item_audio,
        )

        with tempfile.TemporaryDirectory() as td:
            conn, _, packet_id, item_id, audio = self._fixture(Path(td))
            metadata = json_loads(
                conn.execute(
                    "SELECT sampling_metadata_json FROM commons_validation_items WHERE item_id=?",
                    (item_id,),
                ).fetchone()[0]
            )
            page = render_review_page(conn, item_id=item_id, csrf_token="secret")
            self.assertIn("Exact five-second window", page)
            self.assertIn("Full 15-second context", page)
            with patch(
                "scripts.run_validation_desk.PROTOCOL_VERSION",
                "weekly_blinded_future",
            ):
                with self.assertRaisesRegex(ValueError, "inactive validation protocol"):
                    render_review_page(conn, item_id=item_id, csrf_token="secret")
                with self.assertRaisesRegex(ValueError, "inactive validation protocol"):
                    verified_item_audio(conn, item_id=item_id, scope="window")
            self.assertNotIn(metadata["selection"], page)
            self.assertNotIn("model_positive", page)
            self.assertNotIn("boundary", page)
            for context in metadata["model_context"].values():
                self.assertNotIn(context["model_slug"], page)
                self.assertNotIn(str(context["score"]), page)
                self.assertNotIn(str(context["threshold"]), page)
            window_payload = verified_item_audio(conn, item_id=item_id, scope="window")
            with wave.open(io.BytesIO(window_payload), "rb") as sliced:
                self.assertEqual(sliced.getnframes(), 160000)
            self.assertEqual(
                verified_item_audio(conn, item_id=item_id, scope="full"),
                audio.read_bytes(),
            )
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("validation audio reopened a pathname"),
            ):
                descriptor_payload = verified_item_audio(
                    conn, item_id=item_id, scope="window"
                )
            self.assertEqual(descriptor_payload, window_payload)
            symlink_parent = Path(td) / "linked-parent"
            symlink_parent.symlink_to(Path(td), target_is_directory=True)
            conn.execute(
                "UPDATE commons_media SET path=? WHERE path=?",
                (str(symlink_parent / audio.name), str(audio)),
            )
            conn.commit()
            with self.assertRaisesRegex(ValueError, "symlinked"):
                verified_item_audio(conn, item_id=item_id, scope="window")
            with self.assertRaisesRegex(ValueError, "not yet reviewed"):
                render_reveal_page(conn, item_id=item_id)

            record_validation_review(
                conn,
                item_id=item_id,
                reviewer="human:test",
                insect_presence="present",
                chicken_presence="absent",
                signal_quality="clear",
                reviewed_at="2026-07-16T16:10:00+00:00",
            )
            reveal = render_reveal_page(conn, item_id=item_id)
            self.assertIn(metadata["selection"], reveal)
            self.assertIn(metadata["model_context"]["insect_present"]["model_slug"], reveal)
            self.assertIn(packet_id, reveal)
            conn.close()

    def test_loopback_server_health_and_csrf_gate(self):
        from scripts.run_validation_desk import create_server

        with tempfile.TemporaryDirectory() as td:
            conn, db_path, _, item_id, _ = self._fixture(Path(td))
            conn.close()
            server = create_server(
                db_path=db_path,
                host="127.0.0.1",
                port=0,
                csrf_token="known-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                health = json_loads(urllib.request.urlopen(base + "/healthz").read())
                self.assertEqual(health["status"], "ok")
                review_url = base + "/review?" + urllib.parse.urlencode({"item_id": item_id})
                page = urllib.request.urlopen(review_url).read().decode("utf-8")
                self.assertIn("Blinded field validation", page)
                bad_body = urllib.parse.urlencode(
                    {
                        "csrf_token": "wrong",
                        "item_id": item_id,
                        "reviewer": "human:test",
                        "insect_presence": "present",
                        "chicken_presence": "absent",
                        "signal_quality": "clear",
                    }
                ).encode()
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(
                        urllib.request.Request(base + "/review", data=bad_body, method="POST")
                    )
                self.assertEqual(caught.exception.code, 403)
                check = sqlite3.connect(db_path)
                self.assertEqual(
                    check.execute("SELECT COUNT(*) FROM commons_validation_reviews").fetchone()[0],
                    0,
                )
                check.close()

                good_body = urllib.parse.urlencode(
                    {
                        "csrf_token": "known-token",
                        "item_id": item_id,
                        "reviewer": "human:test",
                        "insect_presence": "present",
                        "chicken_presence": "absent",
                        "signal_quality": "clear",
                        "confounder": "bird_overlap",
                        "notes": "test review",
                    }
                ).encode()
                response = urllib.request.urlopen(
                    urllib.request.Request(base + "/review", data=good_body, method="POST")
                )
                self.assertEqual(response.status, 200)
                check = sqlite3.connect(db_path)
                self.assertEqual(
                    check.execute("SELECT COUNT(*) FROM commons_validation_reviews").fetchone()[0],
                    1,
                )
                check.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_request_logging_redacts_audio_bearer_token(self):
        from scripts.run_validation_desk import ValidationDeskHandler

        handler = object.__new__(ValidationDeskHandler)
        captured = io.StringIO()
        with redirect_stderr(captured):
            handler.log_message(
                '"%s" %s %s',
                "GET /audio?item_id=vit_0123456789abcdef01234567&token=secret-token HTTP/1.1",
                "200",
                "123",
            )
        self.assertNotIn("secret-token", captured.getvalue())
        self.assertIn("token=[REDACTED]", captured.getvalue())


def json_loads(value):
    import json

    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


if __name__ == "__main__":
    unittest.main()
