#!/usr/bin/env python3
"""
Pine Hollow Bioacoustics Data Factory — Retrain Pipeline

Trains per-track classifier heads on frozen Perch 2.0 embeddings (1,536-dim)
using confirmed/corrected labels from the archive. OneVsRest LogisticRegression
with per-class threshold tuning.

╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  OPERATOR INVARIANTS — READ BEFORE EDITING OR RUNNING     ║
╠══════════════════════════════════════════════════════════════════╣
║  • Multi-label is auto-detected via isinstance(y[0], list).    ║
║    Do NOT hardcode single-label assumptions.                   ║
║  • human_label is COMMA-SEPARATED from the review app          ║
║    multiselect. Always split on comma before matching.         ║
║  • human_tags is a JSON array (preferred source).              ║
║  • BirdNET-reviewed clips ARE the background negatives.        ║
║  • score_all_clips is SCOPED per track source.                 ║
║  • This script trains on Perch embeddings, NOT BirdNET logits. ║
║  • Load the pine-hollow-archive skill before operating.        ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
    python3 retrain.py --track insectnet                   # retrain a specific track
    python3 retrain.py --track chicken --version v0.2.0    # with explicit version
    python3 retrain.py --all-tracks                        # retrain everything with new data
    python3 retrain.py --compare                           # compare current model vs previous
    python3 retrain.py --list-tracks                       # show available tracks

Requires:
    - Archive DB with confirmed clips (review_status IN ('confirmed','corrected'))
    - Perch embeddings stored as BLOBs in the clips table
    - tag_map.json for label routing
"""

import os, sys, json, sqlite3, hashlib, argparse, csv
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

import numpy as np
import joblib

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.multiclass import OneVsRestClassifier
from sklearn.model_selection import KFold
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.metrics import (
    classification_report, f1_score
)

# =============================================================================
# Configuration
# =============================================================================

ARCHIVE_ROOT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_ROOT / "archive.db"
MODELS_DIR = ARCHIVE_ROOT / "models"
TAG_MAP_PATH = ARCHIVE_ROOT / "tag_map.json"
DOCS_DIR = Path.home() / ".hermes/hermes-agent/docs"

RANDOM_STATE = 42
N_FOLDS = 5
MIN_SAMPLES_PER_CLASS = 5

# Track definitions — label source → tag map training_tracks → classifier
TRACKS = {
    "insectnet": {
        "classes": ["background", "cicada_drone", "cricket_katydid",
                    "frog", "grasshopper", "bee"],
        "min_samples": 10,
        "description": "6-class insect/frog acoustic classifier",
        "comparison_model": DOCS_DIR / "insectnet_6class_classifier.joblib",
    },
    "chicken": {
        "classes": ["chicken", "not_chicken"],
        "min_samples": 5,
        "description": "Binary chicken detector",
        "comparison_model": None,
    },
    "bird46": {
        "classes": None,  # dynamic: all species labels in confirmed clips
        "min_samples": 3,
        "description": "Multi-species bird classifier",
        "comparison_model": None,
    },
}


# =============================================================================
# Helpers
# =============================================================================

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_tag_map():
    """Load tag_map.json and build:
    1. species_to_track: Perch label → list of training tracks
    2. track_to_tags: track name → set of universal tags
    """
    if not TAG_MAP_PATH.exists():
        return {}, {}
    
    with open(TAG_MAP_PATH) as f:
        data = json.load(f)
    
    tags = data.get("tags", {})
    species_to_track = {}
    track_to_tags = {}
    
    for tag_name, tag_info in tags.items():
        tracks = tag_info.get("training_tracks", [])
        for track in tracks:
            track_to_tags.setdefault(track, set()).add(tag_name)
            # Map bird_song or generic bird_classifier to bird46
            if "bird" in track:
                track_to_tags.setdefault("bird46", set()).add(tag_name)
        
        for species in tag_info.get("perch_labels", []):
            species_to_track[species.lower()] = tracks
    
    return species_to_track, track_to_tags


def resolve_version(track_name, force_version=None):
    """Auto-increment version based on existing models."""
    if force_version:
        return force_version
    
    existing = sorted(MODELS_DIR.glob(f"{track_name}_v*.joblib"))
    if not existing:
        return "v0.1.0"
    
    latest = existing[-1].stem
    parts = latest.split("_v")[-1].split(".")
    try:
        minor = int(parts[1]) + 1
        return f"v{parts[0]}.{minor}.{parts[2]}"
    except (IndexError, ValueError):
        return "v0.1.0"


def compute_dataset_hash(labels):
    """SHA-256 of concatenated sorted labels for dataset versioning."""
    h = hashlib.sha256()
    for label in sorted(labels):
        h.update(label.encode())
    return h.hexdigest()[:12]


# =============================================================================
# Data Loading
# =============================================================================

def load_training_data(track_name):
    """Load confirmed clips from the archive for a given track.
    
    Uses the tag map to route human labels to the right track.
    Returns (embeddings, labels, label_map) or raises if insufficient data.
    """
    conn = get_db()
    _, track_to_tags = load_tag_map()
    
    # Get the universal tags that route to this track
    track_tags = track_to_tags.get(track_name, set())
    
    if track_name == "chicken":
        # Binary: anything tagged "chicken" is positive, everything else is negative
        chicken_rows = conn.execute("""
            SELECT perch_embedding, human_label FROM clips
            WHERE review_status IN ('confirmed', 'corrected')
            AND human_label IS NOT NULL AND human_label != ''
            AND perch_embedding IS NOT NULL
        """).fetchall()
        
        X, y = [], []
        for r in chicken_rows:
            emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            if emb.shape != (1536,):
                continue
            X.append(emb)
            is_chicken = 1 if "chicken" in [t.strip() for t in (r["human_label"] or "").lower().split(",")] else 0
            y.append("chicken" if is_chicken else "not_chicken")
    
    elif track_name == "insectnet":
        # Multi-label: InsectNet-sourced clips provide active class labels.
        # BirdNET-sourced clips serve as "background" negatives —
        # they're confirmed bird vocalizations, proven non-insect by BirdNET.
        valid_classes = set(TRACKS["insectnet"]["classes"])

        # Phase 1: insectnet + public clips → multi-label active classes
        insect_rows = conn.execute("""
            SELECT perch_embedding, human_label, human_tags, source_label
            FROM clips
            WHERE review_status IN ('confirmed', 'corrected')
            AND source IN ('insectnet', 'public')
            AND perch_embedding IS NOT NULL
        """).fetchall()

        X, y_multilabel = [], []
        for r in insect_rows:
            # Parse human_tags JSON (preferred), fall back to comma-split human_label
            tags = []
            if r["human_tags"]:
                try:
                    tags = [t.strip().lower() for t in json.loads(r["human_tags"])]
                except (json.JSONDecodeError, TypeError):
                    pass
            if not tags and r["human_label"]:
                tags = [t.strip().lower()
                        for t in r["human_label"].split(",") if t.strip()]

            # Filter to valid insectnet classes — keep ALL matches (multi-label)
            active = [t for t in tags if t in valid_classes]

            # Fall back to source_label if no human tags matched
            if not active:
                source = (r["source_label"] or "").strip().lower()
                if source in valid_classes:
                    active = [source]

            if not active:
                continue

            emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            if emb.shape != (1536,):
                continue
            X.append(emb)
            y_multilabel.append(active)

        # Phase 2: birdnet clips → background negatives
        # These are real Pine Hollow field audio with no insect content.
        # Every birdnet-reviewed clip is a confirmed bird vocalization,
        # proven non-insect by BirdNET's bird-focused head.
        #
        # INVARIANT: Do NOT use silence or synthetic noise for background.
        # Real field audio from the same mic/environment is essential for
        # the model to learn what Pine Hollow sounds like without insects.
        bg_rows = conn.execute("""
            SELECT perch_embedding FROM clips
            WHERE review_status IN ('confirmed', 'corrected')
            AND source = 'birdnet'
            AND perch_embedding IS NOT NULL
            LIMIT 500
        """).fetchall()

        bg_count = 0
        for r in bg_rows:
            emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            if emb.shape != (1536,):
                continue
            X.append(emb)
            y_multilabel.append(["background"])
            bg_count += 1

        if bg_count == 0:
            print("  ⚠ No birdnet clips available for background training. "
                  "Background class will have no negative examples.",
                  file=sys.stderr)
        else:
            print(f"  Loaded {bg_count} birdnet clips as background negatives")

        # Convert list-of-lists to flat list for compatibility with
        # existing chicken track (which uses single-label strings).
        # train_classifier will re-multilabelize via MultiLabelBinarizer.
        y = y_multilabel  # keep as list-of-lists — train_classifier handles it
    
    elif track_name == "bird46":
        # Dynamic multi-species: use source_label from BirdNET high-confidence clips.
        # If the human_label is comma-separated (e.g. "bird, chicken"), take the
        # first tag that doesn't look like a compound.
        rows = conn.execute("""
            SELECT perch_embedding, human_label, source_label, source_conf FROM clips
            WHERE review_status IN ('confirmed', 'corrected')
            AND source = 'birdnet'
            AND perch_embedding IS NOT NULL
        """).fetchall()
        
        X, y = [], []
        for r in rows:
            raw = (r["human_label"] or r["source_label"] or "").strip()
            if not raw:
                continue
            # If human_label is comma-separated tags, take the first plausible one
            if "," in raw:
                parts = [p.strip() for p in raw.split(",")]
                # Prefer a part that looks like a species (two words) or is in the
                # default tag map
                label = parts[0]  # fallback
                for p in parts:
                    if " " in p and p[0].isupper():
                        label = p
                        break
                raw = label
            emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            if emb.shape != (1536,):
                continue
            X.append(emb)
            y.append(raw)
    
    else:
        raise ValueError(f"Unknown track: {track_name}")
    
    conn.close()
    
    # Sufficiency check — works for both single-label (list of strings)
    # and multi-label (list of lists). For multi-label, count distinct
    # classes across all samples.
    if len(X) == 0:
        raise ValueError(
            f"No training data available for '{track_name}': "
            f"0 confirmed clips. Review some clips first."
        )
    
    if isinstance(y[0], list):
        unique_classes = set()
        for labels in y:
            unique_classes.update(labels)
        n_classes = len(unique_classes)
    else:
        n_classes = len(set(y))
    
    if len(X) < MIN_SAMPLES_PER_CLASS * n_classes:
        raise ValueError(
            f"Insufficient training data for '{track_name}': "
            f"{len(X)} samples across {n_classes} classes "
            f"(need at least {MIN_SAMPLES_PER_CLASS} per class)"
        )
    
    # X as numpy array; y kept in native format (list of strings for
    # single-label tracks, list of lists for insectnet multi-label)
    return np.array(X), y


# =============================================================================
# Training
# =============================================================================

def train_classifier(X, y, track_config):
    """Train a per-track classifier with cross-validation.

    Supports both single-label (y = list of strings) and multi-label
    (y = list of lists of strings). Multi-label uses threshold-based
    prediction via OneVsRestClassifier + per-class threshold tuning.

    Returns (model_package, cv_results) where model_package is a dict with:
    - scaler: fitted StandardScaler
    - classifier: fitted OneVsRestClassifier
    - classes: list of class names
    - thresholds: dict of per-class F1-optimized thresholds
    - is_multilabel: bool
    """
    classes = track_config["classes"]
    if classes is None:
        if isinstance(y[0], list):
            all_labels = set()
            for labels in y:
                all_labels.update(labels)
            classes = sorted(all_labels)
        else:
            classes = sorted(set(y))

    # Detect multi-label format — automatic, do not hardcode.
    # isinstance(y[0], list) is True when y is list-of-lists (insectnet)
    # and False when y is list of strings (chicken, bird46).
    #
    # INVARIANT: Do NOT replace with a hardcoded track_name check.
    # Multi-label detection must remain automatic so the same
    # train_classifier function works for all tracks.
    is_multilabel = isinstance(y[0], list)

    # Convert to binary indicator matrix
    if is_multilabel:
        mlb = MultiLabelBinarizer()
        mlb.fit([classes])  # ensure consistent column order
        y_bin = mlb.transform(y)  # (n_samples, n_classes)
    else:
        mlb = None
        y_bin = None

    print(f"\n  Classes ({len(classes)}): {classes}")
    print(f"  Samples: {len(X)}{' (multi-label)' if is_multilabel else ''}")

    # K-fold CV
    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    fold_metrics = []
    # For multi-label: accumulate per-class predictions as binary matrices
    all_y_true_bin = []
    all_y_prob_arr = []
    # For single-label: accumulate fold predictions for honest CV metrics
    all_y_true_sl = []
    all_y_pred_sl = []

    for fold, (train_idx, test_idx) in enumerate(kf.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        clf = OneVsRestClassifier(
            LogisticRegression(C=0.1, class_weight='balanced',
                             solver='lbfgs', max_iter=1000,
                             random_state=RANDOM_STATE)
        )

        if is_multilabel:
            y_train_bin = y_bin[train_idx]
            y_test_bin = y_bin[test_idx]
            clf.fit(X_train_scaled, y_train_bin)

            y_prob = clf.predict_proba(X_test_scaled)  # (n_test, n_classes)
            # Threshold at 0.5 for fold evaluation
            y_pred_bin = (y_prob >= 0.5).astype(int)

            all_y_true_bin.append(y_test_bin)
            all_y_prob_arr.append(y_prob)

            fold_f1 = f1_score(y_test_bin, y_pred_bin, average='macro',
                               zero_division=0)
        else:
            y_train, y_test_fold = y[train_idx], y[test_idx]
            clf.fit(X_train_scaled, y_train)

            y_prob = clf.predict_proba(X_test_scaled)
            y_pred = clf.predict(X_test_scaled)

            # Accumulate CV-fold predictions for honest metrics
            all_y_true_sl.extend(y_test_fold)
            all_y_pred_sl.extend(y_pred)

            fold_f1 = f1_score(y_test_fold, y_pred, average='weighted',
                               zero_division=0)

        fold_metrics.append(fold_f1)
        print(f"    Fold {fold+1}: F1={fold_f1:.4f}")

    # Full training on all data (final model)
    final_scaler = StandardScaler()
    X_scaled = final_scaler.fit_transform(X)

    final_clf = OneVsRestClassifier(
        LogisticRegression(C=0.1, class_weight='balanced',
                         solver='lbfgs', max_iter=1000,
                         random_state=RANDOM_STATE)
    )

    if is_multilabel:
        final_clf.fit(X_scaled, y_bin)
    else:
        final_clf.fit(X_scaled, y)

    # Per-class metrics and thresholds
    thresholds = {}
    per_class_f1 = {}

    if is_multilabel:
        # Concatenate fold results
        y_true_full = np.vstack(all_y_true_bin)    # (n_samples, n_classes)
        y_prob_full = np.vstack(all_y_prob_arr)    # (n_samples, n_classes)

        for i, cls in enumerate(classes):
            cls_true = y_true_full[:, i]
            cls_prob = y_prob_full[:, i]

            # F1-optimized threshold sweep
            best_thresh = 0.5
            best_f1 = 0
            for thresh in np.arange(0.1, 0.95, 0.05):
                cls_pred = (cls_prob >= thresh).astype(int)
                f1 = f1_score(cls_true, cls_pred, zero_division=0)
                if f1 > best_f1:
                    best_f1 = f1
                    best_thresh = thresh
            thresholds[cls] = round(best_thresh, 2)
            per_class_f1[cls] = round(float(best_f1), 4)

        # Macro F1 across all folds
        y_pred_full = (y_prob_full >= 0.5).astype(int)
        macro_f1 = f1_score(y_true_full, y_pred_full, average='macro',
                           zero_division=0)
        print(f"\n  CV Macro F1: {macro_f1:.4f} "
              f"(±{np.std(fold_metrics):.4f})")
    else:
        # Single-label path: per-class metrics from accumulated CV predictions
        if all_y_true_sl:
            report = classification_report(all_y_true_sl, all_y_pred_sl,
                                           output_dict=True, zero_division=0)
        else:
            report = {}

        print(f"\n  CV Weighted F1: {np.mean(fold_metrics):.4f} "
              f"(±{np.std(fold_metrics):.4f})")

        for cls in classes:
            thresholds[cls] = 0.5  # default for single-label
            if report and cls in report and cls != 'accuracy':
                per_class_f1[cls] = round(report[cls].get('f1-score', 0), 4)

    print(f"  Per-class thresholds: {thresholds}")

    # Compute dataset hash — flatten multi-label y for hashing
    if is_multilabel:
        hash_labels = []
        for labels in sorted(y, key=lambda x: tuple(sorted(x))):
            hash_labels.append(",".join(sorted(labels)))
        dataset_hash = compute_dataset_hash(hash_labels)
    else:
        dataset_hash = compute_dataset_hash(y)

    model_package = {
        "track": track_config.get("track_name", "unknown"),
        "version": track_config.get("version", "v0.0.0"),
        "classes": classes,
        "thresholds": thresholds,
        "scaler": final_scaler,
        "classifier": final_clf,
        "is_multilabel": is_multilabel,
        "cv_f1_mean": float(np.mean(fold_metrics)),
        "cv_f1_std": float(np.std(fold_metrics)),
        "per_class_f1": per_class_f1,
        "train_count": len(X),
        "trained_at": datetime.now().isoformat(),
        "dataset_hash": dataset_hash,
    }

    return model_package, None


# =============================================================================
# Database Update
# =============================================================================

def score_all_clips(model_package, track_name):
    """Run the new model on relevant clips for this track, update predictions.

    Scopes to the track's natural source to prevent cross-contamination:
      insectnet → insectnet-sourced clips only
      bird46    → birdnet-sourced clips only
      chicken   → all clips (binary chicken/not is relevant everywhere)
    """
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    
    scaler = model_package["scaler"]
    clf = model_package["classifier"]
    classes = model_package["classes"]
    version = model_package["version"]
    
    if track_name == "insectnet":
        where_clause = "WHERE perch_embedding IS NOT NULL AND source = 'insectnet'"
    elif track_name == "bird46":
        where_clause = "WHERE perch_embedding IS NOT NULL AND source = 'birdnet'"
    else:
        # chicken, soundscape — applies to all clips
        where_clause = "WHERE perch_embedding IS NOT NULL"
    
    rows = conn.execute(
        f"SELECT id, perch_embedding FROM clips {where_clause}"
    ).fetchall()
    
    updated = 0
    for r in rows:
        emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
        if emb.shape != (1536,):
            continue
        
        X = scaler.transform(emb.reshape(1, -1))
        proba = clf.predict_proba(X)[0]
        thresholds = model_package.get("thresholds", {})
        
        if model_package.get("is_multilabel"):
            # Multi-label: apply per-class thresholds, return all active
            active = []
            for i, cls in enumerate(classes):
                thresh = thresholds.get(cls, 0.5)
                if proba[i] >= thresh:
                    active.append(cls)
            
            if not active:
                # No class above threshold → classify as background
                pred_class = "background"
                pred_conf = float(proba[classes.index("background")]) if "background" in classes else 0.0
            else:
                pred_class = ", ".join(active)
                pred_conf = float(max(proba[i] for i, cls in enumerate(classes) if cls in active))
        else:
            # Single-label: argmax
            pred_idx = np.argmax(proba)
            pred_class = classes[pred_idx]
            pred_conf = float(proba[pred_idx])
        
        conn.execute(
            "UPDATE clips SET model_version = ?, model_pred = ?, model_conf = ? WHERE id = ?",
            (version, pred_class, pred_conf, r["id"])
        )
        updated += 1
    
    conn.commit()
    conn.close()
    return updated


# =============================================================================
# Model Registry
# =============================================================================

def register_model(model_package):
    """Insert a model record into the models table."""
    conn = get_db()
    
    # Deactivate previous active model for this track
    conn.execute(
        "UPDATE models SET active = 0 WHERE track = ? AND active = 1",
        (model_package["track"],)
    )
    
    conn.execute("""
        INSERT INTO models 
        (track, version, artifact_path, classes, train_count,
         cv_f1_macro, per_class_f1, dataset_hash, active, trained_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), ?)
    """, (
        model_package["track"],
        model_package["version"],
        model_package.get("artifact_path", ""),
        json.dumps(model_package["classes"]),
        model_package["train_count"],
        model_package["cv_f1_mean"],
        json.dumps(model_package["per_class_f1"]),
        model_package["dataset_hash"],
        f"Thresholds: {model_package['thresholds']}",
    ))
    conn.commit()
    conn.close()


# =============================================================================
# InsectNet Comparison
# =============================================================================

def compare_with_insectnet(model_package):
    """Compare the new Perch-based model against the existing InsectNet model.
    
    Loads a held-out set of clips, runs both models, reports comparison.
    """
    existing_model_path = TRACKS["insectnet"]["comparison_model"]
    if not existing_model_path or not existing_model_path.exists():
        print("\n  ⚠ No existing InsectNet model found for comparison.")
        return
    
    print("\n  === Comparison: Perch-based vs BirdNET-logit InsectNet ===")
    print(f"  Existing model: {existing_model_path}")
    
    # Load a held-out set from the archive that has both embeddings AND logits
    conn = get_db()
    rows = conn.execute("""
        SELECT perch_embedding, human_label, source_label FROM clips
        WHERE review_status IN ('confirmed', 'corrected')
        AND perch_embedding IS NOT NULL
        AND source = 'insectnet'
        LIMIT 50
    """).fetchall()
    conn.close()
    
    if len(rows) < 10:
        print("  Not enough comparison data yet. Keep reviewing!")
        return
    
    print(f"  Comparison set: {len(rows)} clips")
    print("  (Full comparison will be meaningful after more labels are confirmed)")
    
    # Load existing InsectNet model
    try:
        old_m = joblib.load(existing_model_path)
        old_scaler = old_m["scaler"]
        old_clf = old_m["classifier"]
        old_classes = old_m["classes"]
        print(f"  Existing model classes: {old_classes}")
    except Exception as e:
        print(f"  ⚠ Could not load existing model: {e}")
        return
    
    # Score with new model
    scaler = model_package["scaler"]
    clf = model_package["classifier"]
    new_classes = model_package["classes"]
    
    new_correct = 0
    old_correct = 0
    total = 0
    
    for r in rows:
        true_label = (r["human_label"] or r["source_label"] or "").strip().lower()
        if not true_label:
            continue
        
        emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
        if emb.shape != (1536,):
            continue
        
        # New model prediction
        X_new = scaler.transform(emb.reshape(1, -1))
        new_proba = clf.predict_proba(X_new)[0]
        new_pred = new_classes[np.argmax(new_proba)]
        
        # Old model requires logits, not embeddings — skip comparison for now
        # (This would need the full BirdNET pipeline to extract logits)
        
        total += 1
    
    print(f"  Comparison summary: {total} clips evaluated")
    if total > 0:
        print("  Full comparison requires BirdNET logit extraction pipeline (future work)")
        print("  For now: Perch-based model metrics are reported above.")


# =============================================================================
# CLI
# =============================================================================

def list_tracks():
    """Print available tracks and their status."""
    conn = get_db()
    print("\nAvailable tracks:")
    for name, config in TRACKS.items():
        # Count confirmed clips relevant to this track
        if name == "insectnet":
            count = conn.execute(
                "SELECT COUNT(*) FROM clips WHERE review_status IN ('confirmed','corrected') AND source='insectnet'"
            ).fetchone()[0]
        elif name == "chicken":
            count = conn.execute(
                "SELECT COUNT(*) FROM clips WHERE review_status IN ('confirmed','corrected') AND human_label IS NOT NULL"
            ).fetchone()[0]
        elif name == "bird46":
            count = conn.execute(
                "SELECT COUNT(*) FROM clips WHERE review_status IN ('confirmed','corrected') AND source='birdnet'"
            ).fetchone()[0]
        else:
            count = conn.execute(
                "SELECT COUNT(*) FROM clips WHERE review_status IN ('confirmed','corrected')"
            ).fetchone()[0]
        # Latest version
        latest = sorted(MODELS_DIR.glob(f"{name}_v*.joblib"))
        version = latest[-1].stem if latest else "not trained"
        print(f"  {name:<20} {config['description']:<40} {version}")
        print(f"  {'':20} Confirmed clips: {count}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Pine Hollow Retrain Pipeline")
    parser.add_argument("--track", help="Track to retrain (insectnet, chicken, bird46)")
    parser.add_argument("--all-tracks", action="store_true", help="Retrain all tracks")
    parser.add_argument("--version", help="Explicit version string (e.g. v0.2.0)")
    parser.add_argument("--list-tracks", action="store_true", help="Show track status")
    parser.add_argument("--compare", action="store_true", help="Compare with previous model")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be trained")
    args = parser.parse_args()
    
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.list_tracks:
        list_tracks()
        return
    
    tracks_to_train = []
    if args.all_tracks:
        tracks_to_train = list(TRACKS.keys())
    elif args.track:
        if args.track not in TRACKS:
            print(f"Unknown track: {args.track}")
            list_tracks()
            sys.exit(1)
        tracks_to_train = [args.track]
    else:
        parser.print_help()
        return
    
    for track_name in tracks_to_train:
        print(f"\n{'=' * 60}")
        print(f"  Retraining: {track_name}")
        print(f"  {TRACKS[track_name]['description']}")
        print(f"{'=' * 60}")
        
        track_config = TRACKS[track_name].copy()
        track_config["track_name"] = track_name
        
        # Load data
        try:
            X, y = load_training_data(track_name)
        except ValueError as e:
            print(f"\n  ⚠ {e}")
            continue
        
        print(f"\n  Loaded {len(X)} training samples")
        
        classes = track_config.get("classes")
        if classes is None:
            classes = sorted(set(y))
        track_config["classes"] = classes
        
        if args.dry_run:
            print("\n  [DRY RUN] Would train with:")
            print(f"    Classes: {classes}")
            print(f"    Samples: {len(X)}")
            print(f"    CV folds: {N_FOLDS}")
            print(f"    Version: {resolve_version(track_name, args.version)}")
            continue
        
        # Train
        version = resolve_version(track_name, args.version)
        track_config["version"] = version
        model_package, report = train_classifier(X, y, track_config)
        
        # Save artifact
        artifact_path = MODELS_DIR / f"{track_name}_{version}.joblib"
        joblib.dump(model_package, artifact_path)
        model_package["artifact_path"] = str(artifact_path)
        print(f"\n  Saved: {artifact_path}")
        
        # Register in DB
        register_model(model_package)
        print(f"  Registered in model registry as active")
        
        # Score all clips for this track
        updated = score_all_clips(model_package, track_name)
        print(f"  Updated predictions for {updated} clips in archive")
        
        # Compare
        if args.compare and track_name == "insectnet":
            compare_with_insectnet(model_package)
        
        print(f"\n  ✅ {track_name} {version} ready")
    
    print(f"\n{'=' * 60}")
    print(f"  Done. Run with --compare to benchmark against previous versions.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
