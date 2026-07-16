# Physical-Ecology Data Factory Development Log — 2026-07-16

## Initial conditions

- Archive branch: `master`, three commits ahead of remote.
- Pre-existing user modifications preserved:
  - `.gitignore`
  - `scripts/pull_clips.py`
  - `scripts/review_app.py`
- Field-listener repository was clean.
- Website and BirdNET-Pi were outside implementation scope.
- No commit or push was authorized or performed.

## Planning

Saved implementation contract:

- `docs/plans/2026-07-16-physical-ecology-automation-line.md`

Core choices:

- extend `commons_*` rather than legacy `clips`;
- one Commons event per retained 15-second recording;
- explicit five-second score rows;
- separate model and human assertions;
- generic non-causal event links;
- deterministic job queue with immutable transition history;
- CPU timer only; explicit GPU worker.

## Test-first implementation

### Schema

Created failing tests for six missing tables and immutable research records. Added schema version 4:

- `commons_acoustic_windows`
- `commons_event_links`
- `commons_review_queue`
- `commons_jobs`
- `commons_job_transitions`
- `commons_research_records`

One broad patch failed validation because an insertion anchor was ambiguous. It changed no file. The schema edit was split into unique anchors and then applied successfully.

### Acoustic import

Created a complete fixture containing:

- retained WAV named by SHA-256;
- JSON sidecar;
- read-only field ledger;
- checksum-identified deployed bundle;
- three exact score windows;
- one source threshold event.

Implemented `commons_lab/acoustic.py` with strict joins, private in-place evidence registration, model assertions, score bands, human review, and correction-by-supersession.

A large test-file patch was rejected because an anchor matched twice. It changed no file. Because the test file was newly created in this work, it was rewritten once with the complete test suite.

### Temporal context

Implemented `commons_lab/context.py`:

- aware ISO-8601 parsing;
- same-site nearest-event selection;
- signed offset and tolerance;
- explicit non-causal metadata;
- immutable Observatory snapshot copies.

### Job ledger and factory

Implemented:

- `commons_lab/jobs.py`
- `commons_lab/factory.py`
- `scripts/run_data_factory.py`

Tested deterministic enqueue, energy/job allowlist, lease exclusion, expired-lease recovery, retry cap, lease-owner completion, CPU cycle replay, and explicit GPU lane.

Retry behavior was tightened with exponential backoff capped at five minutes.

### Scheduler watermark correction

The first live replay created an unnecessary field-import job because the source watermark included field database/WAL timestamps. Ordinary non-retained listener processing changes those files.

Correction:

- added a regression test that changes field database mtime;
- removed database/WAL state from the import watermark;
- retained WAV identities, sidecar hashes, and bundle manifests remain in the watermark.

After one compatibility job, the next live cycle created zero new jobs and ran nothing.

## Migration and backup

Before live migration, a SQLite backup was created:

```text
private/backups/archive-pre-data-factory-20260716T133038Z.db
```

- bytes: `46,477,312`
- SHA-256: `0c2c8c27273168c5b3dfec55a8706a640a9f600a13948e8c99b2b23e7b9d923d`

Migration was first tested against a SQLite backup copy. Existing table counts remained unchanged except the expected schema-version row.

## Legacy integrity finding

`PRAGMA foreign_key_check` reported 32 pre-existing violations before migration and the identical 32 after migration:

- child table: `label_events`
- rows: 87–118
- missing parent: `clips`

No new Commons table was involved. The data factory integrity handler now:

- fails on any `commons_*` foreign-key violation;
- reports legacy violation count and sample;
- does not claim the entire legacy archive has zero violations.

The legacy condition was not repaired because it predates and is outside this release.

## First live cycle

Results:

- 103 retained recordings imported;
- 618 exact windows inserted;
- 206 model assertions inserted;
- one immutable Observatory snapshot created;
- 11 visual links inserted;
- one environmental link inserted;
- SQLite integrity `ok`;
- Commons foreign-key violations: zero;
- GPU jobs automated: false.

## Explicit GPU lane

Ran `gpu_environment_probe` manually through a worker allowed to claim `deferrable_gpu` jobs.

Observed:

- GPU: NVIDIA GeForce RTX 4090
- total VRAM: 24,564 MiB
- free VRAM: 22,411 MiB
- utilization during probe: 12%
- driver: 610.62

No model inference or sustained GPU workload was started.

## Review queues

Initial deterministic score-band queues:

- ChickenNet: 12 recordings
- InsectNet: 29 recordings
- total: 41

No deployed threshold or training manifest changed.

## Service deployment

Installed `pine-hollow-data-factory.service` and `.timer` into the user systemd directory with Linux mode 0644. The sandboxed manual service cycle and immediate timer-triggered cycle both completed successfully and created no new work. The timer is enabled on a ten-minute cadence. A post-deployment listener check reported connected capture, zero sequence gaps, zero producer drops, database `ok`, no health issues, and both deployed listener units active.

## Files created

- `commons_lab/acoustic.py`
- `commons_lab/context.py`
- `commons_lab/jobs.py`
- `commons_lab/factory.py`
- `commons_lab/incidents.py`
- `scripts/run_data_factory.py`
- `tests/test_data_factory.py`
- `deploy/systemd/pine-hollow-data-factory.service`
- `deploy/systemd/pine-hollow-data-factory.timer`
- architecture/research/development/operations/validation documents

## Files modified

- `commons_lab/schema.py` — additive schema versions 4 and 5 only.

Existing user-modified files were not edited by this work.

## Independent-review hardening pass

Two read-only reviewers compared the implementation against the phase plan and examined data-loss, concurrency, privacy, and sandbox risks. Their findings were treated as release gates rather than advisory notes.

Corrections applied:

- database-level update/delete guards for model and human assertions;
- background worker heartbeat, fresh per-job clocks, and lease-valid completion/failure;
- temporal eligibility gate for mutable Observatory snapshots;
- source/tolerance/method-aware context job identity;
- `commons_current_event_links` for canonical nearest relationships while preserving raw history;
- retained-ledger and WAV-mtime source watermark coverage;
- continuous window, class, timestamp, and supersession checks for human reviews;
- one atomic transaction per imported recording;
- symlink-ancestor rejection for private snapshot promotion;
- narrower systemd read-only overlays for repository code and metadata;
- exact private preservation of field incident JSON/JSONL without synthetic media events.

The incident source contains six recording SHA-256 identities lost after ACK under the former evicting 32-file spool. The summary records the corrected non-evicting backpressure behavior. These losses are provenance, not recoverable acoustic evidence.

## Hardened live cycle

The timer was stopped during schema and worker changes. A read-only source validation found 112 retained recordings. The first bounded manual cycle then:

- imported 9 new recordings while recognizing 103 existing recordings;
- inserted 54 windows and 18 model assertions;
- preserved two incident-ledger files as two incident records;
- archived one temporally eligible Observatory snapshot;
- inserted 20 visual and 10 environmental links under tolerance-versioned methods;
- ran no GPU work.

One expected reconciliation context job followed because newly imported events changed the archived-event watermark after initial scheduling; it inserted zero links. The next cycle created zero jobs and ran zero handlers.

## Final blocker-review correction

The final read-only reviewer found three remaining high-severity gaps: no full WAV bytes in the scheduler watermark, symlink checks after normalization at several source boundaries, and repository-wide service write access required by root-level SQLite WAL files.

Corrections:

- introduced `commons_lab/safe_paths.py` for component-wise no-symlink resolution;
- applied it across import, context, incident, scheduler, and Observatory-gate source paths;
- added full retained-WAV SHA-256 content to `_field_watermark`;
- added four regression groups covering same-size/restored-mtime mutation, symlinked sources, retained-WAV gate paths, and service write scope;
- moved the canonical SQLite database beneath `private/commons_lab/runtime/` while preserving `archive.db` as a relative compatibility symlink;
- changed the unit from repository-wide write access to a read-only repository with only the private runtime/data tree and cache/lock tree writable.

The first exact-file WAL/SHM design passed once but failed on the next start because SQLite legitimately removed the sidecars. That design was discarded. The runtime-directory design passed repeated service starts, a zero-link reconciliation, and a zero-work replay.

One final bypass remained in `scripts/run_data_factory.py`: CLI configuration called `resolve()` before the strict source-path layer. Replacing those calls with `absolute()` preserves symlink components without leaving relative-path ambiguity. The new CLI regression test raises on a symlinked review root before any import.

The last lease review found `run_jobs()` still passed its optional cycle-start `now` into terminal completion/failure calls. Those calls now always use `live_clock()`. The fixed cycle time remains available for deterministic enqueue/claim tests, but it can no longer authorize a terminal transition after real lease expiry. A dedicated regression simulates the expiry and proves the job remains recoverable rather than falsely successful or failed.

The follow-up review found that retaining the fixed `now` for repeated claims could give later jobs shortened or already-expired leases. The parameter was removed from `run_jobs()` rather than patched at individual callers. Every claim and terminal transition now uses `live_clock()`; deterministic tests inject their own clock, while cycle-start time remains only in run metadata, enqueue identity, and explicit enqueue timestamps.
