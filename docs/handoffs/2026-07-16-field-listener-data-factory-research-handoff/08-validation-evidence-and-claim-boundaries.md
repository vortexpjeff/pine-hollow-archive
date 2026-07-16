# 8. Validation evidence and claim boundaries

## Validation is layered

No single test establishes this system. The release case combines:

1. artifact identity;
2. unit/integration tests;
3. replay and fault injection;
4. live service observation;
5. sandbox enforcement probes;
6. database/evidence integrity checks;
7. independent read-only review;
8. human exact-span review.

Each layer supports different claims.

## Claim-evidence matrix

| Claim | Evidence | Status | Boundary |
|---|---|---|---|
| Public artifacts are exactly identified | public SHA-256, dataset hashes, Hub revisions, downloaded checksum verification | supported | does not reconstruct private row-level splits |
| Runtime uses frozen Perch and strict heads | runtime manifests, member checksums, bundle IDs, loader tests | supported | not a clean retraining proof |
| Public artifacts were not deployed | public model cards and July 15 audit | supported | historically true at public-release checkpoint |
| Later private broad-head exports were integrated | strict bundle source hashes, live loaded bundle IDs, listener ledger | supported | not public artifacts byte-for-byte; not ecological validation |
| Transport survives disconnect/lost ACK | outage replay and no-ACK full-frame test | supported | physical power cut not tested |
| Duplicate delivery is idempotent | exact recording/bundle/span keys and replay tests | supported | relies on preserved deterministic contracts |
| Queue pressure no longer causes post-ACK eviction | corrected admission rule, regression, live one-slot test | supported after incident | six earlier recordings were still lost |
| BirdNET is unchanged by listener | separate sidecar/service boundary and live BirdNET service checks | supported for documented build | does not audit future unrelated BirdNET changes |
| Listener sandbox hides unrelated state | live child-process mount/network probes | supported on deployed WSL environment | kernel/platform changes require recheck |
| Factory replay does not mutate evidence | insert-or-verify, append-only triggers, zero-work replay | supported | legacy pre-Commons archive conditions remain |
| Factory job ownership is durable | lease, heartbeat, expiry, retry tests and independent review | supported | heartbeat stop has one medium timing note |
| Scheduled line cannot claim GPU jobs | energy-class allowlist and live unattended cycles | supported | manual GPU command remains available by design |
| Factory entered unattended production | 11:40 no-work and 11:50 evidence-bearing timer cycles plus later successful cycles | supported | pipeline production is not model field certification |
| v4 packet is deterministic and immutable | manifest hash, replay checks, schema triggers | supported | new protocol versions create new manifests |
| Review is blind before judgment | UI tests and live use | supported for desk workflow | CLI recovery review is not inherently blind |
| Audio served is exact and path-safe | dual hash validation, descriptor-relative `O_NOFOLLOW`, focused regressions | supported on POSIX/WSL deployment | launcher readiness race remains UX-only |
| Review writes are atomic | transaction tests and 24 completed live reviews | supported | reviewer authority remains human-provided identity |
| First packet establishes recall | candidate/boundary/control design | **not supported** | complete review of bounded time blocks required |
| First packet calibrates model probabilities | scores are case-control outputs | **not supported** | no probability calibration model exists |
| Candidate count estimates abundance/occupancy | no detection/sampling model | **not supported** | separate ecological study required |
| Context links establish causality | nearest-time relation only | **not supported** | explicit causal study required |
| Sentinel check detects fresh model drift | current archive-side check does not rescore | **not supported yet** | approved inference bridge required |

## Automated test evidence

### Private field listener

The original acceptance recorded:

- 15 private field tests passed;
- Ruff passed;
- compileall passed;
- shell syntax passed;
- systemd unit verification passed.

The public InsectNet code suite recorded 26 passing tests at listener handoff. The final packet release gate reruns the current private listener suite and records the result in the release document.

### Factory before weekly desk

The hardened factory acceptance included:

- focused regressions for identity immutability, transaction atomicity, leases, watermarks, symlink rejection, and sandbox paths;
- full unittest and pytest suites;
- compileall;
- live dry-run;
- sandboxed manual and unattended service cycles;
- zero-work replay;
- repeated blocker/high read-only review.

### Final weekly desk

After the two final findings were corrected:

- 72/72 unittest passed;
- 72/72 pytest passed;
- compilation passed;
- diff checks passed;
- focused inactive-protocol sentinel and descriptor-safe audio regressions passed.

The final documentation release gate reruns the relevant suites and reports the fresh output in [Git and release record](12-git-and-release-record.md).

## Integrity evidence

### Field listener

At fixed snapshot:

- SQLite quick-check: `ok`;
- duplicate/gap/drop health issues: none;
- spool queues: all empty;
- evidence pair mismatch list: empty;
- capture and listener success fresh;
- exact loaded bundle IDs known.

### Factory

At fixed snapshot:

- schema 7;
- 68/68 jobs successful;
- latest factory run successful;
- timer enabled and active;
- one-shot service inactive between runs as designed;
- active v4 packet 24/24 complete;
- packet readiness still true;
- no active sentinels.

### Known legacy condition

Thirty-two `label_events -> clips` foreign-key violations predate Commons schema 4. SQLite integrity is `ok`; Commons-scoped violations are zero. This condition was not caused, hidden, or repaired by the two-day build.

## Fault-injection evidence

### Listener

| Test | Observation |
|---|---|
| Athena outage | four Pi recordings / 11,520,176 bytes accumulated and replayed |
| lost ACK | full 2,880,044-byte frame retained and replayed |
| local capacity one | second recording stayed upstream; no drops; drained after restore |
| committed evidence missing | replay rebuild path verified |
| committed evidence hash mismatch | rejected rather than accepted |
| restart with processing work | recovery returns uncommitted work to ready |

### Factory

| Test | Observation |
|---|---|
| same identity, changed material values | replay raises |
| downstream import failure | no partial event/media/window/assertion commit |
| same-size byte mutation with restored mtime | SHA-256 watermark changes and work schedules |
| symlinked source/config path | rejected before import |
| stale/foreign lease completion | rejected |
| later job after long first job | receives fresh claim time |
| unchanged sources | zero created jobs/handlers |
| changed retained evidence | complete import/context jobs succeed |
| repository write from sandbox | fails read-only |
| private runtime write | succeeds |

### Validation desk

| Test | Observation |
|---|---|
| stale/historical protocol review | rejected |
| historical protocol sentinel promotion | rejected |
| repeat reveal before review | hidden |
| one assertion write fails | entire review rolls back |
| audio path has symlink component | rejected |
| `Path.read_bytes()` path reopen | no longer used; descriptor-safe helper required |
| mismatched media/packet hash | audio rejected |
| non-loopback bind/Host | rejected |
| malformed/oversized POST | rejected |

## Independent review history

The build did not treat the first green test suite as acceptance. Read-only blocker/high reviews repeatedly found:

- mutable replay identities;
- stale lease time;
- incomplete transaction ownership;
- weak watermarks;
- symlink normalization;
- writable repository surface;
- active-protocol gaps;
- audio path check/open race.

Each blocking/high issue was traced, corrected, regression-tested, and re-reviewed before unattended operation resumed.

One final review correctly returned **NOT PASS** on the v4 desk because:

1. historical items could be promoted to sentinels;
2. checked audio paths were reopened by pathname.

The timer remained paused. Follow-up commit `16c2344…` closed both findings. Full suites passed, the timer was re-enabled, and immediate cycle `run_f74d6677628c45e5ada1f85e5d366c2a` succeeded.

## Human validation evidence

The completed v4 packet provides:

- 24 append-only reviews;
- 48 target labels;
- 22 distinct parent recordings;
- two exact hidden-repeat pairs;
- measured review burden;
- score-independent controls;
- both sides of both operational thresholds;
- exact source/media/span/model context.

It supports workflow feasibility and initial local descriptive patterns. It does not certify model performance.

## Remaining limitations by severity

### Blocking for ecological inference

- no complete bounded-time recall study;
- no probability calibration;
- no detection/occupancy/abundance model;
- no multi-season or multi-site validation;
- no multi-reviewer study;
- private dev2 training runs were not clean-commit reproductions;
- no approved fresh-rescore sentinel bridge.

### Important engineering follow-up

- physical power-cut campaign across producer/receiver/SQLite boundaries;
- longer soak monitoring of queue/WAL/storage guards;
- stress reproduction for heartbeat shutdown under prolonged SQLite blocking;
- fix Windows launcher’s browser-before-server readiness race;
- periodically re-probe sandbox enforcement after WSL/systemd updates.

### Recorded non-blocking condition

Heartbeat shutdown performs a timed join. Under unusual prolonged SQLite blocking the thread may remain alive briefly after stop returns. Ownership and lease checks still reject stale terminal writes, and expired jobs remain recoverable.

## Honest release statement

The engineering pipeline is accepted for private evidence accumulation under bounded unattended operation. The models remain experimental screening instruments. The first human audit is a successful protocol execution and an informative local sample—not a field-accuracy certification.