# Physical-Ecology Data Factory Research Record — 2026-07-16

## Research question

How should Pine Hollow connect field sensing, private evidence, human review, sustainable automation, NVIDIA acceleration, and public interpretation without creating vendor lock-in or false ecological certainty?

## Local evidence considered

- Durable field listener running frozen Perch with separate InsectNet and ChickenNet heads.
- 103 retained field recordings validated at implementation time.
- 52 private fixed-camera frames and existing Commons quality measurements.
- Live local Observatory payload generated every thirty minutes.
- RTX 4090 with 24,564 MiB total VRAM and more than 22 GiB free during initial inspection.
- Existing Pine Hollow Archive additive Commons schema and publication guards.
- Eight human-confirmed rooster clips showing useful ChickenNet ranking but an overly conservative deployed threshold.

## Findings

### Compute is not the present bottleneck

The archive is still small enough for SQLite and ordinary Python. The scarce material is reviewed local evidence, representative controls, exact spans, synchronization, intervention records, and seasonal repetition. GPU-first redesign would add operational weight without improving those constraints.

### NVIDIA is an acceleration layer

Adopt NVIDIA components only behind open evidence and model contracts.

- **CUDA / RTX 4090:** useful now for scheduled training and future batch embedding.
- **Triton:** appropriate only after multiple clients require shared versioned models.
- **RAPIDS cuDF:** appropriate after metadata volume or measured ETL time justifies GPU transfer.
- **DALI:** appropriate after decode/preprocessing is measured as a bottleneck.
- **DeepStream / Jetson Orin:** appropriate for future real-time visual edge work, not as a BirdNET-Pi replacement.
- **TAO:** primarily relevant to bounded vision adaptation, not the present Perch heads.
- **Cosmos Curator / Physical AI Data Factory:** relevant to future video and robotics datasets, not biological occurrence truth.
- **Isaac Sim / Omniverse:** useful after a concrete drone or robot task exists.
- **Jetson Thor:** unjustified for the current stationary station.

Synthetic data may cover rare robot or infrastructure hazards. It must not substitute for field evidence of organism presence.

### Evidence, assertions, and actions must remain separate

A model score, human review, temporal association, management decision, and ecological outcome have different authority. Separate records allow later correction and prevent a convenient prediction from becoming “truth” through database overwrite.

### Exact windows are necessary

Perch inputs are five seconds while field recordings are fifteen seconds. A review or training label must state the reviewed span. Recording-level labels can otherwise contaminate unrelated windows.

### Controls are necessary

Detector-selected positives cannot estimate missed events. Deterministic low-score controls and review across score bands are required for threshold calibration.

### Temporal context is not cause

A nearby camera frame or weather snapshot can help interpretation, but proximity alone cannot explain a call. Links therefore preserve signed time difference, method, tolerance, and `causal_claim: false`.

### Mutable web payloads are not archival evidence

The Observatory JSON is overwritten in place. Any payload used in research must be copied atomically and hashed before linking.

### Sustainable automation requires explicit energy classes

Continuous Pi capture is appropriate. GPU work should be scheduled, deferrable, bounded, and manually eligible until there is a demonstrated workload. An idle GPU is not unused capacity that must be filled.

## Adopted practices

- Additive SQLite migration.
- SHA-256 content identities.
- Read-only field source connection.
- Atomic snapshot copy.
- Deterministic idempotency keys.
- Append-only windows, links, transitions, and research records.
- Human correction by supersession.
- Code-level job allowlist.
- Worker leases and exponential retry backoff.
- Explicit resource and filesystem limits in systemd.
- Private-by-default events and media.
- Dated Markdown research/development/validation records alongside database records.

## Deferred practices

- Lowering ChickenNet threshold.
- Automatic dataset assembly.
- Triton deployment.
- GPU Perch serving.
- RAPIDS/DALI migration.
- DeepStream or Jetson purchase.
- Synthetic ecological training data.
- Kubernetes/OSMO orchestration.
- Website redesign or new public surface.

## Primary sources

Retrieved or checked on 2026-07-16.

### NVIDIA

- NVIDIA Physical AI Data Factory: https://github.com/NVIDIA/physical-ai-data-factory
- PAIDF Auto-Labeling: https://github.com/NVIDIA/paidf-auto-labeling
- DeepStream SDK: https://developer.nvidia.com/deepstream-sdk
- Triton Inference Server: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/
- NVIDIA Metropolis: https://developer.nvidia.com/metropolis
- NVIDIA TAO Toolkit: https://developer.nvidia.com/tao-toolkit
- NVIDIA Holoscan: https://developer.nvidia.com/holoscan-sdk
- NVIDIA Cosmos Curator: https://github.com/NVIDIA/Cosmos-Curator
- NVIDIA Cosmos Evaluator: https://github.com/NVIDIA/Cosmos-Evaluator
- NVIDIA Earth2Studio: https://github.com/NVIDIA/earth2studio
- NVIDIA RAPIDS: https://developer.nvidia.com/rapids
- NVIDIA DALI: https://developer.nvidia.com/dali
- NVIDIA JetPack: https://developer.nvidia.com/embedded/jetpack
- NVIDIA Jetson Thor overview: https://blogs.nvidia.com/blog/jetson-thor/

### Data and operations

- SQLite transactions: https://sqlite.org/lang_transaction.html
- SQLite PRAGMA reference: https://sqlite.org/pragma.html
- systemd service sandboxing: https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- systemd timers: https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html
- FAIR principles: https://www.go-fair.org/fair-principles/
- NEON data portal: https://www.neonscience.org/data-samples/data
- USDA Long-Term Agroecosystem Research Network: https://ltar.ars.usda.gov/

## Review rule

Future research records should state the question, evidence, sources, decision, rejected alternatives, uncertainty, implementation boundary, and validation result. A later record may supersede a decision, but the original record remains.

## Review-driven reliability findings

The implementation review reinforced four broader practices for small physical-ecology factories:

1. **Append-only must be enforced at the storage boundary.** API convention is insufficient when direct SQLite access is part of field operations.
2. **A lease without renewal is only a timeout.** Long handlers need an independent heartbeat and completion must still prove lease ownership and validity.
3. **Mutable environmental context needs an eligibility gate before preservation.** Copying every Observatory refresh would create volume without event relevance; timestamp proximity is an association rule, not causation.
4. **Unrecoverable loss is still evidence.** Incident hashes and timestamps belong in the research record, but must never be converted into synthetic media events.

These findings produced schema version 5 and did not change model thresholds, model interpretation, BirdNET separation, public surfaces, or GPU policy.

## Final evidence-boundary finding

Metadata is useful for fast change detection but cannot be the final identity of retained evidence. Filename, size, and modification time can all remain unchanged while bytes change. The scheduler therefore hashes current retained WAV content even though the importer will hash it again; the duplicate I/O is the cost of ensuring changed evidence cannot remain unscheduled.

Likewise, resolving a configured path before testing `is_symlink()` erases the fact that redirection occurred. Source acceptance now checks each path component before resolution. This is stricter than ordinary filesystem convenience because these paths establish provenance.

Finally, SQLite WAL files belong beside the resolved database target. Moving the canonical database into the private writable runtime tree allowed the repository itself to become read-only without disabling crash-safe WAL behavior. The repository-level symlink preserves operator ergonomics but is not itself the persistence boundary.
