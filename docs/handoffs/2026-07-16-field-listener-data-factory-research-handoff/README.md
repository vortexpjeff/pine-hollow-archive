# Pine Hollow Field Listener and Physical-Ecology Data Factory

## Two-day research and engineering handoff — 2026-07-15 through 2026-07-16

This packet is the canonical end-to-end account of the two-day build that connected:

1. provenance-locked Perch 2 research models;
2. a private, durable, review-only field listener;
3. the Pine Hollow Commons archive and physical-ecology data factory;
4. a weekly blinded human-validation desk;
5. unattended bounded-CPU operation.

It is written to preserve chronology and evidence boundaries. It does **not** replace the model cards, source repositories, private ledgers, raw audio, or study-specific protocols.

## The chronology correction

Three statements that appear contradictory are all true at different times:

- On the afternoon of July 15, the published **InsectNet Research 0.2.0** and **ChickenNet Research 0.1.0** artifacts were research candidates and were not deployed.
- Later that afternoon, expanded private successor candidates—InsectNet dev2 0.3.0 and ChickenNet dev2 0.2.0—were trained. Later still, only their broad heads were exported into strict private runtime bundles and integrated into an Athena listener for **review-candidate generation**, not ecological truth.
- On July 16, the downstream archive factory entered unattended production and a separate weekly blinded review protocol completed its first 24-item human audit.

The deployed listener therefore does **not** run the two public Hugging Face artifacts byte-for-byte. It runs later private broad-head exports with different artifact hashes and stricter operational thresholds. See [Chronology and state transitions](02-chronology-and-state-transitions.md) and [Model, dataset, and deployment dossier](03-model-dataset-and-deployment-dossier.md).

## Current handoff state

**Snapshot:** 2026-07-16 19:40:42 UTC / 15:40:42 EDT.

- Field listener: healthy, connected, both units active.
- Field ledger: 4,668 recordings, 28,008 score rows, 137 retained candidate events.
- Producer accounting: zero producer drops and zero sequence gaps at snapshot.
- Factory: schema 7; timer enabled and active; one-shot service inactive between runs.
- Commons archive: 226 events/media, 888 exact acoustic windows, 344 assertions.
- Factory jobs: 68 successful, zero non-success states.
- Weekly validation: active v4 packet completed, 24/24 reviews over 22 distinct source recordings plus two hidden repeats.
- GPU automation: disabled. The scheduled line is bounded CPU only.
- Publication: no raw audio, private context, credentials, coordinates, or local database content are included in this packet or repository.

These are dated observations, not permanent counts. Use the commands in [Operations and recovery](09-operations-and-recovery.md) for live state.

## Read this packet by question

| Question | Document |
|---|---|
| What did the two-day build actually accomplish? | [Executive synthesis](01-executive-synthesis.md) |
| In what order did research, deployment, production, and review occur? | [Chronology and state transitions](02-chronology-and-state-transitions.md) |
| Which models were public, private, trained, exported, or deployed? | [Model, dataset, and deployment dossier](03-model-dataset-and-deployment-dossier.md) |
| How does evidence move through the complete system? | [Architecture and truth contracts](04-architecture-and-truth-contracts.md) |
| How does the durable listener survive outages and replay? | [Field-listener engineering](05-field-listener-engineering.md) |
| What does schema 7 contain and which tables are authoritative? | [Factory schema and data dictionary](06-factory-schema-and-data-dictionary.md) |
| What was the weekly sampling method and what did the first audit find? | [Weekly validation methods and results](07-weekly-validation-methods-and-results.md) |
| What evidence supports release, and what remains unproven? | [Validation evidence and claim boundaries](08-validation-evidence-and-claim-boundaries.md) |
| How is the live system operated or safely stopped? | [Operations and recovery](09-operations-and-recovery.md) |
| What failed during development, and how was it corrected? | [Incidents and hardening record](10-incidents-and-hardening-record.md) |
| Where did every major claim come from? | [Reproducibility and evidence index](11-reproducibility-and-evidence-index.md) |
| What was committed, published, excluded, and left private? | [Git and release record](12-git-and-release-record.md) |
| What exact aggregate state was captured at handoff? | [`13-fixed-live-snapshot-sanitized.json`](13-fixed-live-snapshot-sanitized.json) |
| Are the files intact? | `SHA256SUMS.txt` |

## Evidence classes used in this packet

| Class | Meaning |
|---|---|
| **Observed live state** | Read directly from systemd, `fieldctl`, or SQLite at the timestamp above. |
| **Immutable artifact identity** | SHA-256, dataset hash, packet manifest hash, or Git commit. |
| **Automated verification** | Test, integrity, replay, sandbox, or checksum result with a recorded command/result. |
| **Human observation** | Append-only blinded review of an exact audio span. |
| **Derived description** | Calculation or summary from recorded rows; not a new observation. |
| **Interpretation** | Scientific meaning bounded by the design and limitations. |

No model score is promoted from “model assertion” to “human observation.” No temporal context link is promoted to causation. No candidate event is promoted to animal abundance, occupancy, or absence.

## Ownership boundaries

- BirdNET continues its own recording and bird-analysis circuit.
- The independent Pi sidecar owns producer sequence and durable upstream backlog.
- Athena capture owns a recording only after exact-byte validation, durable local commit, and matching ACK.
- The private listener owns frozen Perch inference and review-candidate generation.
- The Commons archive owns imported evidence, model assertions, context links, job history, and validation records.
- Human review owns interpretation of audible insect/chicken presence in the exact reviewed span.
- A future ecological study—not this pipeline—must own any inference about abundance, occupancy, seasonal change, welfare, or causality.

## Privacy and publication boundary

This packet is suitable for the public archive repository because it excludes:

- property coordinates and street address;
- LAN addresses, usernames, credentials, private keys, and tokens;
- raw/candidate audio and private context payloads;
- private row-level training manifests and embeddings;
- machine-specific config values;
- private evidence filenames and contents.

The local Hermes Audio mirror contains the same sanitized documents. Existing earlier packets remain intact as dated records.