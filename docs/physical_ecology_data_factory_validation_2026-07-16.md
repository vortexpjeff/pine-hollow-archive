# Physical-Ecology Data Factory Validation — 2026-07-16

## Release scope

Validated Phases 1–3:

- strict field evidence import;
- exact acoustic-window records;
- independent model/human assertions;
- score-stratified review queues;
- non-causal camera/Observatory context;
- deterministic CPU/GPU job ledger;
- bounded CPU automation service;
- explicit GPU inventory lane;
- append-only research/development records.

## Automated tests

Command:

```bash
python3 -m unittest discover -s tests -v
```

Result before live release gate:

```text
Ran 37 tests in 4.733s
OK
```

After retry-backoff and watermark corrections, the 12 dedicated data-factory tests also passed.

Coverage includes:

- additive/idempotent migration;
- append-only guards;
- strict source identity joins;
- hash mismatch failure before event creation;
- exact sample spans and threshold state;
- import replay;
- human correction by supersession;
- deterministic score bands;
- timezone-aware nearest context;
- same-site and tolerance constraints;
- immutable Observatory copy;
- deterministic enqueue;
- job/energy allowlist;
- one-worker leases;
- expired-lease recovery;
- retry caps;
- lease-owner enforcement;
- CPU-cycle replay;
- CPU/GPU lane separation;
- GPU inventory result parsing;
- source-ledger mtime churn does not enqueue import work.

## Static verification

```bash
python3 -m py_compile commons_lab/*.py scripts/*.py
```

Result: exit 0, no output.

```bash
systemd-analyze --user verify \
  deploy/systemd/pine-hollow-data-factory.service \
  deploy/systemd/pine-hollow-data-factory.timer
```

Result: unit syntax accepted. Repository copies on DrvFS produced expected executable/world-writable permission warnings. Installed ext4 copies require mode 0644.

## Read-only live source validation

```bash
python3 scripts/run_data_factory.py dry-run
```

Result:

- writes: false;
- retained field recordings validated: 103;
- deployed bundles validated: 2;
- ChickenNet threshold: 0.9999;
- InsectNet threshold: 0.9995;
- score semantics preserved as uncalibrated case-control ranking score;
- Observatory payload parsed with timestamp.

## Backup and migration-copy gate

Backup:

```text
private/backups/archive-pre-data-factory-20260716T133038Z.db
```

- bytes: 46,477,312
- SHA-256: `0c2c8c27273168c5b3dfec55a8706a640a9f600a13948e8c99b2b23e7b9d923d`

Migration-copy result:

- target schema version: 4;
- six new tables present;
- SQLite integrity: `ok`;
- pre-existing table counts unchanged except schema-version row;
- pre-migration foreign-key violations: 32;
- post-migration foreign-key violations: 32;
- violation sets identical.

Legacy violations are `label_events` rows 87–118 referencing absent `clips` parents. New Commons foreign-key violations: zero.

## First live CPU cycle

Status: success.

| Stage | Result |
|---|---:|
| retained recordings discovered | 103 |
| recordings imported | 103 |
| exact windows inserted | 618 |
| model assertions inserted | 206 |
| immutable Observatory snapshots | 1 |
| visual context links | 11 |
| environmental context links | 1 |
| Commons FK violations | 0 |
| GPU jobs automated | false |

## Replay behavior

Initial replay exposed an overly broad source watermark: field database/WAL activity enqueued an unnecessary import, though import itself created zero records.

After regression test and correction:

- compatibility cycle created one new watermark job;
- import found 103 existing events and inserted zero rows;
- following cycle created zero jobs;
- following cycle ran zero jobs.

This is the accepted steady state.

## Explicit GPU lane

Job: `gpu_environment_probe`

Worker energy permission: `deferrable_gpu`

Status: success.

Observed:

- NVIDIA GeForce RTX 4090;
- total VRAM: 24,564 MiB;
- free VRAM: 22,411 MiB;
- utilization: 12%;
- driver: 610.62.

The automated CPU cycle enqueued no GPU job. No model training or inference was started.

## Calibration queue

```bash
python3 scripts/run_data_factory.py queue-calibration --per-band 10
```

Inserted:

- ChickenNet: 12
- InsectNet: 29
- total: 41

No threshold or training manifest changed.

## Live post-cycle counts

- Commons events: 158
- Commons media: 158
- acoustic windows: 618
- assertions: 206
- event links: 12
- review queue: 41
- jobs: 8, all successful
- job transitions: 24 at validation time

## Privacy and boundary verification

- Field SQLite opened read-only.
- Field WAVs/sidecars retained in place and not modified.
- Observatory source read only; immutable copy stored privately.
- Acoustic and context events private and publication-blocked.
- Website unchanged.
- BirdNET-Pi unchanged.
- Field-listener services unchanged.
- Camera service unchanged.
- No automatic GPU job.
- No commit or push.

## Service deployment

- Installed user units under `~/.config/systemd/user/` with mode 0644.
- Sandboxed manual service cycle: success, zero new work.
- Immediate timer-triggered cycle: success, zero new work.
- Timer: enabled and active, ten-minute cadence.
- GPU jobs automated: false.

## Field-listener post-deployment health

- capture connected: true;
- sequence gaps: zero;
- producer drops: zero;
- database check: `ok`;
- health issues: none;
- capture and listener units: active;
- 3,211 recordings and 19,266 scores at final live check.

The separately queried legacy name `insectnet-pi-spooler.service` was inactive because it is not the deployed unit name. The listener reports `insectnet-field-capture.service` and `insectnet-field-listener.service`, both active.

## Final release actions

- Run final full test suite and diff checks.
- Complete independent specification and code-quality reviews.
- Record any review-driven correction as a new development/validation entry.

## Review-driven hardening validation

This later section records completion of those release actions and supersedes only the pending checklist above. It does not rewrite the original 103-record release evidence.

### Automated verification

- dedicated data-factory suite: 21/21 passed;
- complete unittest suite: 46/46 passed;
- complete pytest suite: 46/46 passed;
- `compileall` for `commons_lab`, `scripts`, and `tests`: exit 0;
- systemd unit verification: accepted;
- installed service and timer modes: 0644.

New regression coverage includes assertion immutability, divergent replay rejection, atomic recording rollback, lease heartbeat and expiry enforcement, Observatory temporal eligibility, tolerance-aware job identity, current-nearest link selection, retained-ledger/WAV watermark changes, human-review lineage, destination symlink rejection, and incident-ledger replay.

### Incident provenance

Verified field sources:

- summary SHA-256: `1e7a5919a8314a6163cd18923846f5f30871c32bfdb5743075d655b6805d8ab7`;
- six-row JSONL SHA-256: `9c40e19757d7f84cb266f3c7523be6446a2343c945e580ddc5c0450670d3958c`.

The JSONL records six `spool_limit` losses with recording hashes and UTC drop times. Both archived private copies reproduce the source hashes exactly. Two new `incident` research records carry `missing_media_recovered: false`. No media or acoustic events were synthesized for the lost WAVs. A third incident research record already present in the archive concerns the separate legacy foreign-key condition.

### Hardened source and live cycles

Read-only dry-run:

- retained recordings validated: 112;
- deployed bundles validated: 2;
- writes: false.

First manual cycle:

- 103 existing and 9 newly imported recordings;
- 54 windows and 18 model assertions inserted;
- 2 incident files copied and 2 incident records appended;
- 1 temporally eligible Observatory snapshot archived;
- 20 visual and 10 environmental links inserted;
- GPU jobs automated: false.

The settling cycle created one context-reconciliation job because the archived-event watermark changed after scheduling; it inserted zero links. The next direct replay created zero jobs and ran zero handlers. The subsequently installed sandboxed service replay also created zero jobs and ran zero handlers.

### Final live state

- schema version: 5;
- Commons events/media: 171 / 171;
- acoustic events: 112;
- exact windows: 672;
- assertions: 224;
- raw/current context links: 42 / 42;
- incident research records: 3 total, including 2 field-loss ledger versions;
- jobs: 15 successful, 0 non-success;
- SQLite integrity: `ok`;
- Commons foreign-key violations: 0;
- legacy `label_events → clips` violations: unchanged at 32.

### Service boundary

- hardened user unit passed a real sandboxed run with `ExecMainStatus=0`;
- code, scripts, tests, docs, deployment files, and `.git` are read-only overlays;
- field-listener and Observatory source trees remain read-only;
- timer re-enabled and active on the ten-minute cadence;
- no GPU job automation;
- no website, BirdNET-Pi, field-listener, camera, model, threshold, training manifest, commit, or push mutation.

Private files under the Windows-mounted repository display DrvFS synthetic mode bits; Linux `chmod` is authoritative only for installed ext4 unit files. Windows ACLs remain the filesystem access boundary for repository-private data.

## Final blocker-review closure

A final production-only reviewer rejected release on three high-severity boundaries:

1. retained WAV watermarks used filename/size/mtime but not current bytes;
2. several source paths were resolved before symlink checks;
3. the systemd unit still reopened the repository root writable for SQLite sidecars.

All three were reproduced with failing tests before correction.

### Corrective implementation

- retained WAV SHA-256 bytes now enter every field watermark, so a same-size mutation with restored `mtime_ns` still changes job identity;
- `commons_lab/safe_paths.py` rejects symlinks in every existing component before strict resolution;
- field ledger, bundles/members, review roots, retained WAVs/sidecars, Observatory snapshots, incident ledgers, generic media, scheduler watermarking, and Observatory eligibility use that policy;
- the canonical database moved to `private/commons_lab/runtime/archive.db`;
- repository `archive.db` is a relative compatibility symlink to that canonical target;
- SQLite resolves the target before placing WAL/SHM, keeping all write artifacts in the private runtime directory;
- the whole repository is read-only in the service namespace; only `private/commons_lab/` and the dedicated cache/lock directory are writable.

An attempted exact-file WAL/SHM mount was deliberately tested and rejected: SQLite removes the sidecars when the last external connection closes, causing a later systemd namespace start to fail before execution. The runtime-directory design replaced that brittle approach. No timer run occurred during the experiment.

### Safety and replay evidence

- pre-runtime-move backup: `private/backups/archive-pre-runtime-move-20260716T145707Z.db`;
- backup SHA-256: `aafb081b64e87ecb21c8738f92b08dcc72efeb2f738550ad04c52992489bb92a`;
- integrity before and after the same-filesystem move: `ok`;
- strict sandbox service run: exit 0;
- transient mount-policy probe: repository-root write blocked with `EROFS` (`errno 30`), private runtime write succeeded, no probe files remained;
- settling context job: zero inserted links;
- following strict replay: zero new jobs and zero handlers.

Two additional retained recordings arrived during review and were imported by the first byte-aware sandbox run: 12 windows and 4 assertions. One eligible Observatory version and five non-causal context links were also preserved.

### Final automated verification

- focused factory suite: 27/27 passed;
- full unittest suite: 52/52 passed;
- full pytest suite: 52/52 passed;
- Python compilation: clean;
- untracked-file whitespace scan: clean;
- production diff whitespace gate: clean outside the two pre-existing user-edited scripts.

### Final live state after blocker closure

- schema version: 5;
- Commons events/media: 182 / 182;
- acoustic events: 118;
- exact windows: 708;
- assertions: 236;
- raw/current context links: 57 / 54;
- jobs: 32 successful, 0 non-success;
- SQLite integrity: `ok`;
- Commons foreign-key violations: 0;
- legacy `label_events → clips` violations: unchanged at 32;
- service last result: success, exit 0;
- timer: enabled and active after the final corrected-production review passed.

The next reviewer found one additional source-boundary bypass in the CLI: `make_config()` resolved paths before handing them to the strict library layer. It now performs only expansion and absolute-path normalization, preserving symlink components for rejection. A CLI-level regression test proves a symlinked review root remains visible and is rejected by the byte-aware watermark path.

One more retained recording arrived during that final CLI validation and was imported under the strict sandbox: 6 windows, 2 assertions, and 3 non-causal context links. Its reconciliation inserted zero links, and the following service replay created zero jobs and ran zero handlers.

The same review described `private/commons_lab/` write access as broader than the database runtime directory. That is not the implemented contract: `runtime/` contains the canonical database and SQLite sidecars, while sibling `observatory_snapshots/` and `field_incidents/` contain intentionally writable private immutable evidence. The service grants the documented private data root and lock tree, not arbitrary repository paths. The direct mount probe proves the repository root remains read-only.

The final lease review found terminal `complete_job()` / `fail_job()` calls still reused the cycle-start timestamp supplied by production scheduling. They now always call the live clock after handler/heartbeat shutdown. A regression test with a one-second lease and a two-second terminal clock proves completion and failure transitions are both rejected, leaving the expired running job for normal lease recovery. Historical-clock tests now inject explicit test clocks rather than weakening production behavior.

A follow-up lease review found the same cycle-start timestamp was still supplied to every claim, shortening later leases. The fixed-time parameter was removed from `run_jobs()` entirely. Each claim, completion and failure now gets a fresh live/injected clock reading; both production callers were updated, and an AST check confirms there are no `run_jobs(now=...)` call sites.

One more retained recording and one eligible Observatory version arrived during live lease validation. The strict service imported 6 windows and 2 assertions, added 3 non-causal context links, reconciled with zero additional links, then produced a zero-job/zero-handler replay.

One further retained recording arrived during fresh-claim validation. It added 6 windows and 2 assertions; reconciliation added one valid nearest-visual link, and the following replay created zero jobs and ran zero handlers.

### Final independent verdict

The last read-only lease-flow review returned **PASS** with no blocker or high-severity finding. It verified fresh clocks for every claim, heartbeat, completion and failure; removal of the fixed-time worker API; timezone-aware lease enforcement; atomic expiry recovery; and safe rejection/recovery after heartbeat failure.

One non-blocking medium note remains: heartbeat shutdown uses a timed thread join, so prolonged SQLite blocking could leave the heartbeat thread alive briefly after `stop()` returns. Existing ownership and expiry checks preserve correctness. This is recorded as future hardening, not a release blocker.

### Unattended timer proof

The first scheduled post-release cycle fired at `2026-07-16 11:40:16 EDT` without manual intervention and completed at `11:40:17 EDT`:

- run ID: `run_5961775786fb4719ab9c0c235bf75ffd`;
- status: `success`;
- new jobs: 0;
- handlers run: 0;
- GPU automation: false;
- service result: success, exit 0;
- timer remained active and waiting for the next 10-minute boundary;
- SQLite integrity remained `ok`;
- Commons foreign-key violations remained 0;
- all 29 jobs remained successful.

This is the final production acceptance evidence: the installed timer woke the sandboxed worker on schedule, found the archive settled, performed no unnecessary work, and returned cleanly to the waiting state.

The next unattended cycle fired at `2026-07-16 11:50:48 EDT` and exercised the non-empty path:

- run ID: `run_13a3cf0bb4914c3486881397e53e9cfd`;
- status: `success`;
- one newly retained field recording imported;
- 6 acoustic windows and 2 assertions appended;
- one eligible Observatory snapshot archived immutably;
- one environmental and one visual non-causal context link appended;
- all 3 new jobs completed successfully;
- GPU automation remained false;
- SQLite integrity remained `ok`;
- the timer returned to waiting with its next run scheduled for `12:00:48 EDT`.

Together, the 11:40 no-work cycle and 11:50 evidence-bearing cycle verify both ordinary production branches under unattended scheduling.

## Additive schema-6 weekly field-validation release

This section is additive. It does not revise the schema-5 counts or acceptance evidence above.

The weekly field-validation release adds:

- one deterministic 24-item packet per local week;
- 22 parent-unique items plus two hidden repeats;
- balanced positive and boundary lanes for both diagnostic heads;
- score-independent random controls;
- exact five-second review audio with optional full-recording context;
- a separate dependency-free loopback review desk;
- server-side blinding until an append-only judgment is saved;
- one atomic review transaction producing two human assertions;
- `training_eligible=false` for every validation assertion;
- Wilson intervals, score-band outcomes, control findings, repeat agreement, coverage and burden reporting;
- manually promoted artifact sentinels with append-only drift checks;
- explicit `fresh_audio_rescore_performed=false` until a separate inference bridge is approved;
- fixed scheduled-CPU handlers for packet creation and sentinel checks;
- no GPU, model, threshold, field-listener, BirdNET, camera, website or publication change.

Focused pre-install verification:

- validation protocol/schema/metrics/automation tests: 12/12 passed;
- loopback desk/audio/security tests: 2/2 passed;
- existing factory regression suite: 27/27 passed;
- CLI command discovery: passed.

The complete scientific and operational contract is recorded in [`weekly_field_validation_desk.md`](weekly_field_validation_desk.md). Live schema migration, packet creation, localhost audio checks, sandboxed worker execution, integrity gates and independent reviews are recorded after they are exercised rather than predicted here.

### Actual schema-6 deployment sequence

The installed ten-minute service reads the working tree directly. Its 13:14 EDT unattended cycle therefore loaded the completed schema/job implementation before the later explicit stop point. That cycle migrated the canonical database to schema 6 and successfully created the first immutable packet. This sequence is recorded as observed rather than rewritten as a staged manual migration.

- packet job: `job_e5ad112a645b788615136c21`;
- packet: `vpk_993f9ab5b2d01796a72de2b4`;
- local week: `2026-07-13`;
- created: `2026-07-16T17:14:49.388444+00:00`;
- manifest SHA-256: `fafddfddd9a4c6ac8d982656877b174be4b4d77a8be21859144459c7e22c2e74`;
- items: 24;
- non-repeat parent recordings: 22 / 22 unique;
- lane counts: 8 model-positive, 8 boundary, 6 random-control, 2 hidden-repeat;
- per class: four model-positive and four boundary;
- boundary balance per class: two above and two below threshold;
- reviews at acceptance: 0.

The timer and service were then stopped before further live verification. A post-migration, pre-review SQLite safety backup was created at `private/backups/archive-pre-validation-v6-20260716T172058Z.db`, SHA-256 `d4115a113f34711f80f02c9f3cb2a1cd27896676b1781d03d6977d2d2191c459`, with integrity `ok`.

### Native-source audio correction

The first live packet audit correctly rejected playback because retained field WAVs are 48 kHz while model spans are indexed in the 32 kHz inference timeline. No review had been written. A failing 48 kHz-source / 32 kHz-span regression was added before correction.

The desk now converts model sample boundaries to elapsed time and then to nearest native source frames. It preserves source PCM format/rate and performs no resampling. All 24 live packet windows subsequently passed byte-hash verification and produced exactly five seconds at 48 kHz (240,000 frames), with zero observed duration error.

### Final automated and live verification

- full unittest suite: 66/66 passed;
- full pytest suite: 66/66 passed;
- Python compilation: clean;
- production diff whitespace gate: clean outside the two pre-existing user-edited scripts;
- new-file whitespace: clean;
- live packet manifest hash recomputation: match;
- all 24 live exact-window audio payloads: hash-verified and duration-correct;
- localhost health: pass;
- pending-page model/score/threshold/selection blinding: pass;
- tokenless audio request: HTTP 403;
- non-loopback Host request: HTTP 421;
- manual bounded-CPU run `run_2c582b70ee3a415a978fc1c84c0e90bd`: success;
- installed sandbox run `run_2811af22a56d48e1a182f2621d3fb3de`: success, `ExecMainStatus=0`;
- sandbox reconciliation: zero links inserted;
- validation packets/items/reviews: 1 / 24 / 0;
- all 51 jobs: successful;
- SQLite integrity: `ok`;
- Commons foreign-key state: clean apart from the unchanged 32 documented legacy `label_events → clips` rows;
- GPU automation: false.

### Control-independence hardening before review

A final internal sampling audit found that the first packet selected random controls after score-driven lanes. A second protocol selected controls first but still preferred recordings absent from prior packets; because prior packet membership was score-driven, that remained indirect score dependence. Neither packet had any human review.

At this stage of validation, the active protocol was `weekly_blinded_v3`:

- controls are selected first from the full aligned parent-recording frame;
- control selection ignores model scores;
- control selection ignores prior packet membership;
- a week-specific deterministic seed provides rotation;
- a regression changes every model score and prior-history membership while requiring the control event set to remain identical.

Historical zero-review packets remain immutable evidence but are filtered out of the routine desk:

- v1: `vpk_993f9ab5b2d01796a72de2b4`;
- v2: `vpk_82f460a25a050e3fdff50b9a`.

The packet active at that stage was:

- v3: `vpk_7ba32f5325a2d82998526715`;
- manifest SHA-256: `a85c153972528d98cd40ec124d69ae856b05192aeae4b0e86765f5f2ca535ea3`;
- state: ready;
- items: 24;
- reviews: 0;
- 22 / 22 unique non-repeat parent recordings;
- controls match a direct full-frame control-sampler recomputation;
- lane balance: 8 positive, 8 boundary, 6 control, 2 hidden-repeat;
- per-class boundary balance: two above and two below;
- all 24 source windows: 48 kHz, exactly five seconds, hash-verified;
- manifest SHA-256 recomputation: match;
- routine desk shows v3 and hides v1/v2.

The v3 worker run `run_8e6ededa5ea94c3da8b9799eda3afea9` completed successfully with GPU automation false. Final post-hardening verification is 68/68 unittest and 68/68 pytest, with clean compilation and production diff checks.

### Independent-review corrections: protocol v4 and schema v7

Independent scientific and operational review rejected v3 for general use despite its clean live packet. The implementation used event identity rather than the archived physical `source_recording_id`, cumulative intervals could count a reused parent more than once, control metadata claimed uniformity while date/hour diversity still affected rank, readiness did not execute the full allocation, packet/item deletion and sentinel mutation were not fully guarded, and audio serving reopened verified paths while logging bearer tokens.

The corrected active code protocol is `weekly_blinded_v4` and the Commons schema is version 7:

- every candidate, history set, non-repeat exclusion, manifest item, and report carries frozen `source_recording_id`;
- two event rows or neighboring windows from one physical recording remain one sampling unit;
- controls are the first six parent identities under the deterministic week hash, with no score/history/date/hour weighting;
- readiness and generation use one global allocation planner;
- packet/item deletion and sentinel update/deletion are blocked;
- replay verifies manifest hash, header, item count, and every frozen item field;
- cumulative summaries use at most one reviewed item per source recording;
- Wilson intervals are labeled descriptive for the realized sample, not design-based population intervals;
- audio paths reject symlinks in any component, source bytes are read once and hashed once, and slices are made from those verified bytes;
- inactive-protocol audio is rejected;
- bearer tokens are redacted from request logs.

Focused post-correction verification passed 17 factory-validation tests and 3 Validation Desk tests. No v4 live packet had been created at this checkpoint; v1-v3 remained historical with zero reviews and the timer remained stopped.

### Verified live v4 checkpoint

After the full corrected tree passed 72/72 unittest and 72/72 pytest, a SQLite backup was created at `private/commons_lab/backups/archive-pre-validation-v4-20260716T143640-0400.db` with SHA-256 `ee87239b6cf339493b7b83e8dc45399d0cf9461f2d8d8b14a17d8fee9b92c5a6` and integrity `ok`.

Schema 7 verification found all 72 historical packet items backfilled with non-null source-recording IDs and all packet/item/sentinel guards installed. Manual CPU run `run_3424e605c48444f2b16dda463a407c4a` then created the first v4 packet:

- packet: `vpk_31d5158ef95e1fe35caff3e4`;
- manifest SHA-256: `bf7da3f8cad4d98fd7a76cc87cf4511e8428ff6b8b3bf127cb8beffe702cbd5e`;
- state: ready;
- items/reviews: 24 / 0;
- 22 distinct frozen non-repeat source recordings;
- lanes: 8 positive, 8 boundary, 6 control, 2 hidden repeat;
- controls exactly matched an independent full-frame deterministic-uniform hash recomputation;
- manifest replay returned the same packet after verifying every frozen row;
- all 24 audio windows were hash-verified 48 kHz stereo WAVs with exactly 240,000 frames;
- the real loopback desk served active v4 audio with HTTP 200, rejected historical v3 audio with HTTP 400, hid v1-v3 from routine navigation, and redacted bearer tokens in logs;
- all 63 factory jobs were successful, SQLite integrity was `ok`, and the unchanged 32 documented legacy foreign-key rows remained;
- installed systemd units were mode 0644 and verified with `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=yes`, and `NoNewPrivileges=yes`;
- factory timer and service remained inactive.

### First completed weekly human audit

The operator completed all 24 v4 judgments on 2026-07-16. The packet closed with 24 reviews over 22 distinct source recordings and two hidden repeats.

- insect model-positive lane: 4/4 reviewed windows marked present;
- insect boundary lane: 2/2 above and 2/2 below threshold marked present;
- insect random controls: 4/6 marked present;
- chicken model-positive lane: two present, one absent, and one uncertain across four reviews (2/3 among decided labels);
- chicken boundary lane: 0/2 above and 1/2 below threshold marked present;
- chicken random controls: 1/6 marked present;
- hidden-repeat agreement: 100% for insect presence, chicken presence, and signal quality across both pairs;
- review burden: 625.8 seconds total (10.4 minutes), with a 23.9-second median per item;
- uncertainty: one uncertain label among 48 presence labels.

This packet supports a practical field-utility audit, not recall, abundance, occupancy, or causal claims. The strong insect result and insect-positive random controls justify examining candidate burden and threshold calibration in later packets. The small chicken cells are insufficient for broad performance claims.

### Open release findings retained at wrap-up

The final read-only v4 review found two unresolved hardening issues:

1. sentinel promotion checks that an item is completed but does not yet reject an inactive historical protocol at the core function;
2. audio bytes are read and hashed once after component-wise no-symlink validation, but the final pathname open is not descriptor-relative `openat`/`O_NOFOLLOW` traversal and therefore retains a narrow local check/open race.

Neither finding altered the completed packet or reviews. No sentinel was promoted. The factory timer and service remained inactive at wrap-up. These items are recorded rather than hidden or expanded into another repair cycle during this session.

### Follow-up closure before factory restart

Both recorded findings were closed in a bounded follow-up:

- sentinel promotion now joins the item's packet and rejects any protocol other than the active `PROTOCOL_VERSION`;
- Validation Desk audio now traverses from the filesystem root with descriptor-relative `open(..., dir_fd=...)`, `O_DIRECTORY` for parent components, and `O_NOFOLLOW` for every component. It verifies a regular final descriptor, reads bytes from that descriptor once, and hashes/slices those same bytes without a pathname reopen.

Focused regressions cover inactive-protocol sentinel rejection, descriptor-only audio reads, and ancestor-symlink rejection. The complete test suite and live timer restart verification follow this record.

### Factory restart verification

- 72/72 unittest and 72/72 pytest passed after both fixes;
- compilation and diff checks passed;
- follow-up implementation commit `16c2344e2d6af4daee171fe5aa25d3390d9c5414` matched `origin/master` exactly;
- `pine-hollow-data-factory.timer` was enabled and started successfully;
- the enabling boundary triggered scheduled run `run_f74d6677628c45e5ada1f85e5d366c2a`, which completed with service result `success` and exit status 0;
- the one-shot service returned to inactive/dead after completion, while the timer remained active with its next ten-minute trigger scheduled.
