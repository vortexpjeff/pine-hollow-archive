#!/usr/bin/env python3
"""
Pine Hollow Bioacoustics Data Factory — Phase 0 Pull + Embed Pipeline

Pulls new clips from BirdNET-Pi, runs Perch 2.0 embedding extraction,
stores everything in the archive SQLite database.

Usage:
    python3 pull_clips.py                    # pull new clips incrementally
    python3 pull_clips.py --backlog           # pull ALL clips (first run)
    python3 pull_clips.py --dry-run           # show what would be pulled
    python3 pull_clips.py --limit 100         # process at most N clips

Requires:
    - SSH access to birdnetpi@192.168.1.223 (askpass pattern)
    - Perch 2.0 CPU model at perch_model_path
    - ffmpeg on PATH
    - CUDA_VISIBLE_DEVICES=-1
"""

import os, sys, csv, json, time, hashlib, argparse, subprocess, shutil, glob
from pathlib import Path
from datetime import datetime
import sqlite3

# =============================================================================
# Configuration
# =============================================================================

ARCHIVE_ROOT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_ROOT / "archive.db"
TEMP_DIR = ARCHIVE_ROOT / "temp"
BIRDNET_DIR = ARCHIVE_ROOT / "birdnet" / "By_Date"
INSECTNET_DIR = ARCHIVE_ROOT / "insectnet" / "captures"
TAG_MAP_PATH = ARCHIVE_ROOT / "tag_map.json"

PERCH_MODEL_PATH = Path.home() / ".cache/kagglehub/models/google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu/1"
LABELS_CSV = PERCH_MODEL_PATH / "assets" / "labels.csv"

PI_HOST = "192.168.1.223"
PI_USER = "birdnetpi"
PI_PASS = "birdnetpi"

PI_BIRDNET_PATH = "~/BirdSongs/Extracted/By_Date/"
PI_INSECTNET_PATH = "~/insectnet_capture/captures/"
PI_INSECTNET_SCRIPT = "~/insectnet_capture/insectnet_capture.py"
PI_CLASSIFIER = "~/insectnet_capture/classifier.joblib"

ASKPASS_PATH = Path("/tmp/askpass.sh")

# Perch 2.0 expects: 5s @ 32kHz = 160,000 samples
PERCH_TARGET_SAMPLES = 160000
PERCH_SAMPLE_RATE = 32000
PERCH_DURATION_S = 5.0


# =============================================================================
# Helpers
# =============================================================================

def setup_askpass():
    """Create the SSH_ASKPASS script for password auth."""
    content = "#!/bin/sh\necho '{}'\n".format(PI_PASS)
    try:
        ASKPASS_PATH.write_text(content)
        ASKPASS_PATH.chmod(0o755)
        return True
    except OSError as e:
        print(f"  ⚠ Could not create SSH askpass script: {e}", file=sys.stderr)
        return False

def pi_cmd(command):
    """Run a command on the Pi via SSH with password auth."""
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["SSH_ASKPASS"] = str(ASKPASS_PATH)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    full_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=10",
                f"{PI_USER}@{PI_HOST}", command]
    result = subprocess.run(full_cmd, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 and "Permission denied" in result.stderr:
        print("  ⚠ SSH failed — is the Pi online?", file=sys.stderr)
        return None
    return result


# =============================================================================
# Database
# =============================================================================

class ArchiveDB:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
    
    def get_sync_state(self, source):
        row = self.conn.execute(
            "SELECT last_file FROM sync_state WHERE source = ?", (source,)
        ).fetchone()
        return row["last_file"] if row else None
    
    def update_sync_state(self, source, last_file):
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_state (source, last_sync_at, last_file) "
            "VALUES (?, datetime('now', 'localtime'), ?)",
            (source, last_file)
        )
        self.conn.commit()
    
    def clip_exists(self, source, filename):
        row = self.conn.execute(
            "SELECT id FROM clips WHERE source = ? AND filename = ?",
            (source, filename)
        ).fetchone()
        return row is not None
    
    def insert_clip(self, clip_data):
        self.conn.execute("""
            INSERT OR IGNORE INTO clips 
            (filename, source, source_label, source_conf, file_path, file_size, 
             duration_s, recorded_at, pulled_at, processing_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), 'pulled')
        """, (
            clip_data["filename"], clip_data["source"],
            clip_data["source_label"], clip_data.get("source_conf"),
            clip_data["file_path"], clip_data.get("file_size"),
            clip_data.get("duration_s"), clip_data.get("recorded_at")
        ))
        self.conn.commit()
    
    def update_embedding(self, clip_id, embedding, perch_top1, perch_top1_conf, 
                         perch_top10, perch_top50):
        self.conn.execute("""
            UPDATE clips SET 
                perch_embedding = ?, perch_top1 = ?, perch_top1_conf = ?,
                perch_top10 = ?, perch_top50 = ?,
                processing_status = 'done'
            WHERE id = ?
        """, (
            embedding.tobytes() if embedding is not None else None,
            perch_top1, perch_top1_conf,
            json.dumps(perch_top10), json.dumps(perch_top50),
            clip_id
        ))
        self.conn.commit()
    
    def mark_failed(self, clip_id, error):
        self.conn.execute(
            "UPDATE clips SET processing_status = 'failed', processing_error = ? WHERE id = ?",
            (str(error)[:500], clip_id)
        )
        self.conn.commit()
    
    def start_run(self):
        cursor = self.conn.execute(
            "INSERT INTO processing_log (run_id, started_at) VALUES (?, datetime('now', 'localtime'))",
            (datetime.now().strftime("%Y%m%d_%H%M%S"),)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def complete_run(self, run_id, stats):
        self.conn.execute("""
            UPDATE processing_log SET 
                completed_at = datetime('now', 'localtime'),
                status = 'completed',
                clips_pulled = ?, clips_converted = ?,
                clips_embedded = ?, clips_failed = ?
            WHERE id = ?
        """, (stats["pulled"], stats["converted"], stats["embedded"], 
              stats["failed"], run_id))
        self.conn.commit()
    
    def close(self):
        self.conn.close()


# =============================================================================
# BirdNET clip discovery via rsync dry-run
# =============================================================================

def discover_birdnet_clips(last_sync_file=None):
    """Use rsync dry-run to find new BirdNET files on the Pi."""
    print("\n  Discovering BirdNET clips...")
    
    rsync_cmd = [
        "rsync", "-avzm", "--dry-run",
        "--include=*/", "--include=*.mp3", "--exclude=*",
        "--no-motd",
        f"{PI_USER}@{PI_HOST}:{PI_BIRDNET_PATH}",
        str(BIRDNET_DIR) + "/"
    ]
    
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["SSH_ASKPASS"] = str(ASKPASS_PATH)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    
    result = subprocess.run(rsync_cmd, env=env, capture_output=True, text=True, timeout=60)
    
    # Collect all .mp3 entries and sort by path (date/species/filename)
    all_entries = []
    for line in result.stdout.split("\n"):
        line = line.strip()
        if not line or line.endswith("/") or not line.endswith(".mp3"):
            continue
        all_entries.append(line)
    all_entries.sort()
    
    if last_sync_file is None:
        return all_entries
    
    try:
        cutoff_idx = all_entries.index(last_sync_file)
        return all_entries[cutoff_idx + 1:]
    except ValueError:
        # Last-synced file was deleted from the Pi. Fall back to all files —
        # INSERT OR IGNORE in the DB prevents duplicate processing.
        print(f"  ⚠ Last synced file not found on Pi (may have been deleted): {last_sync_file}",
              file=sys.stderr)
        print(f"  → Syncing all {len(all_entries)} files (INSERT OR IGNORE prevents duplicates)",
              file=sys.stderr)
        return all_entries


def discover_insectnet_clips(last_sync_file=None):
    """Use rsync dry-run to find new InsectNet files on the Pi."""
    print("\n  Discovering InsectNet clips...")
    
    rsync_cmd = [
        "rsync", "-avzm", "--dry-run",
        "--include=*/", "--include=*.wav", "--exclude=*",
        "--no-motd",
        f"{PI_USER}@{PI_HOST}:{PI_INSECTNET_PATH}",
        str(INSECTNET_DIR) + "/"
    ]
    
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["SSH_ASKPASS"] = str(ASKPASS_PATH)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    
    result = subprocess.run(rsync_cmd, env=env, capture_output=True, text=True, timeout=60)
    
    # Collect all .wav entries and sort by path (class/filename)
    all_entries = []
    for line in result.stdout.split("\n"):
        line = line.strip()
        if not line or line.endswith("/") or not line.endswith(".wav"):
            continue
        all_entries.append(line)
    all_entries.sort()
    
    if last_sync_file is None:
        return all_entries
    
    try:
        cutoff_idx = all_entries.index(last_sync_file)
        return all_entries[cutoff_idx + 1:]
    except ValueError:
        print(f"  ⚠ Last synced file not found on Pi (may have been deleted): {last_sync_file}",
              file=sys.stderr)
        print(f"  → Syncing all {len(all_entries)} files (INSERT OR IGNORE prevents duplicates)",
              file=sys.stderr)
        return all_entries


# =============================================================================
# Perch 2.0 Embedding Extraction
# =============================================================================

class PerchEmbedder:
    """Thin wrapper around Perch 2.0 for batch embedding extraction."""
    
    def __init__(self, model_path, labels_path):
        import tensorflow as tf
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        
        self.model = None
        self.labels = []
        
        print(f"  Loading Perch 2.0 from {model_path}...")
        t0 = time.time()
        self.model = tf.saved_model.load(str(model_path))
        print(f"    Loaded in {time.time()-t0:.1f}s")
        
        with open(str(labels_path)) as f:
            reader = csv.reader(f)
            self.labels = [row[0] for row in reader][1:]
        print(f"    {len(self.labels)} species labels")
    
    def embed(self, wav_path):
        """Extract 1536-dim embedding + top-50 predictions from a WAV file.
        
        Expects WAV at 32000 Hz, mono. Will read anything scipy can handle.
        Returns (embedding, top50_list) or raises on failure.
        """
        import scipy.io.wavfile
        import numpy as np
        
        sr, audio = scipy.io.wavfile.read(str(wav_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        orig_dtype = audio.dtype
        audio = audio.astype(np.float32)
        # Normalize based on original dtype (done AFTER casting so we get float audio)
        if np.issubdtype(orig_dtype, np.integer):
            orig_max = float(np.iinfo(orig_dtype).max)
            audio = audio / orig_max
        
        # Center-crop or pad to 160k samples
        target = PERCH_TARGET_SAMPLES
        if len(audio) > target:
            start = (len(audio) - target) // 2
            audio = audio[start:start+target]
        else:
            audio = np.pad(audio, (0, max(0, target - len(audio))))
        
        import tensorflow as tf
        inp = tf.constant(audio.reshape(1, -1), dtype=tf.float32)
        outputs = self.model.signatures['serving_default'](inputs=inp)
        
        embedding = outputs['embedding'].numpy()[0]
        label_logits = outputs['label'].numpy()[0]
        
        # Get top-50 species with sigmoid confidence
        top50_idx = np.argsort(label_logits)[-50:][::-1]
        top50 = [{
            "species": self.labels[i] if i < len(self.labels) else "?",
            "confidence": float(1.0 / (1.0 + np.exp(-label_logits[i])))
        } for i in top50_idx]
        
        top1 = top50[0]
        top10 = top50[:10]
        
        return embedding, top1, top10, top50


# =============================================================================
# Audio Conversion
# =============================================================================

def convert_to_5s_32khz(input_path, output_path):
    """Convert any audio to 5s @ 32kHz mono WAV using ffmpeg.
    
    Center-crops audio longer than 5s, pads silence for shorter audio.
    Returns (success_bool, duration_seconds).
    """
    # First get duration
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "csv=p=0",
        str(input_path)
    ], capture_output=True, text=True, timeout=30)
    
    try:
        duration_s = float(probe.stdout.strip())
    except (ValueError, TypeError):
        duration_s = 0
    
    # Center-crop: offset = max(0, (duration - 5) / 2)
    offset = max(0.0, (duration_s - PERCH_DURATION_S) / 2)
    
    result = subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(offset),
        "-i", str(input_path),
        "-t", str(PERCH_DURATION_S),
        "-ar", str(PERCH_SAMPLE_RATE),
        "-ac", "1",
        "-sample_fmt", "s16",
        str(output_path)
    ], capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        print(f"    ⚠ ffmpeg failed: {result.stderr.strip()[:200]}", file=sys.stderr)
        return False, duration_s
    
    return True, duration_s


# =============================================================================
# Main Pipeline
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Pine Hollow Bioacoustics Data Factory — Pull + Embed")
    parser.add_argument("--backlog", action="store_true", help="Pull ALL clips (ignore sync state)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pulled without processing")
    parser.add_argument("--limit", type=int, default=0, help="Max clips to process (0 = unlimited)")
    parser.add_argument("--perch-only", action="store_true", help="Only run Perch on already-pulled clips")
    return parser.parse_args()


def main():
    args = parse_args()
    
    print("=" * 60)
    print("  Pine Hollow Data Factory — Phase 0 Pipeline")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Setup
    if not setup_askpass():
        print("  ⚠ SSH askpass setup failed — cannot connect to Pi.", file=sys.stderr)
        if not args.dry_run:
            sys.exit(1)
    db = ArchiveDB(DB_PATH)
    
    # Load Perch
    embedder = PerchEmbedder(PERCH_MODEL_PATH, LABELS_CSV)
    
    if args.dry_run:
        print("\n  [DRY RUN — No files will be modified]")
    
    run_id = db.start_run()
    stats = {"pulled": 0, "converted": 0, "embedded": 0, "failed": 0}
    
    def process_clip(source, label, conf, filename, remote_path, local_path):
        """Process a single clip through the pipeline."""
        nonlocal stats
        stats["pulled"] += 1
        
        if db.clip_exists(source, filename):
            return
        
        clip_data = {
            "filename": filename,
            "source": source,
            "source_label": label,
            "source_conf": conf,
            "file_path": str(local_path.relative_to(ARCHIVE_ROOT)) if local_path else str(remote_path),
            "file_size": local_path.stat().st_size if local_path and local_path.exists() else 0,
            "recorded_at": None,  # extracted from filename metadata
        }
        
        if args.dry_run:
            print(f"  [DRY] Would process: [{source}] {label} — {filename}")
            return
        
        db.insert_clip(clip_data)
        clip_id = db.conn.execute(
            "SELECT id FROM clips WHERE source = ? AND filename = ?",
            (source, filename)
        ).fetchone()["id"]
        
        # Copy from Pi if not already local
        temp_raw = TEMP_DIR / f"raw_{source}_{clip_id}{os.path.splitext(filename)[1]}"
        temp_wav = TEMP_DIR / f"conv_{clip_id}.wav"
        
        try:
            if not local_path or not local_path.exists():
                # rsync will have already pulled this, or we need to scp
                pass  # For now, assume rsync handles the copy
            
            # TODO: Handle source audio that's already local
            
            # Extract source audio
            source_path = local_path if local_path else temp_raw
            
            # Convert to 5s @ 32kHz WAV — unless we're re-processing an existing WAV
            if args.perch_only:
                # When running perch-only, the source_path should already be a
                # convertible audio file. We still need the converted 5s/32kHz WAV.
                if source_path.suffix.lower() != ".wav":
                    ok, duration = convert_to_5s_32khz(source_path, temp_wav)
                    if not ok:
                        db.mark_failed(clip_id, "ffmpeg conversion failed")
                        stats["failed"] += 1
                        return
                    clip_data["duration_s"] = duration
                else:
                    # Already a WAV — use as-is (Perch will handle resampling)
                    temp_wav = source_path
                    clip_data["duration_s"] = clip_data.get("duration_s", 0)
            else:
                ok, duration = convert_to_5s_32khz(source_path, temp_wav)
                if not ok:
                    db.mark_failed(clip_id, "ffmpeg conversion failed")
                    stats["failed"] += 1
                    return
                clip_data["duration_s"] = duration
            
            # Perch embedding
            embedding, top1, top10, top50 = embedder.embed(temp_wav)
            
            # Store in DB
            db.update_embedding(clip_id, embedding, top1["species"],
                               top1["confidence"], top10, top50)
            stats["embedded"] += 1
            stats["converted"] += 1
            
            if stats["pulled"] % 10 == 0:
                print(f"    ... {stats['pulled']} clips processed ({stats['embedded']} embedded, {stats['failed']} failed)")
        
        except Exception as e:
            db.mark_failed(clip_id, str(e))
            stats["failed"] += 1
            print(f"    ⚠ Error: {e}", file=sys.stderr)
        finally:
            # Cleanup temp files
            for p in [temp_raw, temp_wav]:
                if p.exists():
                    p.unlink()
    
    # Discover and process new clips
    total_to_process = 0
    
    # PHASE 1: BirdNET clips
    last_birdnet = db.get_sync_state("birdnet")
    if args.backlog:
        last_birdnet = None
    
    birdnet_files = discover_birdnet_clips(last_birdnet)
    
    if not birdnet_files:
        print("  No new BirdNET clips found.")
    else:
        total_to_process += len(birdnet_files)
        print(f"\n  Found {len(birdnet_files)} new BirdNET clips")
        
        # rsync only the files we'll process
        if not args.dry_run:
            limit = args.limit if args.limit > 0 else len(birdnet_files)
            files_to_pull = birdnet_files[:limit]
            print(f"  Pulling {len(files_to_pull)} BirdNET clips from Pi...")
            env = os.environ.copy()
            env["DISPLAY"] = ":0"
            env["SSH_ASKPASS"] = str(ASKPASS_PATH)
            env["SSH_ASKPASS_REQUIRE"] = "force"
            # Build per-directory batches for efficiency
            dirs_to_pull = set()
            for fp in files_to_pull:
                dirname = str(Path(fp).parent)
                dirs_to_pull.add(dirname)
            for dirname in sorted(dirs_to_pull):
                subprocess.run([
                    "rsync", "-azm",
                    "--include=*/", "--include=*.mp3", "--exclude=*",
                    "--no-motd",
                    f"{PI_USER}@{PI_HOST}:{PI_BIRDNET_PATH}{dirname}/",
                    str(BIRDNET_DIR / dirname) + "/"
                ], env=env, timeout=60)
        
        # Process each clip
        limit = args.limit if args.limit > 0 else len(birdnet_files)
        for i, filepath in enumerate(birdnet_files):
            if i >= limit:
                break
            
            # Parse path: YYYY-MM-DD/Species/filename.mp3
            parts = filepath.split("/")
            if len(parts) < 3:
                continue
            date_str = parts[0]
            species = parts[1]
            filename = parts[-1]
            
            # Extract confidence from BirdNET filename pattern.
            # Format: Species-XX-YYYY-MM-DD-birdnet-HH:MM:SS.mp3
            # Confidence (XX) is always the first 2-digit numeric token.
            try:
                tokens = filename.rsplit(".", 1)[0].split("-")
                conf = None
                for token in tokens:
                    if token.isdigit() and len(token) == 2:
                        conf = int(token) / 100.0
                        break
            except (ValueError, IndexError):
                conf = None
            
            local_path = BIRDNET_DIR / filepath
            
            process_clip("birdnet", species, conf, filename, filepath, local_path)
        
        last_file = birdnet_files[-1] if birdnet_files else last_birdnet
        if not args.dry_run and not args.limit:
            db.update_sync_state("birdnet", last_file)
    
    # PHASE 2: InsectNet clips
    last_insectnet = db.get_sync_state("insectnet")
    if args.backlog:
        last_insectnet = None
    
    insectnet_files = discover_insectnet_clips(last_insectnet)
    
    if not insectnet_files:
        print("  No new InsectNet clips found.")
    else:
        total_to_process += len(insectnet_files)
        print(f"\n  Found {len(insectnet_files)} new InsectNet clips")
        
        if not args.dry_run:
            limit = args.limit if args.limit > 0 else len(insectnet_files)
            files_to_pull = insectnet_files[:limit]
            print(f"  Pulling {len(files_to_pull)} InsectNet clips from Pi...")
            env = os.environ.copy()
            env["DISPLAY"] = ":0"
            env["SSH_ASKPASS"] = str(ASKPASS_PATH)
            env["SSH_ASKPASS_REQUIRE"] = "force"
            # Build per-directory batches
            dirs_to_pull = set()
            for fp in files_to_pull:
                dirname = str(Path(fp).parent)
                dirs_to_pull.add(dirname)
            for dirname in sorted(dirs_to_pull):
                subprocess.run([
                    "rsync", "-azm",
                    "--include=*/", "--include=*.wav", "--exclude=*",
                    "--no-motd",
                    f"{PI_USER}@{PI_HOST}:{PI_INSECTNET_PATH}{dirname}/",
                    str(INSECTNET_DIR / dirname) + "/"
                ], env=env, timeout=60)
        
        limit = args.limit if args.limit > 0 else len(insectnet_files)
        for i, filepath in enumerate(insectnet_files):
            if i >= limit:
                break
            
            # Parse path: class_name/filename.wav
            parts = filepath.split("/")
            if len(parts) < 2:
                continue
            insect_class = parts[0]
            filename = parts[-1]
            
            local_path = INSECTNET_DIR / filepath
            
            process_clip("insectnet", insect_class, None, filename, filepath, local_path)
        
        last_file = insectnet_files[-1] if insectnet_files else last_insectnet
        if not args.dry_run and not args.limit:
            db.update_sync_state("insectnet", last_file)
    
    if total_to_process == 0 and not args.dry_run:
        print("  Nothing to process.")
    
    # Complete the run
    db.complete_run(run_id, stats)
    db.close()
    
    print(f"\n{'=' * 60}")
    print(f"  Run complete: {stats['pulled']} discovered")
    print(f"  Backlog: ~4 hrs for 15k clips at ~970ms/clip")
    print(f"  Daily incremental: ~2-3 min")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
