#!/usr/bin/env python3
"""
Pine Hollow Bioacoustics Data Factory — Streamlit Review App
=============================================================

Single-page, single-user verification of audio clips from BirdNET-Pi,
InsectNet, and Perch 2.0 inference pipeline.

╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  OPERATOR INVARIANTS — READ BEFORE EDITING OR RUNNING     ║
╠══════════════════════════════════════════════════════════════════╣
║  • Skip is an IN-MEMORY queue reorder. It MUST NOT write to    ║
║    the database. Only Confirm and Delete touch the DB.          ║
║  • human_tags is populated as a JSON array alongside            ║
║    comma-separated human_label on every Confirm.                ║
║  • tag_map.json is the SINGLE source of truth for label        ║
║    mapping. No hardcoded fallback dicts.                        ║
║  • The review app produces MULTI-LABEL tags via multiselect.    ║
║    Downstream consumers must split on commas.                   ║
║  • Load the pine-hollow-archive skill before operating.         ║
╚══════════════════════════════════════════════════════════════════╝

Run with:
    streamlit run review_app.py

Dependencies (install via pip):
    streamlit>=1.28
    numpy
    scipy
    matplotlib
    soundfile       (if WAV reading needed beyond librosa)
    librosa         (optional, for advanced spectrograms)

The app:
  - Loads clips from a SQLite archive
  - Prioritises the queue by active-learning value
  - Shows audio + spectrogram + metadata + tag panel
  - Supports confirm / correct / delete / skip with keyboard shortcuts
  - Offers batch auto-accept above a confidence threshold
"""

import os
import sys
import json
import sqlite3
import time
import io
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import streamlit as st

# ── Streamlit version compatibility shims ─────────────────────────
ST_MAJOR, ST_MINOR = map(int, st.__version__.split(".")[:2])
HAS_TOAST = (ST_MAJOR, ST_MINOR) >= (1, 35)
HAS_BORDER = (ST_MAJOR, ST_MINOR) >= (1, 35)

def _toast(msg, icon="✅"):
    """Safe toast wrapper — falls back to success/info on older Streamlit."""
    if HAS_TOAST:
        st.toast(msg, icon=icon)
    else:
        st.success(msg)

def _container(**kwargs):
    """Safe container wrapper — strips `border` kwarg on older Streamlit."""
    if not HAS_BORDER:
        kwargs.pop("border", None)
    return st.container(**kwargs)

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

ARCHIVE_PATH = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB_PATH = ARCHIVE_PATH / "archive.db"
COMMON_NAMES_PATH = ARCHIVE_PATH / "common_names.json"
TAG_MAP_PATH = ARCHIVE_PATH / "tag_map.json"

# Load common name cache (scientific → common)
def load_common_names():
    if COMMON_NAMES_PATH.exists():
        with open(COMMON_NAMES_PATH) as f:
            return json.load(f)
    return {}

# Load tag map
def load_tag_map():
    if TAG_MAP_PATH.exists():
        with open(TAG_MAP_PATH) as f:
            data = json.load(f)
        return data.get("tags", {})
    return {}

# Load and invert tag map for autosuggest
def build_tag_lookup():
    """Build flat species→tag lookup from hierarchical tag_map.json.
    Also returns the set of all universal tags for the correct picker.
    """
    tag_data = load_tag_map()
    species_to_tag = {}  # "Gallus gallus" → "chicken"
    all_tags = set()
    for tag_name, tag_info in tag_data.items():
        all_tags.add(tag_name)
        for species in tag_info.get("perch_labels", []):
            species_to_tag[species] = tag_name
    return species_to_tag, sorted(all_tags)

# Weights for active learning composite score
AL_WEIGHT_MARGIN = 1.0       # low margin -> uncertain -> high priority
AL_WEIGHT_SURPRISE = 2.0     # Perch predicts unknown species -> high priority
AL_WEIGHT_NOVELTY = 1.5      # far from confirmed embeddings -> high priority
AL_WEIGHT_CHRONO = 0.1       # oldest first as tiebreaker

# ──────────────────────────────────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    """Return a read‑only connection (with row factory)."""
    if "db" not in st.session_state:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        st.session_state.db = conn
    return st.session_state.db


def get_cursor() -> sqlite3.Cursor:
    return get_db().cursor()


# ──────────────────────────────────────────────────────────────────────
# Active‑learning queue builder
# ──────────────────────────────────────────────────────────────────────


def compute_active_learning_scores(embeddings, labels, confidences, perch_preds, known_classes):
    """
    Compute composite priority scores for all unreviewed clips.

    Parameters
    ----------
    embeddings : list[np.ndarray]        — 1536‑dim Perch embeddings
    labels     : list[str]               — source label (species)
    confidences: list[float]             — source confidence
    perch_preds: list[list[tuple]]       — [(species, conf), …] top‑50
    known_classes: set[str]              — model's known species set

    Returns
    -------
    scores : np.ndarray  (higher = review sooner)
    """
    n = len(embeddings)
    scores = np.zeros(n)

    # 1. Margin sampling  (higher = more certain = lower priority)
    for i, (preds, conf) in enumerate(zip(perch_preds, confidences)):
        # Sort by confidence descending
        sorted_preds = sorted(preds, key=lambda x: x.get("confidence", 0), reverse=True) if preds else []
        if len(sorted_preds) >= 2:
            margin = sorted_preds[0]["confidence"] - sorted_preds[1]["confidence"]
        else:
            margin = 1.0  # already certain
        scores[i] += AL_WEIGHT_MARGIN * (1.0 - margin)  # low margin -> high priority

    # 2. Perch surprise  — top Perch pred not in known_classes
    for i, preds in enumerate(perch_preds):
        sorted_preds = sorted(preds, key=lambda x: x.get("confidence", 0), reverse=True) if preds else []
        if sorted_preds:
            top_species = sorted_preds[0].get("species", "")
            if top_species not in known_classes:
                scores[i] += AL_WEIGHT_SURPRISE

    # 3. Embedding novelty — cosine distance to nearest confirmed
    confirmed_rows = get_confirmed_embeddings()
    if len(confirmed_rows) > 0:
        conf_embs = np.array([r[0] for r in confirmed_rows])
        conf_scores = np.array([r[1] for r in confirmed_rows])
        for i, emb in enumerate(embeddings):
            if emb.ndim == 1 and emb.shape[0] > 0:
                emb_norm = emb / (np.linalg.norm(emb) + 1e-12)
                # Cosine distances to all confirmed clips
                sims = conf_embs @ emb_norm  # dot product (unit vectors)
                dists = 1.0 - sims
                min_dist = np.min(dists)
                scores[i] += AL_WEIGHT_NOVELTY * min_dist

    return scores


def get_confirmed_embeddings():
    """Return list of (embedding, confidence) for all confirmed clips."""
    cur = get_cursor()
    rows = cur.execute(
        "SELECT perch_embedding FROM clips "
        "WHERE review_status IN ('confirmed', 'corrected') "
        "AND perch_embedding IS NOT NULL"
    ).fetchall()
    result = []
    for r in rows:
        try:
            emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            if emb.shape == (1536,):
                emb = emb / (np.linalg.norm(emb) + 1e-12)
                result.append((emb, 1.0))
        except Exception:
            continue
    return result


def load_queue(progress_callback=None):
    """
    Load all unreviewed clips, compute active‑learning scores, sort.
    Returns list of clip dicts sorted by priority (highest first).
    """
    cur = get_cursor()

    # Fetch all unreviewed clips — matching our archive schema
    rows = cur.execute("""
        SELECT id, file_path, source, source_label, source_conf,
               perch_top10, perch_top50, perch_embedding,
               duration_s, recorded_at, pulled_at
        FROM clips
        WHERE review_status = 'unreviewed' AND processing_status = 'done'
        ORDER BY pulled_at ASC
    """).fetchall()

    if not rows:
        return []

    clips = []
    embeddings = []
    perch_preds_list = []
    confidences = []
    labels = []

    for r in rows:
        clip = dict(r)
        # Parse perch predictions JSON
        try:
            pp = json.loads(r["perch_top10"] or "[]")
            clip["perch_top10"] = pp[:10]
        except (json.JSONDecodeError, TypeError):
            clip["perch_top10"] = []
            pp = []

        # Parse embedding
        emb = None
        if r["perch_embedding"]:
            try:
                emb = np.frombuffer(r["perch_embedding"], dtype=np.float32)
            except Exception:
                emb = np.zeros(1536, dtype=np.float32)
        else:
            emb = np.zeros(1536, dtype=np.float32)

        clips.append(clip)
        embeddings.append(emb)
        perch_preds_list.append(pp)
        confidences.append(r["source_conf"] or 0.0)
        labels.append(r["source_label"] or "")

        if progress_callback:
            progress_callback(len(clips), len(rows))

    # Known classes: union of all source labels in the archive
    known_classes = get_known_classes(cur)

    if len(clips) > 0:
        scores = compute_active_learning_scores(
            embeddings, labels, confidences,
            perch_preds_list, known_classes
        )
        # Sort descending by score; chronological tiebreaker
        indices = np.argsort(-scores)
        clips = [clips[i] for i in indices]

    return clips


def get_known_classes(cur):
    """Return set of all distinct source labels in the archive."""
    rows = cur.execute(
        "SELECT DISTINCT source_label FROM clips WHERE source_label IS NOT NULL"
    ).fetchall()
    return {r["source_label"] for r in rows if r["source_label"]}


# ──────────────────────────────────────────────────────────────────────
# Spectrogram generation
# ──────────────────────────────────────────────────────────────────────


def generate_spectrogram(file_path: Path, nfft=2048, hop_length=512) -> Optional[io.BytesIO]:
    """
    Generate a spectrogram image from an audio file using matplotlib.

    Supports .mp3 (via ffmpeg fallback) and .wav (via scipy).
    Returns a BytesIO PNG buffer or None on failure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal as scipy_signal

    try:
        fp = str(file_path)
        # Try scipy.io.wavfile for .wav
        if file_path.suffix.lower() in (".wav",):
            from scipy.io import wavfile
            rate, data = wavfile.read(fp)
            if data.ndim > 1:
                data = data.mean(axis=1)  # mono mix
            data = data.astype(np.float32) / (np.iinfo(data.dtype).max + 1)
        else:
            # For .mp3 use ffmpeg subprocess (librosa is broken in this env)
            import subprocess
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                subprocess.run(
                    ["ffmpeg", "-i", fp, "-ac", "1", "-f", "wav", "-y", tmp_path],
                    capture_output=True, timeout=30, check=True
                )
                from scipy.io import wavfile
                rate, data = wavfile.read(tmp_path)
                data = data.astype(np.float32) / (np.iinfo(data.dtype).max + 1)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # Compute spectrogram
        f, t, Sxx = scipy_signal.spectrogram(
            data, rate, nperseg=nfft, noverlap=nfft - hop_length
        )
        Sxx_db = 10 * np.log10(Sxx + 1e-10)

        fig, ax = plt.subplots(figsize=(10, 3))
        ax.pcolormesh(t, f, Sxx_db, shading="gouraud", cmap="inferno")
        ax.set_ylabel("Frequency (Hz)")
        ax.set_xlabel("Time (s)")
        ax.set_title("Spectrogram")
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as exc:
        st.warning(f"Spectrogram generation failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────
# UI helpers
# ──────────────────────────────────────────────────────────────────────


def inject_keyboard_shortcuts():
    """
    Inject JavaScript keyboard shortcuts via st.markdown.
    
    Keys:
      Space → Play/Pause
      1     → Confirm
      2     → Correct
      3     → Delete
      4     → Skip
    """
    js = """
    <script>
    document.addEventListener('keydown', function(e) {
        // Don't hijack typing in text inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }
        const btn = (key) => document.querySelector(`[data-sk="${key}"]`);
        switch(e.code) {
            case 'Space':
                e.preventDefault();
                const playBtn = btn('play');
                if (playBtn) playBtn.click();
                break;
            case 'Digit1':
                const c = btn('confirm');
                if (c) c.click();
                break;
            case 'Digit3':
                const del = btn('delete');
                if (del) del.click();
                break;
            case 'Digit4':
                const s = btn('skip');
                if (s) s.click();
                break;
        }
    });
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)


def format_confidence(val: float) -> str:
    """Format a confidence score as percentage string."""
    return f"{val * 100:.1f}%"


def show_sidebar_stats(clip_idx: int, total: int, session_start: float):
    """Sidebar with progress and session stats."""
    elapsed = time.time() - session_start
    elapsed_str = str(timedelta(seconds=int(elapsed)))

    with st.sidebar:
        st.markdown("### 🎯 Progress")
        st.progress(clip_idx / total if total > 0 else 0.0)
        st.metric("Reviewed", f"{clip_idx} / {total}")
        st.metric("Session", elapsed_str)

        # Per‑session counts
        counts = st.session_state.get("session_counts", {})
        col1, col2 = st.columns(2)
        col1.metric("✅ Confirm", counts.get("confirmed", 0))
        col2.metric("🗑️ Deleted", counts.get("deleted", 0))
        col1.metric("⏭️ Skipped", counts.get("skipped", 0))

        st.markdown("---")
        st.markdown("### ⌨️ Shortcuts")
        st.markdown("""
        - **Space** — Play/Pause
        - **1** — Confirm
        - **3** — Delete
        - **4** — Skip
        """)
        
        # Retrain button — always available after 10+ reviews
        counts = st.session_state.get("session_counts", {})
        total = sum(counts.values())
        if total >= 10:
            st.markdown("---")
            st.markdown("### 🧠 Retrain")
            if st.button(f"🔄 Retrain ({total} reviewed)", use_container_width=True):
                import subprocess
                with st.spinner("Training insectnet…"):
                    subprocess.run(
                        ["python3", "scripts/retrain.py", "--track", "insectnet"],
                        cwd=str(ARCHIVE_PATH), capture_output=True, text=True, timeout=120
                    )
                _toast("Retrained!", icon="✅")


def main():
    st.set_page_config(
        page_title="Pine Hollow Bioacoustics — Review",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Initialise session state ──────────────────────────────────
    if "queue" not in st.session_state:
        st.session_state.queue = []
    if "queue_idx" not in st.session_state:
        st.session_state.queue_idx = 0
    if "session_start" not in st.session_state:
        st.session_state.session_start = time.time()
    if "session_counts" not in st.session_state:
        st.session_state.session_counts = {
            "confirmed": 0, "corrected": 0, "deleted": 0, "skipped": 0
        }
    if "batch_mode" not in st.session_state:
        st.session_state.batch_mode = False
    if "batch_threshold" not in st.session_state:
        st.session_state.batch_threshold = 0.95
    if "running_batch" not in st.session_state:
        st.session_state.running_batch = False

    # ── Page title ────────────────────────────────────────────────
    st.title("🐦 Pine Hollow Bioacoustics — Data Factory Review")
    st.caption("Verify species labels from BirdNET-Pi, InsectNet, and Perch 2.0")

    # ── Inject keyboard shortcuts ─────────────────────────────────
    inject_keyboard_shortcuts()

    # ── Check archive exists ──────────────────────────────────────
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Make sure the archive is accessible.")
        st.info("Expected path: " + str(DB_PATH.resolve()))
        return

    # ── Load / reload queue ───────────────────────────────────────
    if st.button("🔄 Load Queue", type="primary", use_container_width=True):
        with st.spinner("Loading queue…"):
            st.session_state.queue = load_queue()
            st.session_state.queue_idx = 0
            st.session_state.session_start = time.time()
            st.rerun()

    # Auto‑load on first run if queue is empty
    if not st.session_state.queue and DB_PATH.exists():
        st.info("Click **Load Queue** to begin reviewing.")
        # Show batch settings even before loading
        show_batch_controls()
        return

    queue = st.session_state.queue
    queue_idx = st.session_state.queue_idx

    if not queue or queue_idx >= len(queue):
        if queue:
            st.success("🎉 All clips reviewed! Load the queue again to check for new clips.")
        else:
            st.info("No unreviewed clips in the archive.")
        
        # Offer retrain after a session
        counts = st.session_state.get("session_counts", {})
        total_actions = sum(counts.values())
        if total_actions >= 10:
            st.markdown("### 🧠 Retrain Models")
            st.caption(f"{total_actions} clips reviewed this session — ready to retrain.")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔄 Retrain InsectNet", use_container_width=True):
                    with st.spinner("Training insectnet model…"):
                        import subprocess
                        subprocess.run(
                            ["python3", "scripts/retrain.py", "--track", "insectnet", "--compare"],
                            cwd=str(ARCHIVE_PATH), capture_output=True, text=True, timeout=120
                        )
                    _toast("InsectNet retrained!", icon="✅")
                    st.rerun()
            with col_b:
                if st.button("🔄 Retrain All Tracks", use_container_width=True):
                    with st.spinner("Training all tracks…"):
                        import subprocess
                        subprocess.run(
                            ["python3", "scripts/retrain.py", "--all-tracks"],
                            cwd=str(ARCHIVE_PATH), capture_output=True, text=True, timeout=300
                        )
                    _toast("All tracks retrained!", icon="✅")
                    st.rerun()
        
        show_batch_controls()
        show_sidebar_stats(0, 0, st.session_state.session_start)
        return

    # ── Batch auto‑accept ─────────────────────────────────────────
    if st.session_state.batch_mode and not st.session_state.running_batch:
        st.session_state.running_batch = True
        batch_accepted = 0
        with st.spinner("Running batch auto‑accept…"):
            remaining = []
            for clip in queue:
                max_conf = max(
                    clip.get("source_conf") or 0,
                    max((d.get("confidence", 0) for d in clip.get("perch_top10", [])), default=0)
                )
                if max_conf >= st.session_state.batch_threshold:
                    # Auto-confirm with auto-derive (same logic as manual confirm)
                    conn = get_db()
                    source_label = clip.get("source_label") or ""
                    # Auto-derive broad tags from source_label via tag_map
                    species_to_tag, _ = build_tag_lookup()
                    all_tags = [source_label]
                    if source_label in species_to_tag:
                        derived = species_to_tag[source_label]
                        if derived not in all_tags:
                            all_tags.append(derived)
                    human_label = ", ".join(all_tags)
                    conn.execute(
                        "UPDATE clips SET review_status = 'confirmed', "
                        "human_label = ?, "
                        "human_tags = json(?), "
                        "reviewed_at = datetime('now', 'localtime') "
                        "WHERE id = ?", (human_label, json.dumps(all_tags), clip["id"])
                    )
                    conn.commit()
                    batch_accepted += 1
                else:
                    remaining.append(clip)
            st.session_state.queue = remaining
            st.session_state.queue_idx = 0
            st.session_state.running_batch = False
            if batch_accepted:
                _toast(f"Batch auto‑accepted {batch_accepted} clips above {st.session_state.batch_threshold:.0%}", icon="✅")
            st.rerun()

    # ── Current clip ──────────────────────────────────────────────
    clip = queue[queue_idx]
    clip_path = ARCHIVE_PATH / clip.get("file_path", "")

    # ── Stats sidebar ─────────────────────────────────────────────
    show_sidebar_stats(queue_idx, len(queue), st.session_state.session_start)

    # ── Batch controls in main area ───────────────────────────────
    show_batch_controls()

    # ── Main layout: two columns ──────────────────────────────────
    left_col, right_col = st.columns([5, 6], gap="medium")

    with left_col:
        st.markdown("### 🔊 Audio")
        # Audio player
        if clip_path.exists():
            audio_bytes = clip_path.read_bytes()
            # Infer format from file extension
            clip_fmt = "mpeg" if str(clip_path).lower().endswith(".mp3") else "wav"
            st.audio(audio_bytes, format="audio/" + clip_fmt)
        else:
            st.warning(f"Audio file not found: {clip_path}")

        # Spectrogram
        st.markdown("### 📊 Spectrogram")
        spec_key = f"spec_{clip['id']}"
        if spec_key not in st.session_state:
            st.session_state[spec_key] = None
        if st.session_state[spec_key] is None:
            with st.spinner("Generating spectrogram…"):
                spec_buf = generate_spectrogram(clip_path)
                if spec_buf:
                    st.session_state[spec_key] = spec_buf
        if st.session_state[spec_key]:
            st.image(st.session_state[spec_key], use_container_width=True)
        else:
            st.caption("Spectrogram unavailable for this clip.")

    with right_col:
        st.markdown("### 🏷️ Labels & Tags")

        # ── Model prediction ───────────────────────────────────────
        model_pred = clip.get("model_pred")
        model_conf = clip.get("model_conf")
        if model_pred:
            with _container(border=True):
                conf_str = f"{model_conf*100:.0f}%" if model_conf else "?"
                st.markdown(f"**🤖 Factory predicts:** `{model_pred}` ({conf_str})")

        # ── Metadata box ──────────────────────────────────────────
        with _container(border=True):
            meta_col1, meta_col2 = st.columns(2)
            meta_col1.metric("Clip ID", f"#{clip['id']}")
            source_display = clip.get("source", "unknown")
            icon = "🐦" if source_display == "birdnet" else "🐛"
            meta_col1.caption(f"{icon} Source: {source_display}")
            meta_col2.metric("Duration", f"{clip.get('duration_s', 0):.1f}s" if clip.get("duration_s") else "—")
            timestamp = clip.get("recorded_at") or clip.get("pulled_at", "")
            if timestamp:
                meta_col2.caption(f"Recorded: {timestamp[:16]}")

        # ── Source label (BirdNET or InsectNet) ────────────────────
        source_label = clip.get("source_label")
        source_conf = clip.get("source_conf")
        source = clip.get("source", "")
        if source_label:
            with _container(border=True):
                cols = st.columns([3, 1])
                if source == "birdnet":
                    cols[0].markdown(f"**BirdNET:** {source_label}")
                    if source_conf:
                        cols[1].metric("Confidence", format_confidence(source_conf))
                    st.caption("🐦 BirdNET-Pi detection")
                elif source == "insectnet":
                    cols[0].markdown(f"**InsectNet:** {source_label}")
                    if source_conf:
                        cols[1].metric("Confidence", format_confidence(source_conf))
                    st.caption("🐛 InsectNet sidecar capture")
                else:
                    cols[0].markdown(f"**Label:** {source_label}")
                    if source_conf:
                        cols[1].metric("Confidence", format_confidence(source_conf))
        
        # ── Perch top-10 ──────────────────────────────────────────
        with _container(border=True):
            st.markdown("**Perch 2.0 — Top Predictions**")
            perch_top = clip.get("perch_top10", [])
            if perch_top:
                # Load tag lookup for common names
                # Load common name cache + tag map
                common_names = load_common_names()
                species_to_tag, _ = build_tag_lookup()
                st.caption(f"📖 Common names loaded: {len(common_names)}")
                for entry in perch_top[:5]:
                    species = entry.get("species", "?")
                    conf = entry.get("confidence", 0)
                    # Common name lookup
                    display = common_names.get(species) or species_to_tag.get(species) or species
                    cols = st.columns([3, 1, 2])
                    cols[0].text(display[:40])
                    cols[1].text(f"{conf*100:.1f}%")
                    cols[2].progress(conf)
                if len(perch_top) > 5:
                    with st.expander(f"+{len(perch_top)-5} more predictions"):
                        for entry in perch_top[5:]:
                            species = entry.get("species", "?")
                            conf = entry.get("confidence", 0)
                            common = species_to_tag.get(species, "")
                            display = species[:35]
                            if common:
                                display += f"  ({common})"
                            cols = st.columns([3, 1])
                            cols[0].text(species[:40])
                            cols[1].text(f"{conf*100:.1f}%")
            else:
                st.caption("No Perch predictions for this clip.")

        # ── Tag panel — two-tier with common names ──────────────────
        species_to_tag, all_known_tags = build_tag_lookup()
        common_names = load_common_names()
        source_label = clip.get("source_label", "")
        perch_hints = clip.get("perch_top10", [])
        
        # Helper: scientific name → readable display
        def tag_display(name):
            """Show common name if available, e.g. 'Carolina Wren (T. ludovicianus)'.
            Falls back to cleaned scientific name with genus capitalized."""
            # Try case-insensitive common name lookup
            clean = name.replace('_', ' ').strip()
            common = common_names.get(clean) or common_names.get(name)
            if not common:
                # Try case-insensitive
                cn_lower = {k.lower(): v for k, v in common_names.items()}
                common = cn_lower.get(clean.lower())
            if common:
                return f"{common} ({clean})"
            # No common name — show cleaned scientific name
            if ' ' in clean:
                parts = clean.split(' ', 1)
                return f"{parts[0].capitalize()} {parts[1]}"
            return clean.replace('_', ' ').capitalize()
        
        # Species-level options: source_label + Perch top-3, with common names
        species_options = []
        species_labels = {}  # display → raw scientific name for lookup
        if source_label:
            display = tag_display(source_label)
            species_options.append(display)
            species_labels[display] = source_label
        if perch_hints:
            for entry in perch_hints[:3]:
                sp = entry.get("species", "")
                if not sp: continue
                display = tag_display(sp)
                if display not in species_options:
                    species_options.append(display)
                    species_labels[display] = sp
        
        # Class-level options: broad tags + acoustic classes
        acoustic_classes = {"cicada_drone", "cricket_katydid", "frog",
                           "grasshopper", "bee", "dog", "chicken",
                           "human_voice", "mechanical", "wind_rain",
                           "background"}
        class_options = sorted(set(all_known_tags) | acoustic_classes)
        class_options = [t for t in class_options if t not in species_options
                        and t not in species_labels]
        
        # Combined tag list
        tag_options = species_options + class_options
        
        # Default: source_label display + Perch top-1
        default_selection = []
        if source_label:
            default_selection.append(tag_display(source_label))
        if perch_hints:
            top_display = tag_display(perch_hints[0].get("species", ""))
            if top_display and top_display not in default_selection:
                default_selection.append(top_display)
        
        tag_options = [t for t in tag_options if t]
        default_selection = [t for t in default_selection if t]

        with _container(border=True):
            st.markdown("**🏷️ Select tags that apply**")
            selected_tags = st.multiselect(
                "Tags for this clip",
                options=tag_options,
                default=default_selection,
                key="tag_multiselect",
                label_visibility="collapsed",
            )
            # Custom tag: type and press Enter to add
            extra = st.text_input(
                "➕ Custom tag",
                key="extra_tag",
                placeholder="type something not in the list",
                label_visibility="collapsed",
            )
            if selected_tags:
                display = list(selected_tags)
                if extra.strip():
                    display.append(extra.strip())
                # Show auto-derived tags that will be added on save
                species_to_tag, _ = build_tag_lookup()
                derived = set()
                for tag in display:
                    if tag in species_to_tag:
                        derived.add(species_to_tag[tag])
                derived_display = [d for d in sorted(derived) if d not in display]
                if derived_display:
                    st.caption(f"Will save: {', '.join(display)}  [+ {', '.join(derived_display)} auto]")
                else:
                    st.caption(f"Will save: {', '.join(display)}")

        # ── Action buttons ────────────────────────────────────────
        st.markdown("### ⚡ Actions")
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

        with btn_col1:
            confirm_btn = st.button(
                "✅ Confirm\n[1]", key="confirm_btn",
                use_container_width=True,
                help="Save selected tags and advance"
            )
        with btn_col2:
            delete_btn = st.button(
                "🗑️ Delete\n[3]", key="delete_btn",
                use_container_width=True,
                help="Mark as false positive"
            )
        with btn_col3:
            skip_btn = st.button(
                "⏭️ Skip\n[4]", key="skip_btn",
                use_container_width=True,
                help="Skip for now, revisit later"
            )
        with btn_col4:
            undo_btn = False
            if st.session_state.get("undo_clip_id"):
                undo_btn = st.button(
                    "↩️ Undo", key="undo_btn",
                    use_container_width=True,
                    help=f"Undo last {st.session_state.get('undo_action', 'action')}"
                )

        # ── Undo handler (before regular actions) ─────────────────
        if undo_btn:
            undo_id = st.session_state.get("undo_clip_id")
            if undo_id:
                conn = get_db()
                conn.execute(
                    "UPDATE clips SET review_status='unreviewed', human_label=NULL, "
                    "human_tags=NULL, reviewed_at=NULL WHERE id=?",
                    (undo_id,)
                )
                conn.commit()
                # Restore clip to front of queue
                restored = [c for c in st.session_state.queue if c["id"] == undo_id]
                if not restored:
                    # Reload it from DB
                    row = conn.execute(
                        "SELECT id, file_path, source, source_label, source_conf, "
                        "perch_top10, perch_top50, perch_embedding, "
                        "duration_s, recorded_at, pulled_at "
                        "FROM clips WHERE id=?", (undo_id,)
                    ).fetchone()
                    if row:
                        restored = [dict(row)]
                if restored:
                    st.session_state.queue.insert(0, restored[0])
                st.session_state.queue_idx = 0
                st.session_state.undo_clip_id = None
                st.session_state.undo_action = None
                # Decrement session count
                counts = st.session_state.session_counts
                undo_action = st.session_state.get("undo_action", "confirmed")
                if counts.get(undo_action, 0) > 0:
                    counts[undo_action] -= 1
                st.rerun()

        # ── Handle button actions ─────────────────────────────────
        action = None
        if confirm_btn:
            action = "confirmed"
        elif delete_btn:
            action = "deleted"
        elif skip_btn:
            action = "skipped"

        if action:
            # Update session counts for all actions (including skip)
            counts = st.session_state.session_counts
            counts[action] = counts.get(action, 0) + 1

            # Only confirmed and deleted touch the database.
            # Skip is a pure in-memory queue reorder — it must NOT write
            # review_status, or load_queue() will permanently drop it on reload.
            #
            # INVARIANT: Do NOT add a DB write for the "skipped" action.
            # This was a bug fixed June 1, 2026. Skipped clips would vanish
            # from the queue on the next Load Queue because load_queue()
            # filters WHERE review_status = 'unreviewed'.
            if action in ("confirmed", "deleted"):
                conn = get_db()
                human_label = None
                human_tags_json = None
                if action == "confirmed":
                    selected = st.session_state.get("tag_multiselect", [])
                    extra = st.session_state.get("extra_tag", "").strip()
                    # Translate common-name displays back to raw names.
                    # "Carolina Wren (Thryothorus ludovicianus)" → "Thryothorus ludovicianus"
                    all_tags = []
                    for tag in selected:
                        if " (" in tag and tag.endswith(")"):
                            all_tags.append(tag.split(" (")[-1][:-1])
                        else:
                            all_tags.append(tag)
                    if extra and extra not in all_tags:
                        all_tags.append(extra)
                    
                    # Auto-derive broad tags from species-level tags.
                    # If user tagged "Dryophytes chrysoscelis", the system
                    # automatically adds "frog" via tag_map.json. This keeps
                    # the dataset clean — user tags species, system handles
                    # taxonomy. No redundant manual tagging.
                    species_to_tag, _ = build_tag_lookup()
                    derived = set()
                    for tag in all_tags:
                        if tag in species_to_tag:
                            derived.add(species_to_tag[tag])
                    for d in sorted(derived):
                        if d not in all_tags:
                            all_tags.append(d)
                    
                    if all_tags:
                        human_label = ", ".join(all_tags)
                        human_tags_json = json.dumps(all_tags)
                    else:
                        human_label = clip.get("source_label")
                        human_tags_json = json.dumps([clip.get("source_label")])
                conn.execute(
                    "UPDATE clips SET review_status = ?, human_label = ?, "
                    "human_tags = ?, reviewed_at = datetime('now', 'localtime') "
                    "WHERE id = ?",
                    (action, human_label, human_tags_json, clip["id"]),
                )
                conn.commit()

            # Store undo info before moving to next clip
            if action in ("confirmed", "deleted"):
                st.session_state.undo_clip_id = clip["id"]
                st.session_state.undo_action = action
            
            # Move to next clip
            if action == "skipped":
                st.session_state.queue.append(st.session_state.queue.pop(queue_idx))
            else:
                st.session_state.queue.pop(queue_idx)
            st.rerun()


def show_batch_controls():
    """Render batch auto‑accept controls below the main layout."""
    with st.expander("⚙️ Batch Mode & Sorting", expanded=False):
        col_a, col_b, _ = st.columns([2, 3, 3])
        with col_a:
            st.session_state.batch_mode = st.checkbox(
                "Auto‑accept high‑confidence clips",
                value=st.session_state.batch_mode,
            )
        with col_b:
            if st.session_state.batch_mode:
                st.session_state.batch_threshold = st.slider(
                    "Confidence threshold",
                    min_value=0.80, max_value=1.0, value=0.95, step=0.01,
                    format="%.0%%",
                )
        # Sort indicator
        st.caption("📊 Queue sorted by **Active Learning Priority**: margin sampling + Perch surprise + embedding novelty → chronological")


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
