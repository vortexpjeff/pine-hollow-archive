# 2. Chronology and state transitions

## Why chronology is part of the safety case

“Not deployed,” “integrated into a listener,” and “entered unattended production” describe different artifacts, components, and times. Collapsing them creates a false narrative. This chronology therefore records state transitions rather than using “the model” or “the system” as if each were one object.

All times below are Eastern Daylight Time unless UTC is shown explicitly.

## July 15 — model publication and listener construction

### 15:48 — public research release corrected and published

Public Git commit `16c71e04ea8b9c34dec79df55f7fb8552af5dfd5` was authored at 19:48:35 UTC. Corrected Hugging Face revisions followed within seconds:

- InsectNet Research 0.2.0 revision `b435c9baa95e5726cb03b57707b1a6c24291f934`;
- ChickenNet Research 0.1.0 revision `2487e6c010aa3553ce6c1172ae7f51194f35379f`.

State at this checkpoint:

- public model cards and artifacts existed;
- exact public artifact and dataset hashes existed;
- publication/privacy/hierarchy corrections had been applied;
- both model cards said research candidate and not deployed;
- no claim of field readiness was made;
- BirdNET was unchanged.

This was the state described by the July 15 model audit. That statement remains historically correct.

### 17:17 — private ChickenNet dev2 candidate trained

Private run report created at 17:17:52:

- name: ChickenNet Research 0.2.0 Perch 2 public-data dev2;
- source artifact SHA-256: `d1595cc65a484ea963172dcc3c8d4b20e0fb6fbc0771883b40105b77668d6686`;
- expanded training frame: 5,492 five-second samples;
- report state: `research_candidate_not_deployed`.

This is a later private artifact, not the public ChickenNet 0.1.0 artifact.

### 17:22 — private InsectNet dev2 candidate trained

Private run report created at 17:22:51:

- name: InsectNet Research 0.3.0 Perch 2 public-data dev2;
- source artifact SHA-256: `9cd5f753db357220a180ead0d13019d46f69d469898b9a88bfdb12ca38fecf14`;
- expanded training frame: 6,097 five-second samples;
- report state: `research_candidate_not_deployed`.

This is a later private artifact, not the public InsectNet 0.2.0 artifact.

### After 17:22 — strict field exports created

Only the two broad presence heads were exported from the private dev2 candidates into runtime JSON/NPZ bundles:

- `insectnet-dev2-field-probe`;
- `chickennet-dev2-field-probe`.

The export changed the runtime object and operational threshold. The strict bundle identities are derived from checksummed `model.json` and `weights.npz` members. They are not identical to the source joblib hashes.

Operational thresholds were intentionally raised to:

- insect presence: `0.9995`;
- chicken vocalization presence: `0.9999`.

Those values are candidate-retention thresholds, not calibrated probabilities and not the training-report thresholds.

### By 21:45 — private listener operating

The listener’s live validation snapshot showed:

- capture connected;
- Perch scoring active;
- strict broad-head bundles loaded;
- producer sequence/drop accounting active;
- deterministic SQLite/evidence output;
- private candidate/control retention;
- BirdNET services remaining active.

The correct state description is:

> Private dev2 broad-head exports integrated into a private review-only listener.

It is **not**:

- public artifacts deployed unchanged;
- models field-validated;
- automatic ecological detections established;
- BirdNET replaced or modified.

### 21:58–22:09 — listener code and reports committed

| Time | Commit | Meaning |
|---|---|---|
| 21:58:24 | `fb732c8db368f8f641d7e2964fd9359c70cb153a` | Durable private Perch field listener committed |
| 22:00:07 | `383fd456250699375212cc963dcbc89c07588664` | Verified Git publication documented |
| 22:09:03 | `333f4f9c9b07d9202c21ceb30ce6fc07747ef173` | Durability and bioacoustic research record expanded |

### July 15 development incident

During sandbox restart testing, Athena accepted and ACKed replayed recordings faster than the listener could drain its 32-file queue. The old retention method then evicted six already-ACKed ready recordings.

State transition:

```text
unsafe: ACK -> receiver eviction -> unrecoverable loss
corrected: capacity check -> no ACK -> Pi retains -> later replay
```

The six byte identities and timestamps were preserved as an incident ledger. No synthetic recordings were created. The destructive path was removed and a live one-slot test proved backpressure before ACK.

## July 16 — factory build and unattended operation

### Morning — archive factory assembled and hardened

The factory added:

- exact field evidence import;
- immutable acoustic windows and model assertions;
- deterministic context links;
- incident-ledger preservation;
- durable jobs with energy classes and leases;
- source watermarks;
- read-only service sandbox;
- additive schema migration.

The timer remained paused while production-consumed code, schema, and sandbox behavior were changing.

### 11:40 — unattended no-work branch observed

A timer-triggered CPU cycle saw unchanged sources and completed with:

- zero created jobs;
- zero handlers;
- no GPU work;
- service success.

This is the required settled-source branch: unchanged evidence does not produce repeated work.

### 11:50 — code committed and evidence-bearing branch observed

Commit `f833e32eb0b2594dc1c18bf427969f154ea6f309` recorded the hardened factory at 11:50:33.

The 11:50 timer cycle then processed changed evidence:

- one retained recording imported;
- six exact model windows appended;
- two model assertions appended;
- one Observatory snapshot archived;
- two non-causal context links appended;
- three jobs successful;
- no GPU work.

Commit `f0ef51dfa67e17ba157c75d409b06a1788bc4f29` at 11:53 documented both unattended branches.

State transition:

> The downstream factory had entered unattended bounded-CPU production.

This does not mean the models had become validated ecological sensors. It means the evidence pipeline was executing safely and idempotently under its timer.

## July 16 — weekly validation desk

### Early protocols v1–v3

Three preliminary packet manifests were created while the protocol was being corrected. They remain immutable historical evidence and were not reviewed:

- `weekly_blinded_v1`;
- `weekly_blinded_v2`;
- `weekly_blinded_v3`.

The corrections addressed control sampling, active-protocol enforcement, repeat blinding, atomic review writes, exact audio serving, and scientific report semantics. Historical packets were not rewritten.

### 14:36 — protocol v4 frozen

The active `weekly_blinded_v4` packet was created for week start 2026-07-13:

- packet ID: `vpk_31d5158ef95e1fe35caff3e4`;
- manifest SHA-256: `bf7da3f8cad4d98fd7a76cc87cf4511e8428ff6b8b3bf127cb8beffe702cbd5e`;
- 24 immutable items;
- 22 unique parent recordings plus two hidden repeats.

### 14:57:13–15:08:28 — first human audit completed

The first review was saved at 18:57:13 UTC and the final review completed the packet at 19:08:28 UTC. The local desk exposed exact five-second spans and optional parent context while hiding model/lane information until after each judgment. All 24 items were reviewed.

This state transition matters:

> The system moved from purely machine-generated evidence to a first bounded set of append-only human observations.

It did not become a validated population-monitoring instrument.

### 15:13 — validation desk committed

Commit `4a10f940e794ce4a51cfe3f737dae10d85b9414c` added the v4 desk, protocol, schema, tests, launcher, and documentation.

### 15:22 — final two security/protocol findings closed

Commit `16c2344e2d6af4daee171fe5aa25d3390d9c5414` corrected:

1. historical-protocol sentinel promotion;
2. path check/open time-of-check/time-of-use exposure in audio serving.

The final desk reads audio through descriptor-relative `O_NOFOLLOW` traversal and hashes/slices from the same descriptor.

### 15:26–15:27 — factory restarted and restart recorded

The factory timer was re-enabled. Immediate cycle `run_f74d6677628c45e5ada1f85e5d366c2a` completed successfully. Commit `7afc63dda3f4847f09cad43197a8b4d4f3624b21` recorded the restart.

## Final fixed snapshot — 15:40:42

At 19:40:42 UTC:

- field listener healthy;
- 4,668 field recordings processed;
- 28,008 field score rows;
- 137 retained field candidate events;
- zero producer drops/gaps at snapshot;
- factory schema 7;
- 226 archived Commons events/media;
- 888 archived windows;
- 344 assertions;
- 68/68 jobs successful;
- v4 weekly packet complete 24/24;
- factory timer enabled/active.

## State language to preserve

| Object | Correct final description |
|---|---|
| Public InsectNet 0.2.0 | Published research artifact; not deployed |
| Public ChickenNet 0.1.0 | Published research artifact; not deployed |
| Private InsectNet dev2 joblib | Later private research candidate; source of deployed broad-head export |
| Private ChickenNet dev2 joblib | Later private research candidate; source of deployed broad-head export |
| Strict dev2 runtime bundles | Deployed privately for review-candidate ranking |
| Field listener | Durable private review-only inference system |
| Physical-ecology factory | Unattended evidence and context pipeline in bounded CPU production |
| v4 validation desk | Completed first weekly blinded human audit |
| Model/ecological status | Not calibrated or validated for unattended ecological inference |