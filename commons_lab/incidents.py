"""Immutable provenance import for field-listener incident ledgers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jobs import append_research_record
from .safe_paths import UnsafePathError, resolve_no_symlinks


class IncidentImportError(ValueError):
    """Raised when an incident ledger violates its preservation contract."""


@dataclass(frozen=True)
class IncidentImportSummary:
    discovered: int
    copied: int
    records_appended: int


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_document(path: Path, payload: bytes) -> int:
    if len(payload) > 5 * 1024 * 1024:
        raise IncidentImportError(f"incident ledger exceeds 5 MiB: {path.name}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise IncidentImportError(
                    f"duplicate JSON key in incident ledger {path.name}: {key}"
                )
            result[key] = value
        return result

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IncidentImportError(f"incident ledger is not UTF-8: {path.name}") from exc
    if path.suffix == ".jsonl":
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            for line in lines:
                json.loads(line, object_pairs_hook=reject_duplicates)
        except json.JSONDecodeError as exc:
            raise IncidentImportError(f"invalid JSONL incident ledger: {path.name}") from exc
        return len(lines)
    try:
        json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise IncidentImportError(f"invalid JSON incident ledger: {path.name}") from exc
    return 1


def _promote(payload: bytes, *, destination: Path, data_root: Path) -> bool:
    if data_root.is_symlink():
        raise IncidentImportError(f"incident data root is a symlink: {data_root}")
    resolved_root = data_root.resolve()
    try:
        relative = destination.parent.relative_to(resolved_root)
    except ValueError as exc:
        raise IncidentImportError("incident destination escapes private data root") from exc
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise IncidentImportError(
                f"incident destination ancestor is a symlink: {current}"
            )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = _sha256(payload)
    if destination.exists():
        if not destination.is_file() or _sha256(destination.read_bytes()) != digest:
            raise IncidentImportError(f"incident destination conflicts: {destination}")
        return False
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def import_field_incident_ledgers(
    conn: sqlite3.Connection,
    *,
    incident_dir: Path | str,
    data_root: Path | str,
) -> IncidentImportSummary:
    """Preserve exact incident ledgers without inventing missing media events."""
    try:
        source_root = resolve_no_symlinks(incident_dir, require_dir=True)
    except (UnsafePathError, FileNotFoundError, ValueError) as exc:
        raise IncidentImportError(f"invalid incident source: {exc}") from exc
    sources = sorted(
        path
        for path in source_root.iterdir()
        if path.suffix in {".json", ".jsonl"} and path.is_file() and not path.is_symlink()
    )
    raw_root = Path(data_root).expanduser().absolute()
    copied = appended = 0
    for source in sources:
        try:
            source = resolve_no_symlinks(source, require_file=True)
        except (UnsafePathError, FileNotFoundError, ValueError) as exc:
            raise IncidentImportError(f"invalid incident ledger path: {exc}") from exc
        payload = source.read_bytes()
        record_count = _validate_document(source, payload)
        digest = _sha256(payload)
        destination = raw_root.resolve() / "field_incidents" / f"{digest}{source.suffix}"
        copied += int(_promote(payload, destination=destination, data_root=raw_root))
        before = conn.execute(
            "SELECT COUNT(*) FROM commons_research_records"
        ).fetchone()[0]
        append_research_record(
            conn,
            record_type="incident",
            title=f"Field listener incident ledger: {source.name}",
            body=(
                "Preserved an exact field-listener incident ledger version. "
                "This record documents unavailable or lost source evidence and does not "
                "create an acoustic event or imply that missing media was recovered."
            ),
            recorded_at=datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc),
            sources=[
                {
                    "kind": "private_archived_incident_ledger",
                    "relative_path": str(destination.relative_to(raw_root.resolve())),
                    "sha256": digest,
                }
            ],
            author="Pine Hollow data factory",
            metadata={
                "source_filename": source.name,
                "record_count": record_count,
                "sha256": digest,
                "missing_media_recovered": False,
            },
        )
        after = conn.execute(
            "SELECT COUNT(*) FROM commons_research_records"
        ).fetchone()[0]
        appended += int(after > before)
    return IncidentImportSummary(len(sources), copied, appended)
