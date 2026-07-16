# Weekly Field Validation Desk

## Purpose

The Field Validation Desk is the human-verification layer for Pine Hollow's private physical ecology data factory.

It answers a narrower question than the factory itself:

> Given exact field recordings and frozen diagnostic model outputs, how often do the proposed insect and chicken signals correspond to what a human can actually hear under current Pine Hollow conditions?

It does not replace evidence integrity checks. It does not retrain either model. It does not turn model scores into ecological truth.

## Verification layers

### Pipeline verification

Automated checks establish that:

- source media bytes match archived SHA-256 identities;
- exact sample spans remain attached to the correct parent recording;
- bundle, class, threshold, score semantics, and preprocessing identity remain frozen;
- jobs are deterministic and replay-safe;
- validation manifests cannot be edited after creation;
- reviews and sentinel checks are append-only;
- the Commons foreign-key and SQLite integrity gates remain clean.

### Model field verification

The weekly packet estimates:

- empirical positive rate among model-positive recordings;
- behavior near both diagnostic thresholds;
- target-positive findings in score-independent random controls;
- empirical human-positive rate across score bands;
- within-reviewer exact agreement on hidden repeats;
- review uncertainty, coverage, and burden.

Cumulative performance summaries use at most one reviewed item per frozen `source_recording_id`, even when a later week reuses the recording. Hidden repeats remain separate and are used only for agreement reporting.

### Training-data verification

Validation judgments are explicitly stored with `training_eligible=false`.

Promotion into any future training corpus requires a separate frozen dataset manifest, parent-day grouping, review authority policy, and train/validation/test split. No weekly review automatically enters training.

## Weekly protocol

Protocol identity: `weekly_blinded_v4`

Routine navigation, direct review pages, CLI review writes, and core append calls accept only the active protocol. Historical packets remain queryable evidence but cannot receive new judgments after a protocol change.

Local week boundary: Monday in `America/New_York`

Sampling unit: unique parent recording, except for two intentional hidden repeats.

Review unit: one exact imported five-second span.

Packet size: 24 items.

| Lane | Count | Purpose |
|---|---:|---|
| Model positive | 8 | Four insect and four chicken threshold-crossers, spread across the positive score range |
| Boundary | 8 | For each model, two just above and two just below the diagnostic threshold |
| Random control | 6 | Score-independent sample selected first from the full eligible frame |
| Hidden repeat | 2 | Delayed duplicate judgments for within-reviewer consistency |

The six controls are selected before any score-driven lane and ignore prior packet membership. They are the first six parent identities under the week-specific deterministic hash order: no score, history, date, or hour weighting enters control inclusion. The 22 non-repeat items use distinct frozen `source_recording_id` values. The repeat items point to earlier source items but carry independent review records and assertion identities.

## Deterministic sampling

Each packet freezes:

- protocol version;
- local week start;
- timezone;
- deterministic sampling seed;
- target count;
- selected event, media, and frozen source-recording IDs;
- exact start/end samples and sample rate;
- lane and primary class where applicable;
- both model contexts;
- source media SHA-256;
- selection method;
- hidden-repeat lineage;
- explicit `training_eligible=false` and `causal_claim=false` markers.

The canonical packet manifest receives its own SHA-256. Packet/item deletion is blocked, manifest fields are immutable, replay verifies every frozen row against the manifest, and sentinel definitions/checks are append-only.

Replaying the same protocol/week returns the existing packet. It does not resample.

Later score-driven lanes prefer parent recordings not used by earlier packets. Controls remain independent of history. When fresh score-lane recordings are insufficient, older material may be considered only after unused material is exhausted by the deterministic selection order.

## Readiness gate

A packet is not enqueued until the archived frame contains:

- at least 22 parent recordings with aligned windows from both diagnostic heads;
- at least six above-threshold parent recordings per class;
- at least two below-threshold parent recordings per class.

These marginal counts are only diagnostics. Readiness also runs the exact global allocation planner—controls, all boundary cells, and both positive lanes under one parent-uniqueness set—and reports the same concrete failure reason packet generation would return.

Inspect readiness:

```bash
cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
python3 scripts/run_data_factory.py validation-status
```

## Open the desk

From Windows, double-click:

```text
C:\Users\Jeffrey\Desktop\pine-hollow-archive\launch_validation_desk.bat
```

Or from WSL:

```bash
cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
./launch_validation_desk.sh
```

Direct command:

```bash
python3 scripts/run_validation_desk.py --host 127.0.0.1 --port 8765
```

Open:

```text
http://localhost:8765
```

The desk is intentionally not a daemon. Start it when reviewing and stop it with `Ctrl+C` afterward.

## Private browser boundary

The desk:

- binds only to `127.0.0.1`, `localhost`, or `::1`;
- rejects non-loopback Host headers;
- uses a fresh random process token for review forms and audio routes;
- accepts review writes only by POST;
- caps form bodies at 64 KiB;
- uses parameterized SQLite queries;
- escapes database and user text in HTML;
- serves no external JavaScript, fonts, analytics, or assets;
- sends no-store, content-type, frame, and content-security headers;
- verifies actual audio bytes against both the Commons media hash and frozen packet hash before serving;
- rejects symlinked or unavailable audio.

The desk never publishes or uploads audio.

## Blinded review sequence

Before a judgment is saved, the review page shows:

- packet progress;
- exact five-second WAV span;
- optional full 15-second recording context;
- insect presence choices;
- chicken vocalization choices;
- signal quality choices;
- confounder tags;
- reviewer authority and notes.

It does not show:

- sampling lane;
- model name;
- score;
- threshold;
- threshold crossing state;
- hidden-repeat status.

After the append-only judgment is saved, the reveal page shows the frozen sampling and model context.

## Label contract

### Insect presence

- `present`: an insect sound is audibly present in the exact five-second span;
- `absent`: no insect sound is audible in that span;
- `uncertain`: the reviewer cannot make a defensible yes/no judgment.

### Chicken presence

- `present`: a chicken vocalization is audibly present in the exact span;
- `absent`: no chicken vocalization is audible in that span;
- `uncertain`: the reviewer cannot make a defensible yes/no judgment.

### Signal quality

Choose one primary condition:

- clear;
- distant;
- overlapping;
- clipped;
- noisy;
- inaudible.

### Confounders

Optional tags include:

- bird overlap;
- wind;
- rain;
- mechanical sound;
- human activity;
- clipping;
- unknown.

Use `uncertain` rather than forcing a target label when the sound cannot be distinguished.

## Exact span versus full context

The first player is the exact five-second model span. That is the unit being judged.

Model span indexes use the bundle's 32 kHz inference timebase. Retained field WAVs currently preserve the capture device's native 48 kHz stream. The desk converts the model start/end samples to elapsed time, maps those boundaries to the nearest native WAV frames, and serves the native-rate PCM segment without resampling. Thus a five-second 32 kHz model span is served as 240,000 frames at 48 kHz while preserving the frozen model-sample lineage.

The second player is the complete retained recording. It can help identify call structure, overlap, or background conditions, but the resulting assertion remains bounded to the five-second model span.

A five-second validation judgment does not mark the entire parent recording as completely reviewed.

## Append-only review transaction

One desk submission executes one SQLite `BEGIN IMMEDIATE` transaction that:

1. validates item, packet, media, span, and frozen model context;
2. appends an insect human assertion;
3. appends a chicken human assertion;
4. appends the validation review row;
5. marks only the validation item complete;
6. advances packet progress;
7. completes the packet only when all 24 items are reviewed.

If either assertion or any later write fails, the entire review rolls back.

Validation assertions carry:

- protocol, packet, item, review, and lane identity;
- exact bundle/class/span lineage;
- human reviewer authority;
- certainty;
- explicit `training_eligible=false`.

They do not complete or dismiss the older score-stratified calibration queue.

## CLI recovery path

Create or replay the current packet:

```bash
python3 scripts/run_data_factory.py validation-packet
```

Create/replay a specified local week:

```bash
python3 scripts/run_data_factory.py validation-packet --week-start 2026-07-13
```

Status:

```bash
python3 scripts/run_data_factory.py validation-status
```

Append a review without the browser:

```bash
python3 scripts/run_data_factory.py validation-review \
  --item-id vit_EXACT_ID \
  --reviewer human:field-reviewer \
  --insect-presence present \
  --chicken-presence absent \
  --signal-quality clear \
  --confounder bird_overlap \
  --notes "Audible insect pulse in exact span."
```

The CLI recovery path is not blind if the operator has already inspected database metadata. Use the browser for routine scientific review.

## Scientific report

Packet report:

```bash
python3 scripts/run_data_factory.py validation-report --packet-id vpk_EXACT_ID
```

Cumulative report:

```bash
python3 scripts/run_data_factory.py validation-report
```

The report includes:

- reviewed/decided/present/absent/uncertain counts;
- empirical positive rate;
- Wilson 95% interval among decided reviews, labeled as descriptive for the realized packet rather than a design-based population interval;
- positive-lane results per class;
- boundary-above and boundary-below results per class;
- random-control positive rate per class;
- empirical review results by score band;
- hidden-repeat exact agreement;
- unique parent recordings and local date/hour coverage;
- uncertain-label rate;
- total and median timed review burden.

## Interpretation boundaries

The report does not establish:

- recall from candidate/boundary review alone;
- calibrated probabilities;
- abundance;
- occupancy;
- absence outside the exact reviewed span;
- seasonal or cross-site generalization;
- causal environmental relationships.

A defensible recall estimate requires independent complete review of bounded microphone-days or time blocks.

Scores remain uncalibrated case-control ranking scores. A displayed score of `0.9999` is not a 99.99% probability.

## Sentinel foundation

A completed item with decided insect and chicken labels can be deliberately promoted:

```bash
python3 scripts/run_data_factory.py validation-promote-sentinel \
  --item-id vit_EXACT_ID \
  --promoted-by human:field-reviewer
```

Uncertain items cannot become sentinels.

Check active sentinels:

```bash
python3 scripts/run_data_factory.py validation-check-sentinels
```

Current sentinel checks verify:

- actual media SHA-256;
- Commons media SHA-256;
- exact event/media/span/sample-rate identity;
- both bundle/class identities;
- frozen scores, thresholds, semantics, and preprocessing recipes.

Each check appends an immutable pass/drift/missing row.

### Sentinel limit

The current archive-side sentinel check does not perform fresh model inference. `fresh_audio_rescore_performed=false` is recorded explicitly.

True runtime drift testing requires an approved bridge to the field listener's exact Perch/head inference environment. That is a separate future integration, not something the archive pretends to have done.

## Weekly automation

The existing ten-minute bounded CPU worker checks whether a packet exists for the current local week.

If none exists and the readiness gate passes, it enqueues one allowlisted job:

```text
weekly_validation_packet / scheduled_cpu
```

The deterministic idempotency key includes protocol and local week.

If active sentinels exist, one weekly check is keyed by local week and active sentinel-set SHA-256:

```text
validation_sentinel_check / scheduled_cpu
```

No validation job uses the GPU. No packet generation changes model thresholds or labels.

## Schema tables

### `commons_validation_packets`

One immutable manifest per protocol/week. Only progress state and completion time can change.

### `commons_validation_items`

Frozen item selection, exact span, lane, primary class, model context, and repeat lineage. Only item state/completion time can change.

### `commons_validation_reviews`

Append-only human judgments. One review per packet item; hidden repeats are separate items.

### `commons_validation_sentinels`

Deliberately promoted decided examples with frozen media/context and human labels.

### `commons_validation_sentinel_checks`

Append-only pass/drift/missing observations.

## Routine weekly workflow

1. Let the factory create the packet automatically.
2. Run `validation-status` or open the desk.
3. Review the 24 items without inspecting model details elsewhere.
4. Use `uncertain` when evidence is ambiguous.
5. Read the packet report after completion.
6. Do not change thresholds from one small packet.
7. After several weeks, inspect cumulative intervals, control findings, confounders, and coverage.
8. Promote only clear, stable examples into the sentinel foundation.

## First-month interpretation

### Weeks 1–3

Collect packets without threshold changes or retraining. The primary outputs are:

- review habit and burden;
- confounder inventory;
- obvious positive-lane failures;
- random-control target findings;
- hidden-repeat consistency;
- date/hour coverage.

### Week 4

Use the cumulative report to ask:

- Are model-positive recordings audibly useful?
- Does the near-threshold sample differ across the boundary?
- Are random controls finding obvious misses?
- Are uncertainties concentrated in rain, overlap, distance, or clipping?
- Is the review protocol repeatable enough to trust?

Do not interpret four weeks as seasonal generalization.

## Failure and recovery

### No packet appears

```bash
python3 scripts/run_data_factory.py validation-status
```

Inspect the readiness counts. Do not lower protocol requirements merely to force a packet.

### Desk will not start

```bash
python3 scripts/run_validation_desk.py --host 127.0.0.1 --port 8765
```

If the port is occupied, choose another loopback port.

### Audio is rejected

The desk refuses media when:

- the path is missing;
- the path is a symlink;
- actual bytes do not match Commons SHA-256;
- actual bytes do not match the packet's frozen media SHA-256;
- the imported sample rate or span is invalid.

Do not bypass this guard. Investigate evidence drift.

### Review submission fails

No partial review should remain. Confirm:

```bash
python3 scripts/run_data_factory.py validation-status
sqlite3 archive.db "PRAGMA integrity_check; PRAGMA foreign_key_check;"
```

### Sentinel reports drift

Do not overwrite expected values. Preserve the drift row, compare current bytes and artifacts with the frozen record, and determine whether the cause is media corruption, database inconsistency, or an intentional artifact replacement.

## Energy and privacy contract

- packet generation: scheduled CPU;
- sentinel byte checks: scheduled CPU;
- browser review: manual local CPU;
- GPU automation: false;
- media: private;
- packet manifests: private;
- reviews: private;
- coordinates: not part of the desk;
- publication: none.
