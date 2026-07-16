# 4. Architecture and truth contracts

## System purpose

The system preserves a chain from transient field audio to private human-review evidence. Its primary product is not a detection count. Its primary product is an auditable relationship among:

- exact audio bytes;
- model configuration and output;
- durable event identity;
- environmental context;
- human judgment;
- operational history.

## End-to-end dataflow

```text
field microphone
  |
  v
existing BirdNET recorder/analyzer ----------------------> BirdNET's own outputs
  |
  | completed WAV observed independently
  v
Pi sidecar
  - persistent sequence ledger
  - private copied WAV spool
  - byte/file/free-space limits
  - status frames
  |
  | restricted at-least-once SSH protocol
  | ACK(sequence, WAV SHA-256) only after receiver commit
  v
Athena capture
  - validates frame and declared length
  - streams + hashes exact bytes
  - fsyncs file and directory
  - atomic incoming -> ready publication
  - pre-ACK backpressure
  |
  v
Athena listener
  - claims ready -> processing
  - frozen Perch 2 inference
  - strict InsectNet/ChickenNet broad-head bundles
  - deterministic SQLite recording/score/event keys
  - candidate and deterministic control retention
  |
  | read-only source boundary
  v
Commons physical-ecology factory
  - immutable media/event identity
  - exact model windows and assertions
  - incident provenance
  - bounded jobs and energy classes
  - non-causal context links
  - weekly validation manifests/reviews/sentinels
  |
  v
private loopback validation desk
  - blinded exact-span playback
  - insect/chicken human labels
  - quality/confounder metadata
  - append-only assertions and review
  |
  v
cumulative evidence for later study design
```

## Separation from BirdNET

BirdNET remains an independent voice in the commonwealth. This build did not change:

- BirdNET models;
- sensitivity or confidence settings;
- occurrence filters;
- database or UI;
- notifications or publication behavior;
- recording, analysis, log, statistics, livestream, or Icecast services.

The Pi sidecar observes close-write completion and copies finished audio into its own spool. It is not inserted into BirdNET’s analysis path.

This separation protects both systems:

- a listener defect does not alter BirdNET’s existing work;
- BirdNET bird detections are not mixed with experimental insect/chicken assertions;
- stopping the listener or factory does not stop BirdNET;
- claims retain their source authority.

## Authority model

| Authority | Owns | Does not own |
|---|---|---|
| BirdNET | BirdNET recording and bird analysis | Experimental insect/chicken truth |
| Pi producer | Sequence truth, copied upstream audio, pre-ACK ownership | Receiver inference |
| Athena capture | Durable exact-byte receiver ownership after ACK boundary | Ecological interpretation |
| Perch/head runtime | Deterministic model scores under frozen artifacts | Calibrated probability or observation |
| Field SQLite/evidence | Recording, score, event, and retained-byte provenance | Human label |
| Commons archive | Imported evidence, model assertions, context, jobs, validation records | Source mutation |
| Human reviewer | Audible target label in exact reviewed span | Unreviewed time or population state |
| Future study protocol | Explicit estimand and ecological inference | Retroactive conversion of candidates into truth |

## Truth ladder

### Level 0 — bytes

A WAV exists with a measured byte length and SHA-256. This establishes exact-byte identity, not audio semantics.

### Level 1 — model assertion

A frozen bundle produced a score for an exact sample span. The assertion includes:

- bundle ID and class;
- start/end samples and sample rate;
- score and threshold;
- score semantics;
- preprocessing recipe;
- source event identity.

This is a machine assertion.

### Level 2 — human span observation

A reviewer listened to the exact span and appended `present`, `absent`, or `uncertain` for insect and chicken presence. This is a human observation bounded to that span and review authority.

### Level 3 — study result

A study defines sampling frame, estimand, inclusion/exclusion, reviewer policy, quality control, and statistical model. The current system has not yet produced population-level study results.

### Level 4 — ecological inference

Claims about abundance, occupancy, trend, welfare, habitat response, or causality require a documented detection/sampling model and evidence beyond this two-day build.

No automated transition exists between these levels.

## Identity hierarchy

```text
WAV SHA-256
  -> recording ID
    -> bundle ID + exact start sample
      -> deterministic score row
        -> merged deterministic event ID
          -> retained evidence pair
            -> Commons event/media ID
              -> exact acoustic-window ID
                -> model assertion ID
                  -> validation item/review/human assertion IDs
```

Each layer keeps its own identity because each answers a different question. The archive does not use filenames alone as evidence identity.

## Timebase contract

The model operates on non-overlapping five-second windows at 32 kHz. Retained field recordings preserve the capture stream’s native rate, currently 48 kHz.

The validation desk:

1. takes frozen model start/end samples in the 32 kHz inference timebase;
2. converts boundaries to elapsed time;
3. maps them to nearest native WAV frames;
4. serves native PCM bytes without resampling;
5. keeps the human assertion attached to the original model span.

A five-second model span therefore corresponds to 240,000 native frames at 48 kHz while retaining 160,000-sample model lineage at 32 kHz.

## Delivery and ownership contract

### Producer

```text
observed -> copying -> ready -> transmitting -> acked
                    \-> dropped
```

A producer `dropped` state is explicit and unhealthy. Ready items are never silently evicted.

### Receiver

```text
wire -> incoming -> ready -> processing -> committed/deleted
                                  \-> failed
```

The invariant is:

```text
matching ACK
  => receiver durably owns exact bytes
     OR an exact deterministic duplicate is already owned
```

If receiver capacity is insufficient:

```text
no body admission -> no ACK -> Pi retains source -> later replay
```

This is at-least-once transport. Duplicate attempts are expected after a lost ACK. Deterministic identities make effects idempotent.

## Evidence commit contract

Candidate/control retention commits in this order:

1. deterministic WAV path;
2. WAV write, flush, and fsync;
3. deterministic JSON sidecar;
4. sidecar write, flush, and fsync;
5. evidence-directory fsync;
6. SQLite transaction commit;
7. source deletion only after successful durable processing.

A replay verifies retained evidence. Missing evidence can be rebuilt from a still-owned source. A hash mismatch is an incident, not an overwrite opportunity.

## Factory write contract

The factory reads field sources but cannot modify them. For each retained recording, one transaction owns:

- Commons event;
- Commons media;
- every exact model window;
- every model assertion.

Existing deterministic identities use insert-or-verify semantics. A replay with materially changed score, threshold, source identity, preprocessing, or bundle context raises rather than silently mutating history.

## Context contract

The factory may link an acoustic event to the nearest eligible camera or Observatory event within a configured tolerance. The link records:

- source and target identities;
- relation and method;
- signed offset;
- tolerance;
- creation/provenance.

These are temporal relationships only. They do not establish that weather, an animal image, or another event caused the sound.

Raw link history is immutable. A current-view layer selects the present nearest relationship without deleting earlier provenance.

## Review contract

Before a v4 judgment, the reviewer does not see:

- lane;
- model/bundle;
- score;
- threshold;
- crossing state;
- hidden-repeat identity.

One review transaction appends:

- insect human assertion;
- chicken human assertion;
- validation review row;
- item progress;
- packet completion when appropriate.

If any write fails, all roll back. `training_eligible=false` is explicit.

## Protocol immutability

A packet freezes:

- protocol and local week;
- seed and deterministic selection method;
- selected identities and spans;
- both model contexts;
- media hash;
- lane/repeat lineage;
- no-training and no-causation markers.

The manifest itself is hashed. Packet/item deletion is blocked. Historical packets remain readable but inactive protocols cannot receive new reviews or sentinel promotions.

## Energy contract

| Energy class | Trigger | Normal use |
|---|---|---|
| `scheduled_cpu` | ten-minute timer | imports, context, incidents, weekly packet, sentinel byte checks |
| `manual_cpu` | explicit operator action | review queues, reports, local desk |
| `deferrable_gpu` | explicit manual authorization only | fixed GPU inventory probe or future approved work |

The scheduled timer cannot claim GPU jobs. The factory does not invoke an LLM.

## Privacy contract

### Always private

- raw and retained audio;
- packet manifests and review content;
- local field/database paths and context payloads;
- credentials and network details;
- row-level private training manifests and embeddings;
- property location.

### Publicly shareable after review

- architecture and methods;
- aggregate counts and dated snapshots;
- artifact and Git hashes;
- aggregate model/validation metrics with limitations;
- incident summaries that expose no private evidence;
- source citations and licenses.

## Security boundaries

### Pi key

The field key is a single-purpose forced-command capability. Arbitrary commands, forwarding, agent use, and PTY are disabled.

### Athena listener

The listener uses an unprivileged user/mount namespace wrapper because live WSL testing showed that declarative user-systemd path restrictions alone did not hide all unrelated files. The final listener:

- sees only required code/config/state/runtime/model paths;
- has code and bundles read-only;
- cannot see unrelated home/Windows/Hermes state;
- cannot see the capture service’s field SSH material;
- runs in a private network namespace.

### Factory

The repository is read-only to the service. Only the private Commons runtime tree and a dedicated cache are writable. Field sources and contextual sources are read-only. The service has no general network requirement for its normal cycle.

### Validation desk

The desk:

- binds only to loopback;
- rejects non-loopback Host headers;
- uses a random process token;
- writes only by POST;
- uses parameterized SQL and escaped HTML;
- serves no external assets;
- verifies exact bytes and frozen hashes;
- traverses audio descriptor-relatively with `O_NOFOLLOW`;
- hashes and slices from the same final descriptor.

## Core claim

The architecture supports durable, inspectable accumulation of private evidence. It intentionally stops before automatic ecological interpretation.