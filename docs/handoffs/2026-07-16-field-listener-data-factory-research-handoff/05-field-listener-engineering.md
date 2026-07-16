# 5. Field-listener engineering

## Design target

The field listener had to consume transient BirdNET recordings without coupling experimental inference to BirdNET, without losing acknowledged evidence, and without letting a candidate score masquerade as ecological truth.

The deployed system is deliberately made from inspectable pieces:

- Linux close-write observation;
- SQLite ledgers;
- ordinary files and directories;
- SHA-256;
- a restricted SSH protocol;
- systemd user units;
- frozen Perch inference;
- strict JSON/NPZ heads.

## Pi producer

### Observation

An independent sidecar observes completed BirdNET WAV close events. It does not edit the BirdNET recording path or analysis process.

### Persistent sequence

Every observation receives a monotonic producer sequence in SQLite. The ledger records source identity, copy state, byte length, SHA-256, retries, ACK state, and explicit drops.

### Private copy

The producer copies the completed WAV into its own spool. It does not depend on the original BirdNET stream file remaining available indefinitely.

### Durability sequence

For a new private copy:

1. write temporary file on the spool filesystem;
2. fsync file;
3. atomically publish ready state;
4. fsync containing directory;
5. commit ledger transition.

Interrupted `copying` work is reconciled on restart.

### Capacity

The producer is bounded by:

- 512 recordings;
- 2 GiB total ready bytes;
- 2 GiB free-disk guard.

Capacity failures become explicit `dropped` ledger states and health failures. The producer does not evict old ready work to admit new work.

## Wire protocol

The versioned frame contains:

- frame kind (`audio` or `status`);
- producer identity;
- monotonic sequence;
- source name and mtime;
- byte count;
- WAV SHA-256;
- observed-sequence watermark;
- ready count/bytes;
- cumulative drop count.

Athena reads exactly the declared byte count and hashes while streaming. Extra or missing bytes fail the frame.

ACK contains the producer sequence and exact WAV SHA-256. A disconnect before matching ACK leaves the item ready upstream.

Status frames make upstream pressure and drop accounting visible even when no audio frame is transferred.

## Athena capture spool

### States

```text
incoming -> ready -> processing
                     |       |
                     |       +-> committed/deleted
                     +----------> failed
```

### Admission

Before accepting a nonduplicate body, capture measures combined ready/processing count and bytes. The local queue is bounded to 32 recordings and 128 MiB.

If admission would exceed a bound:

- capture returns no ACK;
- connection closes;
- Pi retains the item;
- later replay resumes when capacity returns.

Exact duplicates remain admissible for idempotent ACK recovery.

### Local commit

Capture:

1. validates header fields;
2. writes into `incoming`;
3. hashes streamed bytes;
4. verifies declared count and digest;
5. fsyncs audio and metadata;
6. atomically renames to `ready`;
7. fsyncs directory state;
8. returns matching ACK.

The receiver owns the item only after this boundary.

### Concurrency

Queue mutation uses a cross-process lock. Claim, capacity, duplicate detection, and startup recovery do not rely on unlocked directory scans.

## Listener runtime

### Claim and recovery

The listener atomically claims `ready` into `processing`. On startup, abandoned processing work returns to ready. A failed item retains source bytes and an error record.

### Audio

Each field recording is 15 seconds. It is decoded to the frozen Perch contract and split into three non-overlapping five-second windows.

### Frozen inference

The listener verifies:

- Perch model-tree hash;
- supported bundle schema;
- exact preprocessing recipe;
- checksummed members;
- allowed NPZ keys;
- shape, dtype, and finite values;
- broad class identity;
- threshold and runtime event configuration.

Joblib is not accepted at runtime. Trusted export is a separate explicit action.

### Scores and events

For each recording and bundle, three score rows are written. Adjacent crossing windows can be merged deterministically into candidate events according to the frozen runtime configuration.

Primary identities are deterministic:

- recording ID = exact WAV SHA-256;
- score key = recording + bundle + start sample;
- event ID = deterministic recording/bundle/span identity.

### Retention

Ordinary recordings are deleted after successful processing. Candidate events and a deterministic 1-in-240 control sample retain:

- WAV evidence;
- JSON sidecar;
- byte hash;
- source/model/span metadata.

The review store is bounded to 5 GiB. Health checks pairing and capacity.

## Field ledger at handoff

At 2026-07-16 19:40:42 UTC:

| Measure | Value |
|---|---:|
| recordings | 4,668 |
| score rows | 28,008 |
| retained candidate events | 137 |
| producer observed sequence | 4,540 |
| last received sequence | 4,540 |
| producer drops | 0 |
| sequence gaps | 0 |
| incoming/ready/processing/failed | 0/0/0/0 |
| SQLite quick-check | `ok` |
| listener health | healthy |

The recording count and current producer sequence are different counters with different historical scopes. The fixed snapshot does not establish the cause of their offset, so it must not be interpreted as a gap. These counts are a snapshot, not a rate or ecological total.

### Event distribution

The live ledger contained:

| Runtime bundle | Candidate events | Field-ledger review state |
|---|---:|---|
| Insect dev2 field probe | 100 | unreviewed |
| Chicken dev2 field probe | 37 | unreviewed |

The later Commons weekly review does not mutate these field-ledger rows. It creates separate exact-span human assertions in the archive.

## Security implementation

### Restricted uploader capability

The Pi-authorized key uses forced command and disables forwarding, agent, PTY, and arbitrary command execution.

### Why declarative systemd was insufficient

The initial user-systemd unit contained path restrictions, but a live process on WSL could still see unrelated home content. The configured property was not treated as proof.

A tested unprivileged user/mount namespace wrapper now:

- captures explicit required paths;
- overlays the home, Windows mount root, and user runtime directory;
- restores only required binds;
- makes code/bundles read-only;
- hides unrelated paths;
- gives the listener a private network namespace.

The capture service sees its dedicated field key; the listener does not.

## Fault injection and live tests

### Athena outage replay

A deliberate Athena outage accumulated four Pi recordings totaling 11,520,176 bytes. They replayed after reconnection.

### Lost ACK replay

A complete 2,880,044-byte frame was received without ACK. The Pi retained and replayed it. Receiver idempotency prevented duplicate logical records.

### One-slot backpressure

With Athena capacity reduced to one item and the listener stopped:

- one local ready item occupied capacity;
- the next recording remained ready on the Pi;
- producer drop count remained zero;
- restoring capacity drained both sides;
- sequence gaps remained zero.

### Sandbox probes

Actual child processes were probed to verify filesystem and network visibility. This tests enforcement rather than unit-file intent.

### Evidence and database checks

At the original listener handoff:

- private field suite: 15 passed;
- public InsectNet suite: 26 passed;
- Ruff, compileall, shell syntax, and systemd verification passed;
- duplicate score keys: zero;
- orphan scores: zero;
- evidence hash/sidecar checks: valid.

The final packet verification reruns the private field suite and static checks; see the release record for the final observed result.

## Known incident: six post-ACK losses

During sandbox restart testing, a replay burst filled the receiver faster than inference could drain it. The original code ACKed durable receipt and then enforced capacity by evicting six ready recordings.

Impact:

- six exact WAV payloads were lost from the candidate-processing path;
- hashes and timestamps were preserved;
- no fabricated events replaced them;
- BirdNET remained unchanged;
- the issue was detected by the receiver drop ledger and health check.

Correction:

- remove post-ACK eviction;
- reject new nonduplicate admission before body read;
- withhold ACK;
- preserve Pi ownership;
- add regression and live one-slot tests.

The incident is part of provenance. It is not erased by the correction.

## Health contract

`fieldctl health` fails if any of the following is true:

- capture/listener inactive;
- capture not actually connected;
- success timestamps stale;
- producer drops or sequence gaps nonzero;
- producer/local queues approach bounds or stop moving;
- local dead-letter/drop evidence exists;
- disk guard crossed;
- SQLite quick-check fails;
- WAL exceeds guard;
- retained WAV/JSON pairs diverge;
- review storage approaches capacity.

“Service active” alone is not healthy.

## Recovery rules

### Disconnect

- inspect health and logs;
- confirm producer remains active;
- preserve Pi spool and ledger;
- restart only the private listener target if needed;
- verify upstream ready work drains and sequence catches up;
- treat any unexplained drop/gap as an incident.

### Full local queue

Do not delete ready files. Restore throughput/storage and allow upstream replay.

### Abandoned processing

Restart recovery returns uncommitted processing work to ready. Preserve state before manual intervention.

### Failed item

Preserve source and error record. Determine whether audio, bundle, storage, or code is at fault. Deleting a dead letter is not resolution.

### SQLite failure

Stop the private target and preserve database, WAL, SHM, spools, statuses, and evidence together. Work from a copy.

## Remaining validation gap

The system has not been physically power-cut during each durability boundary on the real storage stack. `fsync` and rename ordering are correct at the application level, but physical durability still depends on kernel, filesystem, controller, and device honoring flushes.