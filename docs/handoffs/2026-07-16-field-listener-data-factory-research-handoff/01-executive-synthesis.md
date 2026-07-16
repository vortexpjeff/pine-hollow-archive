# 1. Executive synthesis

## Research question

Can a small private field station turn transient autonomous-recorder audio into durable, reviewable insect and chicken evidence while preserving BirdNET independence, exact-byte provenance, conservative model semantics, bounded energy use, and a credible path to human validation?

Over July 15–16, 2026, the build produced a working answer at the engineering and evidence-management levels. It did **not** establish ecological abundance, occupancy, absence, welfare status, or general field accuracy.

## What was built

### Layer 1 — research artifacts

Two public Perch 2 linear-transfer artifacts were trained, audited, corrected, checksummed, and published on July 15:

- InsectNet Research 0.2.0;
- ChickenNet Research 0.1.0.

Their public cards correctly state that they were research candidates and not deployed. They disclose both favorable internal checks and material external limitations.

Later that day, expanded private successor candidates were trained:

- InsectNet Research 0.3.0 dev2;
- ChickenNet Research 0.2.0 dev2.

Their run reports also initially marked them not deployed. Only later were their broad presence heads exported into strict JSON/NPZ field bundles with frozen Perch identity and much stricter review thresholds.

### Layer 2 — durable private listener

An independent Pi sidecar observes completed BirdNET WAVs without changing BirdNET. It assigns monotonic sequence numbers, copies recordings into a private durable spool, and retains each item until Athena returns an ACK matching sequence and SHA-256.

Athena:

1. receives a versioned frame;
2. writes and hashes exact bytes;
3. fsyncs file and directory state;
4. atomically publishes a ready item;
5. ACKs only after durable ownership;
6. runs frozen Perch 2 inference;
7. applies the two private broad-head bundles;
8. writes deterministic SQLite scores/events;
9. retains candidate/control evidence privately;
10. deletes ordinary source audio only after durable processing.

The transport is honestly described as **at-least-once delivery with idempotent effects**, not exactly-once delivery.

### Layer 3 — Commons data factory

The July 16 factory reads retained field evidence and the field ledger without modifying either. It imports:

- exact media identity;
- exact five-second model spans;
- per-bundle scores and thresholds;
- provenance and score semantics;
- source event identity;
- historical field-listener incident records;
- non-causal Observatory and camera-time context.

It uses deterministic jobs, explicit energy classes, leases, heartbeat renewal, retries, append-only transitions, source watermarks, and a read-only repository sandbox. The ten-minute scheduled line can claim only bounded CPU jobs. GPU work requires explicit manual authorization.

### Layer 4 — weekly blinded review

Protocol `weekly_blinded_v4` creates one deterministic 24-item packet per local week when enough archived evidence exists:

- 8 model-positive items;
- 8 threshold-boundary items;
- 6 score-independent random controls;
- 2 hidden repeats.

The browser is loopback-only. Before judgment it hides lane, model, score, threshold, crossing state, and repeat identity. Each submission appends two exact-span human assertions plus one review row in one transaction. Reviews are explicitly ineligible for automatic training.

The first packet completed 24/24 reviews over 22 unique source recordings. It demonstrated that the workflow is usable and that hidden-repeat judgments agreed in both pairs. It did not provide a recall estimate or field-performance certification.

## What is operational at handoff

At the fixed 2026-07-16 19:40:42 UTC snapshot:

| Component | State |
|---|---|
| BirdNET | Separate and unchanged by this build |
| Pi durable sidecar | Operating; producer drop count 0 at snapshot |
| Athena capture | Active and connected |
| Athena listener | Active and healthy |
| Field ledger | SQLite quick-check `ok`; 4,668 recordings; 28,008 scores; 137 events |
| Athena spool | Empty across incoming/ready/processing/failed |
| Commons factory | Schema 7; timer enabled/active |
| Factory service | Inactive between successful one-shot runs, as designed |
| Factory jobs | 68 success; no other states |
| Weekly validation | v4 packet complete, 24/24 |
| Sentinel set | Empty; foundation implemented but no examples promoted |
| GPU automation | Disabled |

The field counts are changing live and must be treated as a dated snapshot.

## Strongest results

### Engineering

- BirdNET was preserved as a separate system.
- ACK follows durable receiver ownership.
- Exact SHA-256 identity and deterministic keys make replay idempotent.
- Queue pressure is handled before ACK, preserving upstream ownership.
- The listener and factory have explicit crash/recovery behavior.
- Strict bundle loading removes joblib from the runtime path.
- Systemd declarations were verified against live process visibility; unsupported WSL path isolation was replaced with a tested namespace wrapper.
- The factory repository is read-only to its service; mutable state lives under a private runtime tree.
- All scheduled jobs in the final snapshot were successful.
- The final field and factory test gates passed.

### Scientific discipline

- Model scores remain model assertions, not observations.
- Only broad heads are operational; unsupported subtypes are not emitted.
- Thresholds are called diagnostic screening thresholds, not probabilities.
- Random controls are selected independently of score.
- Reviews include `uncertain` and exact-span scope.
- Hidden repeats measure within-reviewer consistency.
- Historical protocols remain evidence but cannot accept new reviews.
- Validation examples cannot silently become training data.
- Context links are explicitly non-causal.
- Lost recordings remain incident evidence rather than synthetic media.

## Material limitations

### Model limitations

- The public InsectNet 0.2.0 artifact activated on 11/26 independent dog windows.
- The private dev2 InsectNet successor improved that diagnostic to 6/26 at its training threshold but still showed cross-domain activation.
- The public ChickenNet artifact had only four crow positives in its internal grouped test.
- The private dev2 chicken weak-positive challenge had no negative examples and cannot measure precision.
- Training and challenge metrics do not directly evaluate the much stricter deployed field thresholds.
- Scores are uncalibrated case-control ranking scores.

### Validation limitations

- The first weekly packet is one small realized sample.
- Model-positive and boundary lanes are purposive, not population-random.
- Controls provide a score-independent sample but only six recordings.
- Candidate review alone cannot estimate recall.
- Hidden-repeat agreement is based on two pairs and one reviewer.
- No seasonal, multi-site, multi-recorder, or multi-reviewer generalization is established.
- No fresh model inference occurs in the current archive-side sentinel check.

### Systems limitations

- A physical power-cut test with real hardware/filesystem flush behavior was not performed.
- Six WAVs were lost during development under a now-removed post-ACK eviction design; hashes and timestamps were preserved.
- The validation launcher may open the browser before the local server is ready; refreshing after startup is the current workaround.
- Heartbeat shutdown has one documented non-blocking medium note under prolonged SQLite blocking.
- Thirty-two legacy archive foreign-key violations predate Commons schema 4; new Commons violations remain zero.

## Why this is research-grade in spirit, and where it is not

The deliverable approaches research-grade practice through explicit provenance, immutable identities, deterministic sampling, append-only review, disclosed incidents, negative challenge reporting, frozen thresholds, source rights lanes, and claim boundaries.

It is **not** a complete reproducible scientific publication because:

- private row-level manifests and audio cannot be redistributed;
- the public model bundles alone cannot reconstruct every training split;
- the local field validation sample is still small;
- the field system has not completed a season-scale or power-cut campaign;
- ecological estimands and detection models have not been defined.

The correct final claim is:

> A private, durable, review-only bioacoustic evidence pipeline and downstream physical-ecology archive were built, hardened, exercised live, placed into bounded unattended operation, and connected to a deterministic weekly human-validation protocol. The system is suitable for accumulating auditable local evidence. Its models are not yet validated for unattended ecological inference.