# 7. Weekly validation methods and first-packet results

## Study purpose

The weekly desk asks:

> Under current local recording conditions, when the deployed broad heads produce selected score patterns, what can one human reviewer hear in the exact five-second spans, and how burdensome/repeatable is the review process?

It does not estimate animal abundance, occupancy, absence, population trend, or complete model recall.

## Protocol identity

| Field | Value |
|---|---|
| protocol | `weekly_blinded_v4` |
| local week start | 2026-07-13 |
| timezone | `America/New_York` |
| packet ID | `vpk_31d5158ef95e1fe35caff3e4` |
| manifest SHA-256 | `bf7da3f8cad4d98fd7a76cc87cf4511e8428ff6b8b3bf127cb8beffe702cbd5e` |
| packet items | 24 |
| unique source recordings | 22 |
| hidden repeats | 2 |
| review state | completed 24/24 |

Earlier v1–v3 manifests remain immutable and unreviewed. They are not included in the first-packet analysis.

## Sampling frame

Eligible material comes from archived field-listener recordings with aligned exact windows for both deployed broad heads.

The readiness gate requires:

- at least 22 eligible parent recordings;
- at least six above-threshold parent recordings for each class;
- at least two below-threshold parent recordings for each class;
- a successful global allocation under one parent-uniqueness constraint.

Marginal counts alone are not enough. The same planner used to build a packet must prove that controls, all boundary cells, positive lanes, and repeats can coexist without unintended parent reuse.

At the fixed final snapshot, the archived frame contained 148 unique eligible parent recordings and remained ready for the active protocol.

## Packet composition

| Lane | Count | Selection purpose |
|---|---:|---|
| model positive | 8 | four insect and four chicken threshold-crossers across positive range |
| boundary | 8 | two just above and two just below each deployed threshold |
| random control | 6 | score-independent parent selection |
| hidden repeat | 2 | delayed duplicates of earlier items |

The 22 non-repeat items have distinct frozen `source_recording_id` values.

## Control construction

Controls are selected before score-driven lanes. They are the first six eligible parent identities under a week-specific deterministic hash order.

Control selection does not use:

- either model score;
- threshold crossing;
- prior packet inclusion;
- date/hour weighting;
- candidate state.

Every control is still labeled for both insect and chicken presence. A target sound in a control is not automatically a model miss; the model score and exact class context must be inspected after review.

## Boundary construction

For each broad head:

- two parent recordings just above the deployed threshold;
- two just below;
- no reuse of another non-repeat packet parent.

Boundary sampling describes local behavior near the operational cut. It is not a regression-discontinuity study and does not validate the threshold as optimal.

## Positive construction

For each broad head, four above-threshold parents are spread deterministically across the positive score range after controls and boundary cells reserve their parent identities.

Positive-lane empirical rate describes reviewed usefulness among those selected items. It is not design-based precision for all future candidates.

## Hidden repeats

Two earlier items are repeated later under independent item/review identities. Before judgment the desk does not reveal repeat status.

Repeats contribute only to within-reviewer agreement, not to performance denominators. Cumulative performance uses at most one reviewed item per frozen source recording.

## Blinding

Before review, the desk shows:

- packet progress;
- exact five-second audio;
- optional complete 15-second parent context;
- insect/chicken choices;
- quality, confounders, reviewer, and notes.

It hides:

- lane;
- model and bundle;
- score;
- threshold;
- crossing state;
- repeat identity.

The reveal appears only after the append-only judgment is saved.

## Human label contract

### Insect and chicken presence

- `present`: target sound audibly present in exact span;
- `absent`: target sound not audible in exact span;
- `uncertain`: defensible yes/no judgment not possible.

### Signal quality

One of clear, distant, overlapping, clipped, noisy, or inaudible.

### Confounders

Optional bird overlap, wind, rain, mechanical sound, human activity, clipping, or unknown.

The reviewer is instructed to use `uncertain` rather than force a label.

## Transaction and provenance

One submission uses one `BEGIN IMMEDIATE` transaction to:

1. revalidate active protocol, item, packet, media, span, and model context;
2. append insect human assertion;
3. append chicken human assertion;
4. append validation review;
5. complete the item;
6. advance/complete the packet.

Any failure rolls back all writes. Human assertions are exact-span and `training_eligible=false`.

## First-packet results

### Primary lane table

Percentages below use decided reviews only. Wilson intervals are descriptive binomial intervals conditional on this realized packet; they are not design-based population confidence intervals.

#### Insect audible presence

| Lane | Reviewed | Present | Absent | Uncertain | Present among decided | Descriptive Wilson 95% |
|---|---:|---:|---:|---:|---:|---:|
| model positive | 4 | 4 | 0 | 0 | 100% | 51.0–100% |
| boundary above | 2 | 2 | 0 | 0 | 100% | 34.2–100% |
| boundary below | 2 | 2 | 0 | 0 | 100% | 34.2–100% |
| random control | 6 | 4 | 2 | 0 | 66.7% | 30.0–90.3% |

#### Chicken vocalization audible presence

| Lane | Reviewed | Present | Absent | Uncertain | Present among decided | Descriptive Wilson 95% |
|---|---:|---:|---:|---:|---:|---:|
| model positive | 4 | 2 | 1 | 1 | 66.7% | 20.8–93.9% |
| boundary above | 2 | 0 | 2 | 0 | 0% | 0–65.8% |
| boundary below | 2 | 1 | 1 | 0 | 50% | 9.5–90.5% |
| random control | 6 | 1 | 5 | 0 | 16.7% | 3.0–56.4% |

### Hidden-repeat agreement

| Dimension | Paired items | Exact agreement |
|---|---:|---:|
| insect label | 2 | 100% |
| chicken label | 2 | 100% |
| signal quality | 2 | 100% |

Two agreeing pairs show that the interface can preserve a repeated decision in this session. They are far too few to estimate stable reviewer reliability.

### Review burden

| Measure | Value |
|---|---:|
| timed reviews | 24 |
| total | 625.82 seconds / 10.43 minutes |
| median | 23.91 seconds per item |

This supports the practical 24-item weekly burden for one completed session. It does not include setup, interruption, report reading, or future difficult clips.

### Uncertainty

There were 48 target labels across 24 items. One chicken label was uncertain:

- uncertain labels: 1/48;
- uncertainty rate: 2.08%.

This is a protocol-use observation, not a population uncertainty estimate.

### Coverage

The 22 unique parent recordings covered:

- local dates: July 15 and July 16;
- local hours: 12, 13, 14, 20, 22, and 23.

Coverage is sparse and opportunistic. It does not represent every hour, weather state, soundscape, or season.

## Score-band description

Every reviewed parent has both broad-head score contexts, so score-band summaries include the full analyzed set, not only the lane targeting that class.

### Insect

| Score band | Reviewed | Present | Absent | Present among decided |
|---|---:|---:|---:|---:|
| `<0.5` | 7 | 0 | 7 | 0% |
| `0.5–0.9` | 1 | 0 | 1 | 0% |
| `0.9–0.99` | 2 | 1 | 1 | 50% |
| `0.99–0.999` | 1 | 1 | 0 | 100% |
| `0.999–0.9999` | 8 | 8 | 0 | 100% |
| `>=0.9999` | 3 | 3 | 0 | 100% |

In this small packet, insect audibility rose sharply with score. Because the sample is deterministic, selected, and only 22 parents, this is an initial local pattern—not calibration.

### Chicken

| Score band | Reviewed | Present | Absent | Uncertain | Present among decided |
|---|---:|---:|---:|---:|---:|
| `<0.5` | 14 | 1 | 13 | 0 | 7.1% |
| `0.999–0.9999` | 1 | 1 | 0 | 0 | 100% |
| `>=0.9999` | 7 | 2 | 4 | 1 | 33.3% |

No reviewed parents occupied the middle chicken score bands in this realized packet. The strict chicken score showed substantial audible false-candidate behavior in this small sample and deserves continued weekly review.

## What the first packet supports

It supports these bounded statements:

- the desk completed an entire v4 packet without partial transactions;
- one reviewer could finish 24 items in about ten minutes of measured review time;
- hidden repeats agreed in both pairs;
- all four insect positive-lane items contained audible insects;
- audible insects were also common in controls and below-threshold boundary items, showing a soundscape with substantial target presence;
- chicken model-positive items were mixed, including absent and uncertain judgments;
- above-threshold chicken boundary items were both judged absent;
- at least one chicken vocalization was audible in a random control;
- weekly local review is scientifically useful and should continue before threshold changes.

## What it does not support

It does not support:

- insect or chicken recall;
- general candidate precision;
- probability calibration;
- threshold optimization;
- abundance, density, occupancy, or absence;
- seasonal or site generalization;
- multi-reviewer reliability;
- causal weather/visual effects;
- automatic training promotion.

## Next defensible accumulation plan

For the first four weeks:

1. keep protocol v4 and thresholds frozen;
2. collect one packet per week when ready;
3. keep random controls score-independent;
4. preserve `uncertain` and confounders;
5. promote no training examples automatically;
6. compare cumulative parent-deduplicated lane and score-band summaries;
7. inspect whether chicken strict-threshold failures repeat by confounder/time;
8. define a separate completely reviewed time-block study before claiming recall.

Four weeks still will not establish seasonal generalization.