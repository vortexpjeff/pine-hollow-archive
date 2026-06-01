#!/usr/bin/env python3
"""
Build Perch foundation model from public data.
Downloads research-grade iNaturalist audio for 6 insectnet classes,
extracts Perch 2.0 embeddings, trains sklearn head, saves to models/.

One-shot bootstrap. Run once to seed the archive with a working classifier.
"""
import os, sys, json, csv, time, subprocess, sqlite3, argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import requests
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, MultiLabelBinarizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.model_selection import KFold
from sklearn.metrics import f1_score

# ── Config ────────────────────────────────────────────────────────
ARCHIVE_ROOT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_ROOT / "archive.db"
MODELS_DIR = ARCHIVE_ROOT / "models"
TEMP_DIR = ARCHIVE_ROOT / "temp"
PERCH_MODEL_PATH = Path.home() / ".cache/kagglehub/models/google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu/1"
LABELS_CSV = PERCH_MODEL_PATH / "assets" / "labels.csv"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── Target species per class ───────────────────────────────────────
# Genus → species with research-grade audio on iNat.
# Focused on Eastern US / Appalachian species where possible.
TARGET_SPECIES = {
    "cicada_drone": [
        "Neotibicen canicularis", "Neotibicen linnei", "Neotibicen tibicen",
        "Megatibicen grossus", "Megatibicen pronotalis",
        "Magicicada septendecim", "Magicicada cassinii",
        "Okanagana rimosa", "Diceroprocta apache",
        "Platypedia areolata", "Cacama valvata",
    ],
    "cricket_katydid": [
        "Gryllus pennsylvanicus", "Gryllus veletis", "Gryllus rubens",
        "Oecanthus fultoni", "Oecanthus niveus", "Oecanthus nigricornis",
        "Neoconocephalus ensiger", "Neoconocephalus retusus",
        "Pterophylla camellifolia", "Microcentrum rhombifolium",
        "Allonemobius fasciatus", "Eunemobius carolinus",
        "Amblycorypha oblongifolia", "Conocephalus fasciatus",
        "Gryllotalpa major", "Neocurtilla hexadactyla",
    ],
    "frog": [
        "Dryophytes chrysoscelis", "Pseudacris crucifer",
        "Anaxyrus americanus", "Anaxyrus fowleri",
        "Lithobates clamitans", "Lithobates catesbeianus",
        "Lithobates sphenocephalus", "Gastrophryne carolinensis",
        "Hyla cinerea", "Hyla squirella",
        "Acris crepitans", "Acris gryllus",
    ],
    "grasshopper": [
        "Melanoplus differentialis", "Melanoplus femurrubrum",
        "Schistocerca americana", "Chortophaga viridifasciata",
        "Dissosteira carolina", "Arphia xanthoptera",
        "Psinidia fenestralis", "Trimerotropis maritima",
        "Spharagemon bolli", "Encoptolophus costalis",
        "Chorthippus biguttulus", "Gomphocerus sibiricus",
    ],
    "bee": [
        "Apis mellifera", "Bombus impatiens", "Bombus pensylvanicus",
        "Xylocopa virginica", "Bombus bimaculatus", "Bombus griseocollis",
        "Xylocopa micans", "Bombus fervidus",
    ],
}

TOTAL_TARGET = 1500  # aim for ~250 per class

def get_archive_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def load_perch():
    print("Loading Perch 2.0...")
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf
    model = tf.saved_model.load(str(PERCH_MODEL_PATH))
    with open(str(LABELS_CSV)) as f:
        labels = [row[0] for row in csv.reader(f)][1:]
    print(f"  {len(labels)} species labels loaded")
    return model, labels

def download_inat_audio(cls_name, species_list, max_per_species=30):
    """Download research-grade audio from iNaturalist API."""
    print(f"\nDownloading {cls_name} audio...")
    total = 0
    for species in species_list:
        if total >= max_per_species * len(species_list) // 2:
            break
        try:
            r = requests.get("https://api.inaturalist.org/v1/observations", params={
                "taxon_name": species, "has[]": "sounds",
                "quality_grade": "research", "per_page": max_per_species,
                "order": "desc", "order_by": "created_at",
            }, timeout=30)
            data = r.json()
            count = 0
            for obs in data.get("results", []):
                for sound in obs.get("sounds", []):
                    url = sound.get("file_url", "")
                    if not url:
                        continue
                    safe_name = f"{species.replace(' ','_')}_{obs['id']}.{url.split('.')[-1].split('?')[0]}"
                    path = TEMP_DIR / safe_name
                    if path.exists():
                        continue
                    try:
                        audio = requests.get(url, timeout=60).content
                        path.write_bytes(audio)
                        count += 1
                        total += 1
                    except Exception:
                        continue
                if count >= max_per_species:
                    break
            print(f"  {species}: {count} clips")
            time.sleep(0.3)  # rate limit
        except Exception as e:
            print(f"  {species}: ERROR - {e}")
    print(f"  Total {cls_name}: {total} clips")
    return total

def convert_to_wav(input_path, output_path):
    """Convert any audio to 5s @ 32kHz mono WAV via ffmpeg."""
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-t", "5", "-ar", "32000", "-ac", "1", "-sample_fmt", "s16",
        str(output_path)
    ], capture_output=True, text=True, timeout=30)
    return result.returncode == 0, None

def extract_embedding(perch_model, wav_path):
    """Extract 1536-dim Perch embedding from a WAV file."""
    import scipy.io.wavfile
    import tensorflow as tf
    
    sr, audio = scipy.io.wavfile.read(str(wav_path))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    orig_dtype = audio.dtype
    audio = audio.astype(np.float32)
    if np.issubdtype(orig_dtype, np.integer):
        audio = audio / float(np.iinfo(orig_dtype).max)
    
    target = 160000
    if len(audio) > target:
        start = (len(audio) - target) // 2
        audio = audio[start:start+target]
    else:
        audio = np.pad(audio, (0, max(0, target - len(audio))))
    
    inp = tf.constant(audio.reshape(1, -1), dtype=tf.float32)
    outputs = perch_model.signatures['serving_default'](inputs=inp)
    return outputs['embedding'].numpy()[0]

def process_downloaded_files():
    """Convert all downloaded files to WAV, extract embeddings, build training arrays."""
    X, y_multilabel = [], []
    files = list(TEMP_DIR.glob("*"))
    # Group by class from filename prefix
    class_files = defaultdict(list)
    for f in files:
        for cls_name in TARGET_SPECIES:
            for species in TARGET_SPECIES[cls_name]:
                if f.name.startswith(species.replace(" ", "_")):
                    class_files[cls_name].append(f)
                    break
    
    print(f"\nProcessing {sum(len(v) for v in class_files.values())} files...")
    
    perch_model, _ = load_perch()
    
    for cls_name, flist in sorted(class_files.items()):
        print(f"  {cls_name}: {len(flist)} files")
        ok = 0
        for f in flist:
            conv = TEMP_DIR / f"conv_{f.stem}.wav"
            try:
                success, _ = convert_to_wav(f, conv)
                if not success:
                    continue
                emb = extract_embedding(perch_model, conv)
                X.append(emb)
                y_multilabel.append([cls_name])
                ok += 1
            except Exception as e:
                continue
            finally:
                if conv.exists():
                    conv.unlink()
        print(f"    → {ok} embeddings extracted")
    
    return np.array(X), y_multilabel

def add_background_from_archive():
    """Use confirmed birdnet clips from the archive as background negatives."""
    conn = get_archive_db()
    rows = conn.execute("""
        SELECT perch_embedding FROM clips
        WHERE source = 'birdnet' AND perch_embedding IS NOT NULL
        AND processing_status = 'done'
        LIMIT 500
    """).fetchall()
    conn.close()
    
    X, y = [], []
    for r in rows:
        emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
        if emb.shape == (1536,):
            X.append(emb)
            y.append(["background"])
    
    print(f"\nBackground from archive: {len(X)} clips")
    return np.array(X), y

def train_and_save(X, y_multilabel):
    """Train sklearn head and save to models/."""
    classes = ["background", "cicada_drone", "cricket_katydid", "frog", "grasshopper", "bee"]
    
    # Binarize
    mlb = MultiLabelBinarizer()
    mlb.fit([classes])
    y_bin = mlb.transform(y_multilabel)
    
    # Count
    print(f"\nTraining data:")
    for i, cls in enumerate(classes):
        print(f"  {cls}: {y_bin[:,i].sum():.0f} clips")
    
    # K-fold CV
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_f1s = []
    thresholds = {}
    all_true, all_prob = [], []
    
    for train_idx, test_idx in kf.split(X):
        X_tr, X_te = X[train_idx], X[test_idx]
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)
        
        clf = OneVsRestClassifier(
            LogisticRegression(C=0.1, class_weight='balanced',
                             solver='lbfgs', max_iter=2000, random_state=42)
        )
        clf.fit(X_tr_s, y_bin[train_idx])
        
        prob = clf.predict_proba(X_te_s)
        pred = (prob >= 0.5).astype(int)
        fold_f1s.append(f1_score(y_bin[test_idx], pred, average='macro', zero_division=0))
        all_true.append(y_bin[test_idx])
        all_prob.append(prob)
    
    print(f"\nCV Macro F1: {np.mean(fold_f1s):.4f} (+/-{np.std(fold_f1s):.4f})")
    
    # Full training
    final_scaler = StandardScaler()
    X_s = final_scaler.fit_transform(X)
    final_clf = OneVsRestClassifier(
        LogisticRegression(C=0.1, class_weight='balanced',
                         solver='lbfgs', max_iter=2000, random_state=42)
    )
    final_clf.fit(X_s, y_bin)
    
    # Per-class thresholds
    y_true_full = np.vstack(all_true)
    y_prob_full = np.vstack(all_prob)
    
    for i, cls in enumerate(classes):
        best_t, best_f1 = 0.5, 0
        for t in np.arange(0.1, 0.95, 0.05):
            p = (y_prob_full[:,i] >= t).astype(int)
            f = f1_score(y_true_full[:,i], p, zero_division=0)
            if f > best_f1:
                best_f1, best_t = f, t
        thresholds[cls] = round(best_t, 2)
        print(f"  {cls}: threshold={best_t:.2f}, F1={best_f1:.4f}")
    
    # Save
    version = "v0.1.0"
    artifact = MODELS_DIR / f"insectnet_perch_foundation_{version}.joblib"
    pkg = {
        "track": "insectnet",
        "version": version,
        "classes": classes,
        "thresholds": thresholds,
        "scaler": final_scaler,
        "classifier": final_clf,
        "is_multilabel": True,
        "cv_f1_mean": float(np.mean(fold_f1s)),
        "cv_f1_std": float(np.std(fold_f1s)),
        "per_class_f1": {cls: round(float(best_f1), 4) for cls, best_f1 in
                         zip(classes, [f1_score(y_true_full[:,i], 
                          (y_prob_full[:,i] >= thresholds[cls]).astype(int), zero_division=0)
                          for i, cls in enumerate(classes)])},
        "train_count": len(X),
        "trained_at": datetime.now().isoformat(),
        "dataset_hash": "foundation_public",
    }
    joblib.dump(pkg, artifact)
    print(f"\nSaved: {artifact}")
    return artifact

def score_archive(model_path):
    """Score all clips in the archive with the new model."""
    pkg = joblib.load(model_path)
    conn = get_archive_db()
    conn.execute("PRAGMA journal_mode=WAL")
    
    rows = conn.execute(
        "SELECT id, perch_embedding FROM clips WHERE perch_embedding IS NOT NULL"
    ).fetchall()
    
    updated = 0
    for r in rows:
        emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
        if emb.shape != (1536,):
            continue
        X = pkg["scaler"].transform(emb.reshape(1, -1))
        proba = pkg["classifier"].predict_proba(X)[0]
        
        active = []
        for i, cls in enumerate(pkg["classes"]):
            if proba[i] >= pkg["thresholds"].get(cls, 0.5):
                active.append(cls)
        
        pred_class = ", ".join(active) if active else "background"
        pred_conf = float(max(proba[i] for i, cls in enumerate(pkg["classes"]) if cls in active)) if active else 0.0
        
        conn.execute(
            "UPDATE clips SET model_version = ?, model_pred = ?, model_conf = ? WHERE id = ?",
            (pkg["version"], pred_class, pred_conf, r["id"])
        )
        updated += 1
    
    conn.commit()
    conn.close()
    print(f"\nScored {updated} clips in archive")
    return updated

def main():
    parser = argparse.ArgumentParser(description="Build Perch foundation model from public data")
    parser.add_argument("--skip-download", action="store_true", help="Skip iNat download (use existing temp files)")
    parser.add_argument("--skip-score", action="store_true", help="Skip scoring archive clips")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Perch Foundation Model Builder")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if args.dry_run:
        print("\nWould download ~250 clips per class from iNaturalist API")
        print(f"Target species: {sum(len(v) for v in TARGET_SPECIES.values())}")
        print("Would train 6-class multi-label sklearn head on Perch embeddings")
        print("Would save to models/insectnet_perch_foundation_v0.1.0.joblib")
        print("Would score all clips in archive.db")
        return
    
    # Step 1: Download
    if not args.skip_download:
        for cls_name, species_list in TARGET_SPECIES.items():
            download_inat_audio(cls_name, species_list)
    
    # Step 2: Process embeddings
    X_public, y_public = process_downloaded_files()
    
    # Step 3: Add background from existing archive birdnet clips
    X_bg, y_bg = add_background_from_archive()
    
    # Step 4: Combine and train
    X_all = np.vstack([X_public, X_bg]) if len(X_bg) > 0 else X_public
    y_all = y_public + y_bg
    print(f"\nTotal training: {len(X_all)} clips ({len(y_public)} public + {len(y_bg)} background)")
    
    artifact = train_and_save(X_all, y_all)
    
    # Step 5: Score archive
    if not args.skip_score:
        score_archive(artifact)
    
    print(f"\n{'=' * 60}")
    print(f"  Foundation model ready: {artifact}")
    print(f"  Launch review app to start reviewing with active learning priority.")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
