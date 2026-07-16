"""Strict local path resolution for evidence sources."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a configured evidence path crosses a symbolic link."""


def resolve_no_symlinks(
    path: str | Path,
    *,
    require_file: bool = False,
    require_dir: bool = False,
) -> Path:
    """Resolve an existing path only after rejecting symlinks in every component."""
    if require_file and require_dir:
        raise ValueError("a path cannot be required to be both a file and a directory")
    expanded = Path(path).expanduser()
    raw = Path(os.path.abspath(expanded))
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise UnsafePathError(f"evidence path contains symlink: {current}")
    try:
        resolved = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(raw) from exc
    if require_file and not resolved.is_file():
        raise ValueError(f"evidence path is not a regular file: {resolved}")
    if require_dir and not resolved.is_dir():
        raise ValueError(f"evidence path is not a regular directory: {resolved}")
    return resolved


def read_bytes_no_symlinks(path: str | Path) -> bytes:
    """Read a regular file through descriptor-relative no-follow traversal."""
    raw = Path(os.path.abspath(Path(path).expanduser()))
    parts = raw.parts[1:]
    if not parts:
        raise ValueError(f"evidence path is not a regular file: {raw}")
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required_flags):
        raise RuntimeError("descriptor-safe evidence reads require POSIX no-follow support")
    common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    current_fd = os.open(raw.anchor, common_flags | os.O_DIRECTORY)
    try:
        for index, part in enumerate(parts):
            flags = common_flags | os.O_NOFOLLOW
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        mode = os.fstat(current_fd).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"evidence path is not a regular file: {raw}")
        blocks: list[bytes] = []
        while True:
            block = os.read(current_fd, 1024 * 1024)
            if not block:
                return b"".join(blocks)
            blocks.append(block)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePathError(f"evidence path contains symlink: {raw}") from exc
        raise
    finally:
        os.close(current_fd)
