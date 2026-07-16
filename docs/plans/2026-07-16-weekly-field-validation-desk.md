# Weekly Field Validation Desk Implementation Plan

> **For Hermes:** Implement phase-by-phase with TDD. Do not modify `scripts/review_app.py` or `scripts/pull_clips.py`.

**Goal:** Build an additive, private, blinded weekly validation workflow that turns the factory's exact acoustic evidence into deterministic 24-item human-review packets, append-only judgments, cumulative scientific metrics, and artifact sentinel checks.

**Architecture:** Add schema version 6 tables for immutable packet manifests, packet items, append-only reviews, and promoted sentinels. A pure-standard-library validation module owns deterministic sampling, transactional review writes, metrics, and exact WAV slicing. The existing bounded CPU cycle creates one packet per local week and verifies promoted sentinels; a separate localhost-only HTTP application provides the blinded review surface.

**Tech stack:** Python 3.11 standard library, SQLite, existing Commons/factory modules, `http.server`, `wave`, `zoneinfo`, unittest/pytest, user systemd for the existing bounded worker.

---

## Scientific contract

- Sampling unit is a unique parent recording, not an individual window. Hidden repeat items are the only intentional duplicate recordings within a packet.
- Each reviewed item is one exact five-second imported span. Full 15-second audio is context only.
- The pre-submit interface hides model, score, threshold, threshold crossing, and sampling lane.
- Weekly packet target is 24 items: 8 model-positive, 8 boundary, 6 random controls, 2 hidden repeats.
- Positive and boundary lanes split evenly across `insect_present` and `chicken_vocalization_present`.
- Boundary splits above/below threshold. Positive sampling spans the positive score range.
- Random controls are selected independently of score from the remaining eligible recordings.
- Deterministic local-week seed, protocol version, sampling frame, exclusions, and selected model context are frozen into a canonical manifest hash.
- Reviews collect insect presence, chicken presence, signal quality, confounders, notes, reviewer, and elapsed review seconds.
- Validation reviews append two span-bounded human assertions with `training_eligible=false`; they never auto-promote into training truth or calibration state.
- Reports are event-level and label score bands as empirical ranking bands, not probabilities.
- Report Wilson intervals, random-control positive rate, boundary outcomes, score-band empirical positive rates, hidden-repeat agreement, day/hour coverage, uncertain rate, and review burden.
- Do not claim recall unless a complete bounded microphone-day/block receives independent full review.
- Sentinel promotion requires a completed, non-uncertain human review. Initial sentinel verification checks media bytes, imported spans, bundle IDs, and frozen scores/thresholds. True fresh audio rescoring remains a later approved field-runtime integration.

## Phase 1 — schema and review transaction seam

**Files:**
- Modify: `commons_lab/schema.py`
- Modify: `commons_lab/acoustic.py`
- Test: `tests/test_factory_validation.py`

1. Write failing migration tests for schema version 6 and tables:
   - `commons_validation_packets`
   - `commons_validation_items`
   - `commons_validation_reviews`
   - `commons_validation_sentinels`
   - `commons_validation_sentinel_checks`
2. Add update/delete guards for immutable manifests, reviews, and sentinel check history.
3. Add indexes for packet state/week, item packet/position/state, and sentinel activity.
4. Extend `record_human_acoustic_review()` with transaction ownership, optional validation context, explicit training eligibility, and nullable uncertain presence while preserving existing defaults.
5. Test that legacy callers retain current behavior and validation callers can atomically append two assertions without touching calibration-queue state.

## Phase 2 — deterministic packet generator

**Files:**
- Create: `commons_lab/validation.py`
- Test: `tests/test_factory_validation.py`

1. Write fixture helpers that create multiple dates/hours, both model bundles, exact aligned windows, and score distributions around both thresholds.
2. Write failing tests for:
   - stable packet ID and manifest hash;
   - 24 positions and lane counts 8/8/6/2;
   - class balance in positive/boundary lanes;
   - 2 above + 2 below boundary items per class;
   - no parent-recording duplication outside repeat lane;
   - hidden repeats reference prior source items and appear later/non-adjacent;
   - random controls are selected without score filtering;
   - previously unused recordings are preferred in later weeks;
   - insufficient frames produce a documented non-created result, not a malformed packet;
   - replay returns the exact existing packet or rejects contract drift.
3. Implement canonical JSON, stable IDs, local-week calculation with `America/New_York`, deterministic seeded ordering, date/hour diversity, and manifest hashing.
4. Insert packet and items atomically.

## Phase 3 — append-only validation review and exact audio

**Files:**
- Modify: `commons_lab/validation.py`
- Test: `tests/test_factory_validation.py`

1. Write failing tests for exact WAV span extraction, sample-rate/channel preservation, and out-of-range rejection.
2. Write failing review tests for required fields, enum validation, item/media/span ownership, duplicate submission, hidden-repeat independence, and rollback after second assertion failure.
3. Implement `record_validation_review()` in one `BEGIN IMMEDIATE` transaction:
   - append validation review;
   - append insect and chicken human assertions with validation item/packet context;
   - set `training_eligible=false`;
   - complete item;
   - update packet state/completion if appropriate.
4. Preserve blind-review data: model context remains in item manifest and is not needed by the pre-submit view model.

## Phase 4 — cumulative scientific metrics and sentinel foundation

**Files:**
- Modify: `commons_lab/validation.py`
- Test: `tests/test_factory_validation.py`

1. Write failing tests for Wilson intervals and empty/small samples.
2. Build packet/cumulative metrics excluding repeat items from performance estimates.
3. Compute:
   - positive-lane empirical precision per class;
   - boundary above/below outcomes;
   - random-control positive rate per class;
   - empirical positive rate by frozen score band;
   - uncertain-review rate;
   - exact hidden-repeat agreement;
   - unique recording/day/hour coverage;
   - total/median review seconds.
4. Add report-language guards stating what cannot be inferred.
5. Add sentinel promotion from completed non-uncertain items.
6. Add sentinel verification for media SHA-256, exact imported span, bundle/class identity, score, threshold, preprocessing recipe, and active state. Checks append immutable rows.

## Phase 5 — localhost Validation Desk

**Files:**
- Create: `scripts/run_validation_desk.py`
- Create: `launch_validation_desk.sh`
- Create: `launch_validation_desk.bat`
- Test: `tests/test_validation_desk.py`

1. Build a pure-standard-library server bound by default to `127.0.0.1:8765`.
2. Add per-process CSRF token and POST-only review writes.
3. Routes:
   - `/` packet list, progress, health summary;
   - `/review?packet_id=...&item_id=...` blinded exact-span review;
   - `/audio/<item_id>?scope=window|full` private WAV streaming;
   - `/report?packet_id=...` packet and cumulative report;
   - `/reveal?item_id=...` post-review model/lane context;
   - `/healthz` local readiness.
4. Do not render score/model/lane in review HTML before completion.
5. Escape all database/user text. Use parameterized SQL. Enforce ID formats and loopback binding.
6. Windows launcher starts WSL server and opens `http://localhost:8765`; shell launcher prints URL.

## Phase 6 — bounded weekly automation and CLI

**Files:**
- Modify: `commons_lab/jobs.py`
- Modify: `commons_lab/factory.py`
- Modify: `scripts/run_data_factory.py`
- Modify: `deploy/systemd/pine-hollow-data-factory.service` only if required paths change
- Test: `tests/test_factory_validation.py`

1. Add allowlisted `weekly_validation_packet` and `validation_sentinel_check` as `scheduled_cpu`.
2. Enqueue packet once per local week using protocol/week key.
3. Include protocol config in the immutable job contract.
4. Enqueue sentinel verification only when active sentinels exist, keyed by week + sentinel-set hash.
5. Add fixed handlers and result summaries.
6. Add CLI commands:
   - `validation-packet [--week-start]`
   - `validation-status`
   - `validation-report [--packet-id] [--json]`
   - `validation-review ...` for recovery/non-browser use
   - `validation-promote-sentinel --item-id`
   - `validation-check-sentinels`
7. Extend status counts without changing existing keys.

## Phase 7 — documentation, live validation, and release gate

**Files:**
- Create: `docs/weekly_field_validation_desk.md`
- Modify: `docs/physical_ecology_data_factory_operations.md`
- Modify: `docs/physical_ecology_data_factory_architecture.md`
- Modify: `docs/physical_ecology_data_factory_validation_2026-07-16.md`
- Update local manual bundle after production acceptance.

Verification sequence:

1. stop only the factory timer before schema/worker changes;
2. create and hash SQLite backup;
3. run failing tests before implementation and focused tests after each phase;
4. run full unittest and pytest suites;
5. compileall and staged security scan;
6. run source dry-run;
7. migrate live DB additively;
8. generate one real weekly packet and verify 24-item manifest/lane counts;
9. launch desk on loopback and exercise health, blinded page, exact audio, safe form validation, and report;
10. do not fabricate human labels during acceptance—leave packet pending;
11. verify service sandbox and scheduled worker;
12. reconcile and prove zero-work replay;
13. run independent blocker/high review;
14. enable timer only after PASS;
15. observe unattended cycle;
16. append validation/operation records.

## Explicit non-goals

- no automatic threshold changes;
- no automatic retraining or training eligibility;
- no claims of recall from candidate-only review;
- no public network binding;
- no changes to BirdNET, field listener, current review app, camera automation, or website;
- no fresh sentinel audio rescoring until a separate field-runtime bridge is designed and approved.
