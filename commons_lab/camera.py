"""Windows DirectShow bridge for the Pine Hollow window camera."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

DEFAULT_DEVICE = "EMEET SmartCam Nova 4K"
DEFAULT_FFMPEG = Path(
    "/mnt/c/Users/Jeffrey/AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"
)


def windows_path(path: Path) -> str:
    result = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def capture_frame(
    output_path: str | Path,
    *,
    device: str = DEFAULT_DEVICE,
    ffmpeg: str | Path = DEFAULT_FFMPEG,
    rotate_180: bool = True,
) -> Path:
    """Capture one normalized JPEG through Windows DirectShow."""
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite finalized evidence: {output}")
    partial = output.with_name(
        f"{output.stem}.{uuid.uuid4().hex}.partial{output.suffix or '.jpg'}"
    )
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "dshow",
        "-rtbufsize",
        "128M",
        "-i",
        f"video={device}",
        # Let the webcam's auto-exposure and white balance settle before the
        # retained frame. The first DirectShow frame is often blown out.
        "-ss",
        "2",
        "-frames:v",
        "1",
    ]
    if rotate_180:
        command += ["-vf", "hflip,vflip"]
    command += ["-q:v", "2", "-update", "1", "-y", windows_path(partial)]
    try:
        subprocess.run(command, check=True, timeout=30)
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError(f"camera capture produced no image: {partial}")
        # Hard-link creation is atomic and fails if the finalized path exists.
        # Because partial and final live in one directory, this never crosses a
        # filesystem boundary and cannot overwrite prior evidence.
        os.link(partial, output)
        partial.unlink()
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return output
