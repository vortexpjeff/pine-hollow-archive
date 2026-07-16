# Pine Hollow Physical-Ecology Data Factory Architecture

**Version:** 0.2

**Established:** 2026-07-16

**Scope:** Phases 1–3: acoustic evidence bridge, temporal context, bounded CPU/GPU automation

**Canonical local ledger:** `private/commons_lab/runtime/archive.db` (`archive.db` is a relative compatibility symlink)

## Purpose

The data factory turns private field observations into traceable research material without treating model output as ecological truth. It connects the durable field listener, Pine Hollow Archive, Commons camera, local Observatory payload, human review, and Athena's optional GPU capacity.

The line is designed for replay, repair, adaptation, and expansion. Each stage exposes its evidence and state. A failed stage does not erase its input or silently relabel it.

## Non-goals

- No model threshold changes.
- No automatic promotion of reviews into training truth.
- No raw audio, camera, exact location, or private context publication.
- No BirdNET-Pi mutation.
- No website mutation.
- No arbitrary commands stored in the database.
- No continuous GPU workload.
- No causal inference from temporal proximity.

## Operating line

```text
BirdNET-Pi 15 s WAV
  -> durable Athena field spool
  -> frozen Perch embedding
  -> InsectNet + ChickenNet exact 5 s scores
  -> retained event/control WAV + JSON + read-only field ledger
  -> strict archive importer
  -> one atomic recording transaction
  -> private Commons event + media + append-only exact-window rows
  -> immutable independent model assertions
  -> score-stratified review queue
  -> append-only human assertions

Commons fixed camera ---------\
                               -> non-causal temporal links
Immutable Observatory snapshot /

Changed source watermarks
  -> deterministic jobs
  -> leased allowlisted worker
  -> background lease heartbeat + append-only transitions
  -> bounded result or retry

Field incident JSON/JSONL
  -> exact private copy + immutable incident record
  -> no synthetic media event
```

## Three truth layers

1. **Evidence:** immutable or hash-verified media and measurements.
2. **Assertions:** model, human, sensor, rule, or external-dataset claims about evidence.
3. **Decisions:** review state, publication state, interventions, and later outcomes.

A high model score is an assertion. A human confirmation is a separate assertion. Neither overwrites the other.

## Identity and idempotency

- Field `recording_id` is the retained WAV SHA-256.
- Bundle identity is recomputed exactly from the verified `SHA256SUMS` contract used by the listener.
- Commons event/media identities derive from site, deployment, source, capture time, event type, file hash, and path.
- Acoustic-window identity derives from recording, bundle, and start sample.
- Queue identity derives from event, bundle, and score band.
- Job identity derives from allowlisted job type and caller-supplied source watermark.
- Event-link identity derives from source event, target event, relation, and method.

Replaying an unchanged stage returns existing identities and inserts no duplicate evidence.

## Source verification

The importer joins three authoritative inputs:

1. retained WAV and JSON sidecar;
2. read-only field SQLite ledger;
3. deployed bundle directory.

It verifies:

- WAV filename, SHA-256, ledger SHA-256, and source byte count agree;
- sidecar recording identity agrees;
- sidecar and ledger bundle sets agree;
- sidecar class matches verified bundle metadata;
- sidecar normalized scores match ledger scores;
- sidecar event IDs match ledger event IDs;
- every scored bundle is currently supplied to the importer;
- controls contain no threshold events;
- each exact window has one unambiguous source event association at most.

Any disagreement fails before creating an acoustic event.

Configured field ledgers, bundle roots and members, review roots, retained WAVs and sidecars, Observatory snapshots, incident ledgers, and generic media sources are resolved only after every existing path component is checked for symbolic links. A configured source that crosses a symlink is rejected rather than normalized to an unexpected target.

## Schema version 5

### `commons_acoustic_windows`

One immutable row per exact scored window. Important fields:

- event/media identity;
- source recording and source event identity;
- bundle ID, slug, class;
- start/end sample and sample rate;
- normalized and raw score;
- deployed threshold and threshold-crossing flag;
- score semantics and preprocessing recipe.

The normalized scores are explicitly recorded as `uncalibrated_case_control_ranking_score`, not probability.

### `commons_event_links`

Immutable association between two Commons events:

- relation;
- method;
- signed time offset (target minus source);
- bounded proximity confidence;
- metadata containing `causal_claim: false`.

Current relations:

- `nearest_visual_context`
- `contemporaneous_environmental_context`

Links require matching private site identity and configurable tolerances.

Raw links remain immutable history. `commons_current_event_links` is the canonical query surface for the currently nearest target per source, relation, and versioned method. Automated method identity includes the configured tolerance, so changing a tolerance creates a distinct matching contract rather than reinterpreting old links.

### `commons_review_queue`

Mutable workflow state, separate from assertions. Current states:

- pending;
- in review;
- completed;
- dismissed.

Queue membership does not mean training eligibility.

### `commons_jobs`

Mutable current state for one deterministic work unit. Current states:

- queued;
- running;
- success;
- skipped;
- failed;
- cancelled.

A worker lease records owner and expiry. A separate SQLite connection renews long-running work before expiry and records `running → running` heartbeat transitions. Completion and failure reject expired or foreign leases. Attempts are bounded. Recoverable failures receive exponential backoff capped at five minutes.

### `commons_job_transitions`

Immutable job history. Every enqueue, lease, recovery, retry, completion, skip, failure, or cancellation adds a row.

### `commons_research_records`

Immutable research, decision, development, experiment, validation, incident, and operational records. Corrections are new records, never edits.

## Human review contract

A review records:

- event and media;
- class and bundle;
- exact start/end sample;
- present/absent assertion;
- certainty (`confirmed`, `probable`, `uncertain`);
- reviewer and review time;
- optional notes;
- optional superseded human assertion.

Only confirmed reviews are marked potentially training-eligible in assertion metadata. Dataset assembly remains a separate governed step.

Corrections append a new assertion with `supersedes_assertion_id`; prior review evidence remains readable. Database triggers reject assertion update and deletion. Review insertion validates timezone-aware review time, bundle/class membership, continuous scored-window coverage, and same-lineage supersession.

## Calibration sampling

For each bundle, the queue uses the maximum window score per retained recording and samples deterministically within:

- `>= 0.9999`
- `0.999–0.9999`
- `0.99–0.999`
- `0.9–0.99`
- `0.5–0.9`
- `< 0.5`

Stable hash ordering prevents a newest-only sample. Deterministic controls provide evidence outside detector-selected positives.

## Temporal context

Camera and Observatory links establish proximity only. They do not label the acoustic event and do not imply weather, light, or visible organisms caused a sound.

The website Observatory file is mutable. It is eligible for archival only when its validated `updated` timestamp falls within the configured tolerance of retained or archived acoustic evidence. Before archival use, exact bytes are copied atomically into:

```text
private/commons_lab/observatory_snapshots/YYYY/MM/DD/
```

The immutable copy receives its own hash, event, media record, privacy block, and source-path provenance. The data root and every existing destination ancestor are rejected if symlinked.

## Incident provenance

Field incident ledgers document evidence that cannot be recovered, including the six post-ACK WAV losses caused by the former evicting local spool. Each JSON/JSONL version is syntax-validated, content-addressed, copied into private archive storage, and represented by an immutable `incident` research record. The importer explicitly records `missing_media_recovered: false`; it never creates an acoustic event or media row for a missing WAV.

## Job allowlist and energy classes

Current allowlisted jobs:

| Job | Energy class | Automated |
|---|---|---:|
| field import | scheduled CPU | yes |
| field incident import | scheduled CPU | yes |
| Observatory snapshot | scheduled CPU | yes |
| context join | scheduled CPU | yes |
| SQLite integrity | scheduled CPU | yes |
| GPU environment probe | deferrable GPU | no |

Defined energy classes:

- `critical_continuous`
- `scheduled_cpu`
- `deferrable_gpu`
- `manual_high_energy`

The database contains structured parameters only. Handler selection is fixed in Python. A job cannot supply a shell command.

## Scheduler behavior

The CPU timer runs every ten minutes with no catch-up storm (`Persistent=false`). Field source watermarks include the full retained WAV SHA-256 bytes as well as identity, size and mtime, sidecar content, retained-only ledger projections, and bundle manifests. Incident watermarks use exact ledger content. Context identity includes archived-event state, changed source markers, tolerances, and method version. Ordinary non-retained field-ledger churn does not enqueue work.

The service is bounded by:

- non-blocking process lock;
- free-space guard;
- maximum jobs per cycle;
- five-minute timeout;
- 50% CPU quota;
- 1 GiB memory cap;
- idle I/O priority;
- private temporary directory;
- no network address families beyond local Unix sockets;
- read-only field-listener and Observatory paths;
- a read-only repository root with only `private/commons_lab/` reopened writable for the canonical database, SQLite WAL/SHM, immutable private copies, and runtime state;
- a separate writable lock directory under `~/.cache/pine-hollow-commons/`;
- no GPU job automation.

## Privacy and publication

Every imported acoustic event, camera relation, and Observatory snapshot is private and publication-blocked. Existing Commons publication guards remain authoritative. The public website receives nothing from this release.

## Extension rules

### Add a model bundle

1. Deploy and validate through the field-listener bundle contract.
2. Add its directory to factory configuration.
3. Run dry-run.
4. Import changed retained evidence.
5. create a score-stratified review queue.
6. Review independent days before changing thresholds.

### Add a job

1. Name a bounded task and energy class.
2. Add it to `JOB_ENERGY_CLASS`.
3. Implement a fixed handler in `factory.py`.
4. Add lease/failure/integration tests.
5. Define a deterministic source watermark.
6. Document inputs, outputs, resource limits, and rollback.
7. Do not accept arbitrary executable parameters.

### Add context

1. Ingest immutable evidence as a Commons event.
2. Define relation and method names.
3. Define same-site and time-tolerance rules.
4. Preserve signed offset.
5. Set `causal_claim: false` unless a separate controlled design supports attribution.

## Recovery boundary

Stopping the timer stops new CPU cycles. It does not stop the field listener or camera timer. Existing schema additions may remain dormant. No rollback deletes evidence. The pre-migration SQLite backup is retained under `private/backups/`.
