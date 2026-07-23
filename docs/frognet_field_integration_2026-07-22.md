# FrogNet archive and weekly-validation integration — 2026-07-22

## Scope

FrogNet is integrated into the private Commons Lab evidence and human-validation path as a third independent Perch head. It predicts broad audible `frog_present`; it is not a species classifier and does not automatically create ecological truth or training labels.

## Runtime and ingestion

The listener processes one 15-second recording as three five-second windows. Each window receives one frozen Perch 2 embedding followed by independent InsectNet, ChickenNet, and FrogNet scores. The factory verifies every configured bundle directory and recomputes its bundle ID before importing model rows.

FrogNet's deployed identity is:

- bundle: `frognet-dev4-field-probe`;
- bundle ID: `db54359b42526010a2e7782837d2ff8a5e7d98beeebba9214211a2ee83572fa8`;
- output: `frog_present`;
- threshold: `0.95`.

The factory opens the evidence ledger read-only. SQLite readers require write access only to the `events.sqlite3-shm` coordination sidecar while the database and WAL remain read-only; the systemd sandbox encodes that narrow exception.

## Schema 8

Commons schema 8 adds `frog_presence` to append-only validation reviews. A completed human review may therefore emit three separate training-ineligible assertions:

- `insect_present`;
- `chicken_vocalization_present`;
- `frog_present`.

The validation desk collects and reports each judgment independently. Missing or uncertain labels are never silently converted into negatives.

## Active weekly protocol

Protocol `weekly_blinded_v5` supersedes v4 for new review writes. Historical v4 packets remain immutable evidence.

The v5 target is 32 items:

| Lane | Count | Allocation |
|---|---:|---|
| Model positive | 12 | Four per class |
| Boundary | 12 | Two above and two below threshold per class |
| Random control | 6 | Score-independent, selected first |
| Hidden repeat | 2 | Delayed duplicates for agreement |

Thirty non-repeat items must have distinct frozen parent-recording identities. Every selected parent must carry aligned windows from all three deployed heads. Reports include per-class positive/boundary/control findings and independent hidden-repeat agreement for insect, chicken, and frog judgments.

Packet creation remains gated on a feasible balanced frame. It will not create an all-frog packet when no current three-head InsectNet or ChickenNet positives are available.

## Verification snapshot

After deployment, the factory successfully imported three-head recordings with nine window-score rows and three model assertions per recording. A readback snapshot contained 92 FrogNet-tagged recordings, 276 FrogNet windows, 270 threshold crossings, and 92 FrogNet model assertions; later successful cycles continued importing new rows. The archive returned `quick_check=ok`, with no queued or failed factory jobs at the closure snapshot.

The archive retains a separate legacy condition: 32 `label_events` foreign-key violations predate Commons schema 4. Commons/FrogNet migrations did not create them, and they must not be rewritten without a separate provenance audit.

## Audit cadence

- Review one balanced packet weekly for the first four to six weeks when the readiness gate passes.
- Move to every two weeks after stable repeat agreement and confound behavior.
- Review immediately after model, threshold, microphone, service, or substantial environmental changes.
- Inspect cumulative score bands, confounders, storm behavior, and burden monthly.

Validation judgments remain evidence for audit. Promotion into training requires a separate frozen dataset manifest and explicit authority decision.

## Related records

- Active desk manual: [`weekly_field_validation_desk.md`](weekly_field_validation_desk.md)
- Factory operations: [`physical_ecology_data_factory_operations.md`](physical_ecology_data_factory_operations.md)
- Runtime deployment details are maintained in the private field-operations repository.
- Safe model release: <https://github.com/vortexpjeff/insectnet/releases/tag/frognet-field-probe-v0.1.0>
