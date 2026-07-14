import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.camera import capture_frame


class CameraCaptureTest(unittest.TestCase):
    def test_capture_is_atomically_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "frame.jpg"

            def fake_run(command, **kwargs):
                self.assertTrue(str(command[-1]).endswith(".partial.jpg"))
                Path(command[-1]).write_bytes(b"complete-jpeg")
                return subprocess.CompletedProcess(command, 0)

            with patch("commons_lab.camera.windows_path", side_effect=lambda path: str(path)):
                with patch("commons_lab.camera.subprocess.run", side_effect=fake_run):
                    result = capture_frame(output)

            self.assertEqual(result, output.resolve())
            self.assertEqual(output.read_bytes(), b"complete-jpeg")
            self.assertEqual(list(output.parent.glob("*.partial.jpg")), [])

    def test_existing_finalized_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "frame.jpg"
            output.write_bytes(b"original-evidence")

            with patch("commons_lab.camera.subprocess.run") as run:
                with self.assertRaises(FileExistsError):
                    capture_frame(output)

            run.assert_not_called()
            self.assertEqual(output.read_bytes(), b"original-evidence")

    def test_failed_capture_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "frame.jpg"

            def fake_run(command, **kwargs):
                self.assertTrue(str(command[-1]).endswith(".partial.jpg"))
                Path(command[-1]).write_bytes(b"incomplete")
                raise subprocess.CalledProcessError(1, command)

            with patch("commons_lab.camera.windows_path", side_effect=lambda path: str(path)):
                with patch("commons_lab.camera.subprocess.run", side_effect=fake_run):
                    with self.assertRaises(subprocess.CalledProcessError):
                        capture_frame(output)

            self.assertFalse(output.exists())
            self.assertEqual(list(output.parent.glob("*.partial.jpg")), [])


if __name__ == "__main__":
    unittest.main()
