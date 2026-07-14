# Pine Hollow Commons Lab v0.1

> **Automation is now active:** see [`commons_lab_automation_v0.2.md`](commons_lab_automation_v0.2.md) for the installed timer, run ledger, CPU quality metrics, operations, and expansion sequence.

## Purpose

Pine Hollow Commons Lab is a local-first physical-ecology data factory. It records what happened, the evidence for it, what models or people asserted, what decisions were made, which interventions were executed, and what outcomes followed.

This v0.1 foundation extends the existing bioacoustics archive. It does not replace or rewrite the current `clips`, `label_events`, model registry, review app, BirdNET-Pi pipeline, Discord agents, or website.

## Research boundary

The system keeps these layers separate:

1. **Evidence** — original sensor media, measurements, field notes, checksums, transformations, and provenance.
2. **Assertions** — model, sensor, rule, external-dataset, or human interpretations of evidence.
3. **Decisions and interventions** — what was proposed, approved, declined, executed, or failed.
4. **Outcomes** — observations linked to an intervention without overstating causality.
5. **Publications** — explicit records of what was reviewed and exposed on a public surface.

A model prediction is not a human label. A recommendation is not an executed action. An associated outcome is not automatically caused by an intervention.

## Current local capacity verified 2026-07-14

- Host: Athena under WSL2
- GPU: NVIDIA GeForce RTX 4090, 24,564 MiB total VRAM
- CPU: Intel Core i9-14900KF, 32 logical CPUs visible to WSL
- WSL memory: 15 GiB
- WSL root filesystem: about 669 GiB available during the audit
- Windows C: about 410 GiB available during the audit
- Camera: EMEET SmartCam Nova 4K
- Camera bridge: Windows DirectShow through Windows FFmpeg
- WSL has no `/dev/video*` camera node
- Archive: SQLite `archive.db`, WAL mode, integrity check `ok`

These figures are an audit snapshot, not durable specifications.

## Schema

Current Commons schema version: **2**.

All new tables use a `commons_` prefix and are additive:

- `commons_schema_versions`
- `commons_sites`
- `commons_sensors`
- `commons_deployments`
- `commons_events`
- `commons_media`
- `commons_measurements`
- `commons_assertions`
- `commons_interventions`
- `commons_outcomes`
- `commons_publications`
- `commons_legacy_links`

The migration is idempotent. It does not alter legacy archive tables.

### Event defaults

New camera events default to:

```text
privacy_level      = private
review_state       = unreviewed
publication_state  = blocked
```

A database trigger prevents a non-public event from being marked publicly approved. Additional guards require published records to reference public-approved events, require withdrawal before event downgrade, and enforce that every deployed event's `site_id` matches its deployment.

### Idempotency

A media event identity is derived from:

```text
site + deployment-or-none + source + capture timestamp + event type + SHA-256
```

Site and source are always included, including for observations without a deployment, so identical evidence cannot collapse across site or provenance boundaries. Deployed records created by the earliest v0.1 build retain backward retry lookup compatibility.

Retries return the original event and media IDs instead of duplicating evidence.

## Window camera deployment

### Registered identity

```text
sensor_id:      emeet-window-camera
deployment_id:  window-view-v1
site_id:        pine-hollow-private
host:           Athena-Windows
transport:      Windows DirectShow
```

### Capture policy

- Capture a normalized still, not continuous video.
- Apply a 180-degree rotation during capture.
- Retain only the normalized frame for this deployment.
- Record the transform in `commons_media.transform_json`.
- Raw imagery remains private.
- No camera image is published automatically.

### Hardware proof

A 3840×2160 frame was captured and ingested into a temporary database. The first immediate frame was severely overexposed. Adding a two-second warmup allowed webcam auto-exposure and white balance to settle before retention.

The corrected view is upright and contains:

- mature tree canopy;
- understory and garden vegetation;
- outbuildings;
- fencing;
- yard equipment and infrastructure.

The upper canopy is suitable for initial qualitative work:

- canopy presence and broad leaf state;
- coarse motion/wind context;
- broad daylight and weather context;
- later fixed-view comparison.

It is not yet suitable for quantitative color phenology because highlights remain clipped in bright sky and foreground regions.

### Privacy assessment

The proof frame did not visibly contain people, faces, license plates, addresses, road traffic, computer screens, or obvious interior reflections. It does contain identifiable private structures, a building window, fencing, equipment, and yard layout.

Therefore:

- full frames remain private;
- future public use should prefer derived environmental state;
- a canopy-only region of interest may be defined later;
- a public crop still requires explicit review;
- no live public camera is part of v0.1.

## Commands

From the repository root:

```bash
# Add/update the schema only
python3 scripts/commons_lab_cli.py init

# Register the camera without capturing
python3 scripts/commons_lab_cli.py register-camera

# Capture, rotate, and ingest one private frame
python3 scripts/commons_lab_cli.py capture-camera

# Inspect table counts and latest event
python3 scripts/commons_lab_cli.py status
```

By default camera images are stored under the existing ignored `temp/` tree:

```text
temp/commons_lab/window_camera/YYYY-MM-DD/
```

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile commons_lab/*.py scripts/commons_lab_cli.py
python3 scripts/audit_labels.py
```

The v0.1 test suite verifies:

- additive migration;
- migration idempotency;
- preservation of a legacy table row;
- camera sensor/deployment registration;
- SHA-256 evidence provenance;
- explicit 180-degree transform metadata;
- private/unreviewed/blocked defaults;
- transactional, concurrent-safe idempotent media ingest;
- database rejection of public approval for private events.

### Pre-existing relational issue

`PRAGMA foreign_key_check` reports 32 legacy `label_events → clips` orphan references (label-event rowids 87 through 118). The identical 32 violations exist in the consistent pre-v0.1 backup; all legacy table row counts also match the backup. Commons Lab tables report zero foreign-key violations. This build deliberately did not delete or rewrite those historical provenance rows.

## Relationship to existing systems

### Bioacoustics archive

Existing `clips` and `label_events` remain operational. Future backfill should use `commons_legacy_links` rather than rewriting clip IDs or deleting existing history.

### BirdNET-Pi and InsectNet

No remote Pi service, recorder, watcher, captured file, or model was touched during v0.1. Future ingestion must remain read-only from the recorder's perspective.

### Website

The website remains as designed. It is not the Commons Lab administration UI. A later exporter may produce a reviewed, privacy-stripped static payload, but v0.1 publishes nothing.

### Discord

Discord remains a conversational dispatch layer. A later bridge may link a dispatch to an event or accept an explicit field note. Discord is not the evidence ledger.

### Holographic memory and Obsidian

The Holo should hold durable distilled facts, not every sensor event. Obsidian can hold human-readable daily or experiment summaries. The Commons tables hold queryable evidence and provenance.

## Near-term roadmap using existing hardware

### 0.1 — Foundation (this build)

- additive event/evidence/research schema;
- local private camera bridge;
- real frame capture and ingest;
- privacy publication guard;
- tests and operating notes.

### 0.2 — Stable visual baseline

- determine a fixed canopy region of interest;
- add exposure/quality metrics and reject unusable frames;
- capture at a conservative daylight cadence;
- retain calibration and camera-configuration history;
- compute simple image statistics before introducing a vision model.

### 0.3 — Existing audio linkage

- backfill current archive clips into `commons_events` through links, not replacement;
- preserve detector labels as model assertions;
- preserve human review as higher-authority assertions;
- introduce unbiased background samples only after privacy quarantine is implemented.

### 0.4 — Multimodal context

- attach local weather and Observatory context by time window;
- calculate dawn/sunset-relative time;
- associate camera conditions with acoustic events;
- preserve no-detection and ordinary conditions.

### 0.5 — Curation on Athena

- image/audio embeddings on the RTX 4090;
- novelty, disagreement, seasonal coverage, and quality queues;
- active-learning review selection;
- model and dataset manifests with hashes.

### 0.6 — Experiment registry

- define management interventions;
- record proposed versus executed actions;
- connect later measurements as associated outcomes;
- support small controlled comparisons without making causal claims automatically.

### 0.7 — Private/public projection

- generate a private lab status product;
- generate a separate privacy-stripped public payload;
- require review and policy checks before any website or dataset publication;
- keep the website's current visual design.

## Deferred deliberately

- continuous window video;
- live public camera;
- automatic website publishing;
- Discord automation;
- BirdNET-Pi changes;
- robotic control;
- Cosmos synthetic data;
- DeepStream deployment;
- Kubernetes, Airflow, or OSMO;
- major sensor purchases.

Those become useful only after the real evidence loop and research questions justify them.
