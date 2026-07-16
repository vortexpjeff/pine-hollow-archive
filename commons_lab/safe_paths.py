"""Strict local path resolution for evidence sources."""

from __future__ import annotations

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
