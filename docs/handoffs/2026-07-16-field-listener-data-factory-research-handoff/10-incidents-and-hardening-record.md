# 10. Incidents and hardening record

## Why this record exists

A research handoff that only describes final success is incomplete. This chapter records material failures, rejected designs, independent-review findings, and documentation corrections across both days.

## 1. Public model-release privacy and inference documentation correction

### Found

The post-publication audit found:

- a site-identifying compact string in four public acquisition-script User-Agent values;
- a ChickenNet usage example that bypassed serialized hierarchy behavior;
- reproducibility wording too broad for artifacts whose row-level manifests remained private.

### Corrected

- replaced all four User-Agent strings;
- expanded privacy regex coverage across spaced, compact, hyphenated, and underscored variants;
- changed usage to the hierarchy-aware helper;
- narrowed reproducibility claims;
- regenerated inventories and republished.

### Verification

- corrective commit `16c71e04…`;
- 25 tests passed at public release correction;
- Hub inventory entries downloaded and rehashed;
- model binary hashes unchanged;
- final Hub revisions recorded.

### Lesson

A privacy scan must cover semantic variants, not one literal spelling. Public documentation examples are part of the inference contract.

## 2. Private dev2 runs were generated from a dirty worktree

### Recorded fact

Both private dev2 run reports identify Git commit `16c71e04…` but also record modified training script, candidate implementation, and tests.

### Current mitigation

- exact dev2 joblib hashes;
- exact dataset/embedding/window hashes;
- exact strict runtime export members;
- runtime bundle loader checks;
- pinned Perch tree.

### Unresolved reproducibility gap

The original dev2 training runs are not clean-commit reproductions. A formal successor release should rerun from a clean pinned tree and compare artifacts/metrics.

### Lesson

Artifact identity can make deployment deterministic without making the original training execution fully reproducible.

## 3. Six recordings lost after receiver ACK

### Found

During sandbox restart testing, a Pi backlog replayed faster than Perch inference. Athena ACKed durable receipt, then the old local retention policy evicted six ready WAVs to enforce its 32-file limit.

### Impact

- six payloads lost from candidate processing;
- hashes/timestamps preserved;
- no fabricated replacements;
- BirdNET unaffected.

### Root cause

The design combined:

1. ACK as ownership transfer;
2. post-ACK receiver eviction.

Once the Pi receives ACK it may delete its copy. Eviction afterward creates irreversible loss.

### Corrected

- remove destructive retention path;
- check ready + processing capacity before body admission;
- close without ACK when full;
- leave source ready upstream;
- allow duplicates for idempotent ACK recovery.

### Verification

- one-item unit regression;
- live one-slot queue test;
- no producer drops;
- no sequence gaps;
- both queues drained after restore.

### Lesson

Backpressure must occur before acknowledgement.

## 4. `active` service did not guarantee connected capture

### Found

A systemd unit could be active while capture status said disconnected.

### Corrected

Health now requires actual connected state and fresh protocol success, not only unit state.

### Lesson

The process manager proves a process state, not application-level dataflow.

## 5. WSL user-systemd path declarations did not enforce expected isolation

### Found

Unit properties appeared configured while a live child could still see unrelated home state.

### Corrected

A tested unprivileged user/mount namespace wrapper overlays private roots and restores only required binds. Listener also receives a private network namespace.

### Verification

Actual child processes were probed for filesystem and namespace visibility.

### Lesson

Security controls are claims until verified on the running manager and kernel.

## 6. Existing acoustic identity could silently accept changed values

### Risk

A replay could reuse deterministic identity while score, threshold, source event, class, bundle, or preprocessing changed.

### Corrected

Insert-or-verify compares the full material contract. Mismatch raises. Append-only database triggers block mutation/deletion.

### Verification

Regressions cover changed scores, thresholds, sources, and model context.

### Lesson

Idempotency means same identity and same material fact—not “ignore any conflict.”

## 7. Terminal job transitions could outlive lease ownership

### Risk

A duplicated or delayed worker could complete after lease loss.

### Corrected

- explicit lease owner/expiry;
- fresh live time on each transition;
- separate-connection heartbeat renewal;
- owner/unexpired checks;
- expired-job recovery;
- immutable transition ledger.

### Verification

Ownership, expiry, heartbeat, retry, recovery, and stale terminal writes are covered.

## 8. Later job claims reused cycle-start time

### Risk

A long first job could make a later job’s “new” lease shortened or already expired.

### Corrected

Removed fixed `now` from worker execution. Every claim, heartbeat, completion, and failure obtains fresh live/injected UTC time.

### Verification

AST gate found no fixed-time callers; focused/full tests and live service passed; independent lease review passed.

## 9. Field import could commit partial evidence

### Risk

Event/media could commit before all windows/assertions, leaving incomplete model lineage.

### Corrected

One transaction now owns event, media, every window, and every assertion.

### Verification

A forced downstream failure leaves no partial state.

## 10. Source watermark could miss same-size byte drift

### Risk

Name, size, and mtime cannot detect same-size mutation with restored mtime.

### Corrected

The watermark hashes retained WAV bytes and relevant sidecars/manifests/bundle members.

### Trade-off

Scheduling and import both hash bytes. Extra I/O is accepted for change detection and verification.

## 11. Symlink resolution erased evidence of redirection

### Risk

Resolving before validation turned a symlinked path into an ordinary destination path.

### Corrected

Configured paths are absolutized without resolving. Strict validation walks existing components and rejects symlinks.

Applied to field ledger, evidence, bundles, context, incident, media, watermark, and CLI source paths.

## 12. Factory repository was writable to service

### Risk

A defective/compromised worker could alter code or documentation.

### Rejected approach

Exact writable exceptions for DB/WAL/SHM failed because SQLite removes WAL/SHM when the final connection closes, leaving bind paths absent.

### Corrected

- canonical DB moved into private runtime tree;
- root `archive.db` became compatibility link;
- entire repository read-only;
- only private runtime and dedicated cache writable.

### Verification

Exact mount-policy probe showed repository write `EROFS` and private write success. Installed units matched repository copies and passed systemd verification.

## 13. Historical field-loss ledgers could be misrepresented as media

### Risk

Hashes/timestamps from unavailable lost recordings might be turned into synthetic media/event rows.

### Corrected handling

The factory validates/hashes/copies incident ledgers immutably and appends incident research records. It creates no media event without actual audio.

### Lesson

A loss record is evidence of absence of evidence, not a recording.

## 14. Preliminary weekly protocols had scientific/interface defects

Protocols v1–v3 were frozen during development. Findings included:

- control selection influenced by score/history rather than fully score-independent order;
- incomplete active-protocol enforcement;
- repeat identity/reveal leakage;
- non-atomic two-assertion review paths;
- report denominators vulnerable to repeated parent recordings;
- insufficient distinction between descriptive intervals and design-based claims.

### Corrected in v4

- controls selected first under deterministic score-independent parent hash;
- one global allocation planner;
- active protocol enforced across routine review paths;
- hidden repeat lineage concealed until after judgment;
- one atomic review transaction;
- parent-deduplicated cumulative performance;
- explicit interval and scientific limitations.

Historical manifests were not rewritten.

## 15. Historical-protocol items could be promoted to sentinels

### Found by final independent review

A completed decided item from an inactive protocol could theoretically enter the sentinel set.

### Corrected

Core promotion joins packet protocol and requires the active version, not only a completed review.

### Verification

Focused inactive-protocol regression plus full 72-test suites.

## 16. Audio path was checked and then reopened by pathname

### Found by final independent review

Component-wise symlink checks occurred before `Path.read_bytes()`. A local same-user path swap between check and open was theoretically possible.

### Corrected

The desk now:

1. opens the root;
2. traverses each component relative to the previous directory descriptor;
3. uses `O_NOFOLLOW`;
4. requires a regular final file;
5. reads, hashes, and slices from that same final descriptor.

### Verification

Focused test proves the old pathname read is not used; symlink and hash mismatch tests remain.

## 17. Factory timer remained off after development

### Event

The timer was correctly paused before editing production-consumed worker/schema code. It remained off after initial wrap because final review was NOT PASS.

### Resolution

After the two findings above were corrected and 72/72 unittest + 72/72 pytest passed:

- timer re-enabled;
- immediate due cycle succeeded;
- next ten-minute tick scheduled;
- restart logged and committed.

### Lesson

Operational holds must be named explicitly. An inactive one-shot service is normal; an inactive timer is not.

## 18. Validation launcher can race server startup

### Observed

The Windows launcher opens the browser before starting the local server process. The initial page can show a connection error or JSON `not_found`; a refresh after the server starts works.

### Status

Open nonblocking UX issue. It does not alter review data or server security. The final packet documents the workaround rather than claiming readiness synchronization exists.

## 19. Known heartbeat shutdown timing note

The heartbeat thread receives a timed join. Under unusually prolonged SQLite blocking it could remain alive briefly after stop returns.

Release remains bounded because:

- heartbeat requires current unexpired ownership;
- terminal transitions use fresh time;
- stale/foreign writes are rejected;
- expired running jobs are recoverable.

A future change should be driven by a real or stress-reproduced occurrence.

## 20. Chronology/documentation confusion

### Problem

Earlier summaries said the July 15 research artifacts were not deployed. Later reports described broad heads active in a private listener. Without artifact/version/time distinctions, this sounded contradictory and caused an earlier infographic error.

### Correction in this packet

The chronology distinguishes:

- public 0.2.0/0.1.0 artifacts: never deployed;
- later private dev2 joblibs: trained later, initially not deployed;
- strict dev2 broad-head exports: later integrated privately for review-only inference;
- downstream factory: unattended production July 16;
- model ecological status: still unvalidated for unattended inference.

### Lesson

Deployment status belongs to an exact artifact, component, purpose, and timestamp.

## Open conditions not erased by release

- six historical lost WAVs;
- dirty-worktree dev2 training provenance;
- no physical power-cut campaign;
- no fresh-inference sentinel bridge;
- one small weekly human packet;
- launcher readiness race;
- heartbeat timed-join note;
- 32 pre-existing legacy archive foreign-key violations;
- no field recall/calibration/ecological study.

The final system is stronger because these remain visible.