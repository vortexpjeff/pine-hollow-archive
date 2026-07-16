# 6. Factory schema and data dictionary

## Schema state

The fixed handoff snapshot uses Commons schema version **7**.

Earlier factory manuals captured schema 5 before the weekly validation system existed. Those documents remain correct historical checkpoints. Schema 7 adds the final validation packet, review, sentinel, active-protocol, and exact source-recording identity rules.

Migration is additive and transactional. Applied versions are recorded in `commons_schema_versions`.

## Runtime layout

The repository-root `archive.db` is a compatibility link to the canonical private runtime database. SQLite WAL/SHM files therefore remain under the private runtime tree rather than requiring repository-root writes.

The service sees the repository read-only. Mutable state is restricted to:

- the private Commons runtime/data tree;
- a dedicated cache/lock tree.

Field ledger/evidence, incident records, Observatory JSON, and camera sources are read-only inputs.

## Field-listener source schema

The field listener has four authoritative SQLite objects.

### `recordings`

One row per exact WAV identity.

| Column | Meaning |
|---|---|
| `recording_id` | deterministic identity; exact WAV SHA-256 |
| `source_sha256` | source byte digest |
| `source_bytes` | exact byte count |
| `captured_at` | source capture timestamp |
| `source_name` | private source filename metadata |
| `committed_at` | durable processing commit time |
| `metadata_json` | source/protocol context |

### `scores`

One row per recording, bundle, and five-second start sample.

| Column group | Meaning |
|---|---|
| `recording_id`, `bundle_id` | source and frozen runtime artifact |
| `start_sample`, `end_sample` | exact model span in 32 kHz inference timebase |
| `score`, `raw_score` | uncalibrated ranking output and pre-normalization form |

Primary key: recording + bundle + start sample.

### `events`

Deterministically merged threshold-crossing windows.

| Column group | Meaning |
|---|---|
| `event_id` | deterministic candidate identity |
| `recording_id`, `bundle_id` | source and runtime artifact |
| `start_sample`, `end_sample` | merged event span |
| `score`, `raw_score` | event ranking values |
| `window_count` | number of merged crossing windows |
| `review_state`, `review_label` | field-ledger review fields; all 137 were unreviewed at snapshot |

### `service_state`

Small key/value operational state for deterministic listener recovery/status.

## Commons base objects

The archive’s broader Commons schema predates this build. The factory uses these shared objects rather than creating a separate silo.

### `commons_sites`

Site identity with public-region and private exact-location separation. Exact locations are private and absent from this packet.

### `commons_sensors`

Sensor identity, type, host role, privacy default, metadata, and retirement time.

### `commons_deployments`

Time-bounded sensor/site deployment and configuration provenance.

### `commons_events`

Canonical event envelope.

Key fields:

- deterministic `idempotency_key`;
- type and start/end/timezone;
- site/deployment/source;
- privacy/review/publication states;
- structured metadata.

Field-listener recordings enter as acoustic events. Observatory snapshots and camera observations use their own event types/authorities.

### `commons_media`

Media attached to an event.

Key fields:

- deterministic media idempotency;
- path, SHA-256, byte size, MIME type;
- duration/dimensions/capture time;
- transform and privacy metadata.

A path is not trusted as identity. Exact bytes are hashed and verified.

### `commons_measurements`

Typed phenomenon/value/unit observations attached to events.

### `commons_assertions`

Append-only machine or human claims.

| Field | Contract |
|---|---|
| `subject`, `predicate`, `value_json` | claim content |
| `source_type`, `source_name`, `source_version` | provenance |
| `confidence` | optional source-specific confidence, not universal probability |
| `authority` | machine bundle, human reviewer, or other explicit authority |
| `created_at` | append time |

Model assertions and human validation assertions are separate authorities. A correction appends a superseding assertion rather than updating old evidence.

### `commons_event_links`

Immutable relationship history among events.

Key fields include relation, method, signed offset, confidence, and metadata. Automated nearest-time links include tolerance/provenance and are non-causal.

### `commons_current_event_links`

A view selecting the present current nearest relationship from immutable link history.

### `commons_interventions` and `commons_outcomes`

Decision/action and observed-outcome structures. This two-day bioacoustic line did not automatically create husbandry or ecological interventions from model scores.

### `commons_publications`

Publication state and reviewed public URI/payload hash. Private audio and validation content are not published.

### `commons_legacy_links`

Explicit bridge from legacy archive rows to Commons identities. It preserves migration provenance instead of silently rewriting history.

## Exact acoustic lineage

### `commons_acoustic_windows`

One immutable exact model window.

| Column | Meaning |
|---|---|
| `window_id` | deterministic identity |
| `event_id`, `media_id` | Commons parent evidence |
| `source_recording_id` | frozen field recording identity; schema-7 analysis key |
| `source_event_id` | original field event identity |
| `bundle_id`, `model_slug`, `class_name` | frozen model context |
| `start_sample`, `end_sample`, `sample_rate` | exact inference span |
| `score`, `raw_score`, `threshold`, `crosses_threshold` | model output contract |
| `score_semantics` | explicitly uncalibrated case-control ranking semantics |
| `preprocess_recipe_id` | exact audio/feature recipe |
| `metadata_json` | source lineage |

Replay uses insert-or-verify. Existing identity with materially different values is an error.

## Review queues

### `commons_review_queue`

Older score-stratified calibration queue.

- event/bundle/class;
- score band;
- priority and reason;
- pending/completed state;
- metadata.

The weekly v4 desk is separate. Completing a validation item does not silently complete this older queue.

## Job and run ledger

### `commons_runs`

One pipeline invocation with trigger, timestamps, status, optional related event, error, and metadata.

### `commons_jobs`

Durable deterministic work item.

| Field group | Meaning |
|---|---|
| `job_key`, `job_type` | idempotent fixed handler identity |
| `energy_class` | scheduled CPU, manual CPU, or deferrable GPU |
| `state`, `priority`, `not_before` | scheduling |
| `attempts`, `max_attempts` | bounded retry |
| `lease_owner`, `leased_until` | exclusive worker ownership |
| `parameters_json`, `result_json`, `error` | input/output/failure record |
| timestamps | creation, start, completion, update |

Arbitrary SQL-inserted job types are not executable. Code must map an allowlisted type to a fixed handler and energy class.

### `commons_job_transitions`

Append-only transition history, including running-to-running heartbeat renewals. Terminal completion/failure requires current owner and unexpired lease.

## Research record

### `commons_research_records`

Dated append-only method, experiment, incident, and research notes with source links and related run/job/event identities.

The Markdown documentation is the human-readable layer. This table is the machine-addressable archive layer.

## Weekly validation schema

### `commons_validation_packets`

One frozen manifest per protocol/week.

| Field | Meaning |
|---|---|
| `protocol_version` | active method identity |
| `week_start`, `timezone` | local sampling week |
| `sampling_seed` | deterministic selection seed |
| `target_count` | 24 for v4 |
| `state`, `completed_at` | progress only |
| `manifest_sha256`, `manifest_json` | immutable canonical selection |

Manifest fields are immutable after creation.

### `commons_validation_items`

One exact review unit.

| Field group | Meaning |
|---|---|
| `packet_id`, `position` | packet order |
| `event_id`, `media_id`, `source_recording_id` | frozen evidence identity |
| `start_sample`, `end_sample`, `sample_rate` | exact span |
| `lane` | positive, boundary, random control, or repeat; hidden before review |
| `source_item_id` | repeat lineage |
| `primary_class_name`, `primary_bundle_id` | sampling target; hidden before review |
| `sampling_metadata_json` | both frozen model contexts and method |
| `state`, `completed_at` | progress only |

### `commons_validation_reviews`

Append-only two-target human judgment.

Fields include:

- reviewer authority;
- insect presence;
- chicken presence;
- signal quality;
- confounder tags;
- notes;
- measured review seconds;
- IDs of the two appended human assertions;
- review timestamp.

### `commons_validation_sentinels`

Deliberately promoted decided examples from the active protocol. Frozen media hash, model context, and human labels form a future artifact-drift foundation.

No sentinel had been promoted at the snapshot.

### `commons_validation_sentinel_checks`

Append-only pass/drift/missing checks of active sentinels. Current checks verify bytes and archived context but do not perform fresh model inference.

## Snapshot counts

At 2026-07-16 19:40:42 UTC:

| Object | Rows |
|---|---:|
| Commons events | 226 |
| Commons media | 226 |
| acoustic windows | 888 |
| assertions | 344 |
| event links | 123 |
| jobs | 68 |
| job transitions | 204 |
| runs | 108 |
| research records | 20 |
| score-stratified review queue | 41 |
| validation packets | 4 |
| validation items | 96 |
| validation reviews | 24 |
| validation sentinels/checks | 0 / 0 |

All 68 jobs were in `success` state. Counts are a dated operational snapshot.

## Mutability summary

| Data | Policy |
|---|---|
| media/event deterministic identity | insert-or-verify |
| acoustic windows | append-only/immutable material contract |
| assertions | append-only; corrections supersede |
| raw event links | append-only history |
| jobs | controlled state transitions only |
| job transitions | append-only |
| research records | append-only |
| validation packet manifest | immutable |
| validation item selection | immutable except progress state |
| validation reviews | append-only, one per item |
| sentinels/checks | append-only; active flag only under explicit operation |

## Integrity gates

Routine gates include:

- `PRAGMA integrity_check`;
- Commons-scoped foreign-key validation;
- exact evidence SHA-256;
- bundle/member identity;
- source-recording/event alignment;
- model context insert-or-verify;
- deterministic replay;
- append-only triggers;
- packet manifest revalidation.

The archive has 32 legacy `label_events -> clips` foreign-key violations that predate Commons schema 4. SQLite integrity is `ok`; new Commons violations remain zero. The factory records but does not erase that legacy condition.