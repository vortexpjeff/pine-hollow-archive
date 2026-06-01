#!/usr/bin/env python3
"""Audit Pine Hollow archive labels before retrain.

This is deliberately conservative. It does not decide truth; it blocks only
clear label-contract violations and warns on likely cleanup work.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from schema_hardening import has_column, training_eligibility_sql

ARCHIVE_ROOT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_ROOT / "archive.db"
TAG_MAP_PATH = ARCHIVE_ROOT / "tag_map.json"

ACOUSTIC_CLASSES = {
    "background",
    "cicada_drone",
    "cricket_katydid",
    "frog",
    "grasshopper",
    "bee",
    "dog",
    "chicken",
    "human_voice",
    "mechanical",
    "wind_rain",
    "bird_song",
    "not_chicken",
}
TARGET_CLASSES = ACOUSTIC_CLASSES - {"background", "wind_rain", "mechanical", "human_voice"}
TRAINING_STATUSES = {"confirmed", "corrected"}


@dataclass
class Issue:
    level: str  # BLOCK | WARN
    clip_id: int | None
    message: str


@dataclass
class AuditResult:
    issues: list[Issue]

    @property
    def block_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "BLOCK")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "WARN")

    @property
    def ok(self) -> bool:
        return self.block_count == 0


def is_species_label(label: str) -> bool:
    label = (label or "").strip()
    if not label:
        return False
    if label.lower() in ACOUSTIC_CLASSES:
        return False
    parts = label.replace("_", " ").split()
    return len(parts) >= 2 and parts[0][:1].isalpha()


def load_species_to_tag(tag_map_path: Path | None = TAG_MAP_PATH) -> dict[str, str]:
    if not tag_map_path or not Path(tag_map_path).exists():
        return {}
    data = json.loads(Path(tag_map_path).read_text())
    out: dict[str, str] = {}
    for tag_name, info in data.get("tags", {}).items():
        for species in info.get("perch_labels", []):
            out[species] = tag_name
            out[species.replace(" ", "_")] = tag_name
    return out


def derive_tags(tags: list[str], species_to_tag: dict[str, str]) -> list[str]:
    out = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            out.append(tag); seen.add(tag)
        derived = species_to_tag.get(tag) or species_to_tag.get(tag.replace("_", " "))
        if derived and derived not in seen:
            out.append(derived); seen.add(derived)
    return out


def parse_human_tags(raw: str | None, human_label: str | None) -> tuple[list[str], str | None]:
    if raw:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            return [], f"invalid human_tags JSON: {exc}"
        if not isinstance(parsed, list):
            return [], "human_tags is not a JSON list"
        return [str(t).strip() for t in parsed if str(t).strip()], None
    if human_label:
        return [t.strip() for t in human_label.split(",") if t.strip()], None
    return [], None


def audit_database(db_path: Path = DB_PATH, tag_map_path: Path | None = TAG_MAP_PATH) -> AuditResult:
    species_to_tag = load_species_to_tag(tag_map_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    has_label_certainty = has_column(conn, "clips", "label_certainty")
    has_review_source = has_column(conn, "clips", "review_source")
    select_cols = ["id", "source", "source_label", "review_status", "human_label", "human_tags", "model_pred"]
    if has_label_certainty:
        select_cols.append("label_certainty")
    if has_review_source:
        select_cols.append("review_source")
    rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM clips").fetchall()
    eligible_ids = set()
    if has_label_certainty and has_review_source:
        eligible_ids = {
            r[0] for r in conn.execute(f"SELECT id FROM clips WHERE {training_eligibility_sql()}")
        }
    conn.close()

    issues: list[Issue] = []
    for r in rows:
        clip_id = r["id"]
        status = r["review_status"]
        tags, err = parse_human_tags(r["human_tags"], r["human_label"])

        if err and status in TRAINING_STATUSES:
            issues.append(Issue("BLOCK", clip_id, err))
            continue

        if status in TRAINING_STATUSES and not tags:
            issues.append(Issue("BLOCK", clip_id, "training-eligible clip has no human_tags/human_label"))
            continue

        low_tags = {t.lower() for t in tags}
        if "background" in low_tags and any(t in TARGET_CLASSES for t in low_tags if t != "background"):
            issues.append(Issue("BLOCK", clip_id, "background mixed with target labels"))

        model_pred = (r["model_pred"] or "").strip().lower()
        human_label = (r["human_label"] or "").strip().lower()
        if status in TRAINING_STATUSES and model_pred and human_label and model_pred == human_label:
            issues.append(Issue("WARN", clip_id, "human label exactly mirrors model_pred; confirm this was human-audited"))

        if has_label_certainty and status in TRAINING_STATUSES:
            certainty = (r["label_certainty"] or "").strip().lower()
            if certainty in {"possible", "unsure"}:
                issues.append(Issue("BLOCK", clip_id, f"certainty '{certainty}' is not training-eligible"))
            elif certainty not in {"certain", "probable"}:
                issues.append(Issue("BLOCK", clip_id, "training-eligible status lacks certain/probable label_certainty"))

        if has_review_source and status in TRAINING_STATUSES:
            review_source = (r["review_source"] or "").strip()
            if review_source == "batch_auto_accept":
                issues.append(Issue("BLOCK", clip_id, "batch auto label is not training-eligible"))

        if has_label_certainty and has_review_source and status in TRAINING_STATUSES and clip_id not in eligible_ids:
            issues.append(Issue("WARN", clip_id, "confirmed/corrected row is excluded by training eligibility gate"))

        derived = derive_tags(tags, species_to_tag)
        missing = sorted(set(derived) - set(tags))
        if missing and any(is_species_label(t) for t in tags):
            issues.append(Issue("WARN", clip_id, f"missing derived class tag(s): {', '.join(missing)}"))

    return AuditResult(issues)


def print_result(result: AuditResult) -> None:
    print(f"Label audit: {result.block_count} BLOCK, {result.warn_count} WARN")
    for issue in result.issues:
        prefix = f"{issue.level}"
        if issue.clip_id is not None:
            prefix += f" clip={issue.clip_id}"
        print(f"{prefix}: {issue.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Pine Hollow archive labels")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--tag-map", type=Path, default=TAG_MAP_PATH)
    parser.add_argument("--warn-only", action="store_true", help="Return 0 even with BLOCK issues")
    args = parser.parse_args()
    result = audit_database(args.db, args.tag_map)
    print_result(result)
    return 0 if result.ok or args.warn_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
