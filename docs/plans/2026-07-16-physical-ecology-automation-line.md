# Pine Hollow Physical-Ecology Automation Line Implementation Plan

> **For Hermes:** Implement test-first in visible phase checkpoints. Do not commit or push without explicit user instruction.

**Goal:** Build Phases 1–3 as an idempotent local automation line that imports field-listener evidence into the Pine Hollow Archive, attaches explicitly non-causal temporal context, and runs bounded CPU/GPU jobs with deep append-only records.

**Architecture:** Extend the additive `commons_*` schema. The field listener remains read-only and authoritative for capture/scoring evidence; the archive references retained evidence in place and records its own model/human/context assertions. A deterministic job ledger drives replay-safe stages. Continuous work remains CPU-light; GPU work is deferrable, allowlisted and bounded.

**Tech stack:** Python 3.11 standard library, SQLite WAL, systemd user units, FFmpeg/ffprobe, NVIDIA `nvidia-smi` preflight. No new Python dependencies, network services, framework, website changes, BirdNET-Pi changes or live model changes.

## Non-negotiable contracts

- Existing legacy archive tables are untouched.
- Existing user changes in `.gitignore`, `scripts/pull_clips.py`, and `scripts/review_app.py` are not overwritten.
- The field database and review evidence are opened/read only.
- Import recomputes evidence SHA-256 and deployed bundle IDs; mismatches fail closed.
- Every five-second model window remains explicit; a 15-second recording label never silently labels another span.
- Model, human and context assertions remain separate.
- Context links record relation, method and signed time offset; they do not assert causation.
- Jobs are allowlisted by code, deterministic, leased, retry-bounded and transition-audited.
- GPU execution is manual/deferrable by default and never continuous.
- Raw field/camera evidence remains private, unreviewed and publication-blocked.
- Research/development records are append-only in SQLite and mirrored by dated Markdown logs.

---

### Task 1: Add the automation schema migration

**Objective:** Add exact acoustic windows, event links, calibration queues, jobs, job transitions and research records without altering legacy data.

**Files:**
- Modify: `commons_lab/schema.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Write failing migration/idempotency/append-only tests.
2. Add schema version 4 tables and indices.
3. Add guards for immutable acoustic windows, event links, transitions and research records.
4. Re-run migration twice and verify legacy/Commons counts are unchanged.

### Task 2: Implement strict field-listener import

**Objective:** Register the microphone/deployment, import retained event/control WAVs idempotently, join field ledger + sidecar + bundle metadata, and preserve exact model windows/events.

**Files:**
- Create: `commons_lab/acoustic.py`
- Create: `scripts/run_data_factory.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Build a fixture field ledger, bundle checksum contract, sidecar and WAV.
2. Write failing tests for event/control import, retry, SHA mismatch, sidecar mismatch, unknown bundle and read-only source behavior.
3. Implement strict bundle-catalog parsing without loading model weights.
4. Import one recording as private `acoustic_recording` evidence.
5. Insert exact windows and source event IDs.
6. Insert one candidate model assertion per bundle while preserving uncalibrated score semantics.
7. Verify a replay creates no duplicate event/media/window/assertion.

### Task 3: Implement human review and calibration queues

**Objective:** Preserve append-only human confirmations and generate deterministic score-stratified review queues without changing deployed thresholds.

**Files:**
- Extend: `commons_lab/acoustic.py`
- Extend: `scripts/run_data_factory.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Write failing tests for human assertion append, correction-by-supersession, certainty gates and queue idempotency.
2. Implement `record_human_acoustic_review()` using `commons_assertions` with explicit reviewer, certainty, span and supersedes metadata.
3. Implement score-band queue generation for each bundle/class.
4. Ensure queue state is independent of training eligibility.
5. Report queue counts by class and score band.

### Task 4: Implement non-causal temporal context joins

**Objective:** Link acoustic events to nearest camera frames and timestamped Observatory snapshots within configurable tolerances.

**Files:**
- Create: `commons_lab/context.py`
- Extend: `scripts/run_data_factory.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Write failing timezone, nearest-event, tolerance and idempotency tests.
2. Implement ISO-8601 normalization and nearest Commons event selection.
3. Insert `nearest_visual_context` links with signed offset and method metadata.
4. Ingest a local Observatory JSON snapshot as private context evidence only when its `updated` time is within tolerance.
5. Link with `contemporaneous_environmental_context`; never infer cause.

### Task 5: Implement the bounded job factory

**Objective:** Provide deterministic enqueue, lease, heartbeat, retry, completion and transition history for CPU and GPU work.

**Files:**
- Create: `commons_lab/jobs.py`
- Create: `commons_lab/factory.py`
- Extend: `scripts/run_data_factory.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Write failing tests for deterministic enqueue, one-worker lease, expired-lease recovery, retry cap, allowlist enforcement and transition history.
2. Implement energy classes: `critical_continuous`, `scheduled_cpu`, `deferrable_gpu`, `manual_high_energy`.
3. Implement allowlisted handlers: field import, context join, SQLite integrity audit, GPU environment probe.
4. GPU preflight records device, free VRAM and utilization via `nvidia-smi`; no arbitrary DB-stored shell commands.
5. Implement one-cycle worker with lock, max-job limit and JSON status output.

### Task 6: Install the low-power automation line

**Objective:** Run import/context/integrity stages automatically while leaving GPU jobs manual/deferrable.

**Files:**
- Create: `deploy/systemd/pine-hollow-data-factory.service`
- Create: `deploy/systemd/pine-hollow-data-factory.timer`
- Create: `scripts/run_pine_hollow_data_factory.py`
- Test: `tests/test_data_factory.py`

**Steps:**
1. Add a shared non-blocking lock across manual and systemd entry points.
2. Add free-space and source-availability guards.
3. Schedule a bounded CPU cycle every ten minutes with `Persistent=false`.
4. Do not schedule GPU work.
5. Verify unit syntax and child-process resource boundaries.
6. Enable only after a dry run and one successful manual full cycle.

### Task 7: Deep records and operating documentation

**Objective:** Make practices, research, decisions, validation and recovery reconstructable.

**Files:**
- Create: `docs/physical_ecology_data_factory_architecture.md`
- Create: `docs/physical_ecology_data_factory_research_2026-07-16.md`
- Create: `docs/physical_ecology_data_factory_development_log_2026-07-16.md`
- Create: `docs/physical_ecology_data_factory_operations.md`
- Create: `docs/physical_ecology_data_factory_validation_2026-07-16.md`
- Update: `README.md` only if it can be done without conflicting with user changes.

**Steps:**
1. Record architecture, invariants, table dictionary and data flow.
2. Record official NVIDIA/SQLite/systemd/FAIR research sources and adoption boundaries.
3. Record every implementation decision, failed attempt and correction.
4. Document status, dry-run, manual cycle, review, recovery, retry, pause and rollback commands.
5. Record real test, migration, import, context and GPU-probe outputs.

### Task 8: Final release gate

**Objective:** Verify correctness without committing or publishing private evidence.

**Verification:**
- `python3 -m unittest discover -s tests -v`
- `python3 -m py_compile commons_lab/*.py scripts/*.py`
- `python3 scripts/audit_labels.py`
- `sqlite3 archive.db 'PRAGMA integrity_check; PRAGMA foreign_key_check;'`
- Run migration on a copy and compare legacy/Commons preexisting counts.
- Dry-run source discovery.
- Run one live import cycle twice; second run must be a no-op.
- Run context join twice; second run must be a no-op.
- Enqueue and run one SQLite integrity job and one GPU environment probe.
- `systemd-analyze --user verify deploy/systemd/pine-hollow-data-factory.{service,timer}`
- Verify timer/service health and field listener health after installation.
- Review `git diff`, secret scan and private-path boundaries.
- Independent spec and code-quality review must approve before completion.

## Rollback boundary

- Disable the new timer.
- New code and units can be removed without affecting BirdNET-Pi, the field listener, legacy clips or camera capture.
- Schema migration is additive. New tables can remain dormant; no rollback deletes evidence.
- No threshold/model/website changes are part of this release.
