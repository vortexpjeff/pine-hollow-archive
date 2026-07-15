# InsectNet management audit

**Date:** 2026-07-14
**Mode:** Local/public inventory plus explicitly approved read-only BirdNET-Pi inspection
**Initial audit boundary:** The inventory phase made no BirdNET-Pi, GitHub, or Hugging Face changes. A later user-approved reconciliation is recorded at the end of this document.

## Purpose

Establish actual InsectNet source, artifact, deployment, and documentation truth across:

1. the BirdNET-Pi deployment directory;
2. `vortexpjeff/insectnet` on GitHub;
3. `TheVortexProject/insectnet` on Hugging Face;
4. the Pine Hollow archive workspace;
5. surviving desktop artifacts.

The machine-readable companion is:

```text
docs/audit/insectnet_artifact_registry_2026-07-14.json
```

It intentionally excludes exact coordinates, addresses, credentials, tokens, raw audio, and private source-media paths.

## Executive finding

InsectNet is not currently managed as one versioned system.

- GitHub and Hugging Face preserve the same six-class v0.1 model bytes.
- BirdNET-Pi's active classifier file is also those v0.1 bytes, but no InsectNet process is currently running.
- BirdNET-Pi preserves the only known copies of the best-documented 0.2 artifacts.
- The Pi sidecar source is newer than the GitHub source and is not represented in Git.
- Historical archive documents point at release and training paths that no longer exist.
- A June 6 desktop candidate survives, but its embedded/report evidence does not support promotion.
- The public docs contain privacy, security, licensing, provenance, performance, and operational errors.

The Pi therefore holds important recovery evidence, but it must not become the canonical source repository. Git should become source truth; Hugging Face should be a generated release mirror; the Pi should remain a deployment target with a declared manifest and rollback artifact.

## Current runtime truth

Read-only inspection at 2026-07-14 19:39 EDT found:

- hostname: `BirdNetPi`;
- BirdNET core services: all four active;
- BirdNET's own inotify watcher: one expected process;
- InsectNet sidecar process: absent;
- InsectNet systemd unit: absent;
- InsectNet crontab: absent;
- sidecar shutdown: clean;
- last InsectNet ledger record: 2026-06-17 18:05 EDT;
- last session: 56,474 WAVs processed, 17,130 detections logged as kept, 39,344 discarded, zero errors;
- retained review audio: eight MP3 files, all in `uncertain`;
- InsectNet ledger: 17,129 JSONL lines;
- free root storage: 8.8 GiB;
- BirdNET authoritative detection ledger remains present and current.

No remote file, service, process, crontab, or configuration was changed.

## Artifact identity

### v0.1.0 reference

```text
SHA-256: 5e6ecfc68d78a2cf2e9e9e47da5cb58d696e8de354fd620cfcccc5db9da48702
Bytes:   474,892
Classes: background, bee, cicada_drone, cricket_katydid, frog, grasshopper
```

Identical bytes are present at:

- GitHub tag `v0.1.0` and `main`;
- Hugging Face `main`;
- archive workspace `models/insectnetpi_sidecar_v0.1.0_may29.joblib`;
- BirdNET-Pi's active classifier path.

The artifact embeds only `scaler`, `classifier`, and `classes`. It does not embed version, per-class thresholds, training snapshot, BirdNET backbone hash, release status, or deployment status.

### Best-documented 0.2 artifact

```text
SHA-256: 6627cb41861285ca8c8111941b1de029671415398c7e1d0fc0adab0ec639c0dc
Bytes:   421,724
Variant: insectnet_0.2_final_curated_local_anchor
Classes: background, cicada_drone, cricket_katydid, frog, grasshopper
Status:  final_not_deployed
```

It survives only as `classifier_0.2.bak` on BirdNET-Pi. The original workstation release package and manifests named in its embedded notes are absent.

Treat this as the strongest recoverable 0.2 release candidate, not as evidence of a successful deployment.

### June 5 bird-negative candidate

```text
SHA-256: 175b01b0bc81534f8c82e297d499ab33e8a115b6ec52ad50cb3e2a63bd0049e8
Bytes:   474,958
Policy:  v01_restored_bg_plus_25_birdneg
Status:  candidate_only_not_deployed
```

Two identical copies survive on the Pi. The embedded class-specific thresholds and feature contract are useful. The named workstation report and training manifest are missing. Its continuous field review load was never measured.

### Historical pre-rollback artifact

```text
SHA-256: 5beb3178aef6b48d4b922a698faf76a370e06c5d1defb43df29b58eda420e58e
Variant: final5_grass
```

Preserve as historical evidence. Do not promote without a separate evaluation.

### June 6 desktop experiment

```text
SHA-256: 42236d3766b73e44bbc0204b6283b2fb36368804a2963b1e27a09c71b97ed970
Macro F1:    0.559
Weighted F1: 0.647
Bird negatives embedded in report: 0
```

The report conflicts with the companion narrative that bird negatives were the branch's main improvement. Its cicada threshold is 0.15, several class precisions are weak, and no durable training manifest was found. Preserve as an experiment; do not deploy or call it final.

## Source-code lineage

GitHub `v0.1.0`:

```text
src/insectnet/capture.py  18,435 bytes  SHA-256 f3d1896a...
src/insectnet/birdnet.py   1,897 bytes  SHA-256 501ddeb9...
src/insectnet/train.py     5,418 bytes  SHA-256 63fd3209...
scripts/deploy.sh          1,541 bytes  SHA-256 d7484379...
```

BirdNET-Pi:

```text
insectnet_capture.py      23,476 bytes  SHA-256 182833a0...
```

The Pi source is newer and implements a different evidence contract: five BirdNET-aligned windows per 15-second source and BirdNET-style six-second MP3 review clips. It is not represented in Git. The audit did not copy the Pi source because this phase was explicitly read-only with no transfer.

## Public repository findings

### Release management

- GitHub has tag `v0.1.0` but no GitHub Release.
- Hugging Face has one branch, no tags, and one initial model upload.
- There is no shared release manifest linking Git commit, Hub commit, model SHA-256, BirdNET backbone SHA-256, source version, metrics, thresholds, or deployment state.
- The archive Git remote currently returns `Repository not found`; public InsectNet docs link to that unavailable repository.

### Code and test findings

The public GitHub source compiles, but there are zero tests.

High-priority problems before calling it deployable:

1. The runtime ignores embedded per-class thresholds.
2. The runtime calls itself multi-label but chooses and stores only one top class.
3. GitHub captures only the center 3-second window; the newer Pi source evaluates all five aligned windows.
4. Capture names use second-level timestamps and can collide.
5. Deployment overwrites source/model files without backup, checksum verification, rollback, compile check, or service-health gate.
6. Capture starts an unmanaged detached process rather than a bounded service.
7. Pull mode writes a hardcoded password helper.
8. Training cross-validation fits scaling before splitting and does not group windows by parent source.
9. Missing logit files are silently skipped.
10. The training CLI does not enforce 6,522-dimensional finite feature vectors or write a reproducible training snapshot.
11. README and scripts refer to nonexistent `models/6class.joblib` while the repository contains `models/classifier.joblib`.
12. Package metadata declares CC BY-NC-SA text while also claiming an MIT classifier.

### Public documentation/privacy findings

Public GitHub and Hugging Face documentation currently includes information that should be removed or generalized:

- exact site coordinates;
- Pi address and default credentials;
- claims of production readiness not supported by current runtime state;
- instructions that overwrite deployed files directly;
- stale links and path assumptions;
- local/private validation details that should be projected as generalized methods and limitations.

### License/provenance findings

The current blanket table is inaccurate:

- InsectSet459's current dataset card states CC BY 4.0 / CC0 source material, not CC BY-NC-SA 4.0.
- ESC-50 states CC BY-NC 3.0, not CC BY-NC 4.0.
- iNaturalist media licenses vary per observation; a blanket dataset license is insufficient.
- Code licensing and trained-model licensing should be stated separately.
- A release must preserve per-source/per-record license provenance rather than infer one license from dataset names.

This is a provenance correction, not legal advice.

## Recommended managed structure

Use `vortexpjeff/insectnet` as the canonical source and release repository:

```text
insectnet/
├── src/insectnet/
├── tests/
├── deploy/systemd/
├── models/
│   └── manifests/
├── releases/
│   ├── v0.1.0/
│   └── v0.2.0-rc1/
├── docs/
│   ├── architecture.md
│   ├── operations.md
│   ├── privacy.md
│   ├── data-provenance.md
│   └── model-governance.md
└── scripts/
    ├── audit_release.py
    ├── build_release.py
    └── deploy_verified.py
```

Surface roles:

- **GitHub:** source truth, tests, immutable manifests, tagged releases, operational docs.
- **Hugging Face:** generated model release mirror and model card; no independent hand-maintained truth.
- **BirdNET-Pi:** deployment target only; every active file must match a released SHA-256 and declared source version.
- **Pine Hollow archive:** private evidence, raw audio, review records, training snapshots, and intervention/outcome history.

## Proposed release policy

Every model release should carry:

- immutable artifact SHA-256 and byte size;
- release ID and status (`experimental`, `candidate`, `field_review`, `released`, `retired`);
- class order and independent per-class thresholds;
- feature-space contract and BirdNET backbone SHA-256;
- source/window manifest digest;
- grouped train/evaluation split policy;
- metrics with explicit evaluation-set scope;
- known false positives and review workload;
- source/data license manifest;
- code commit and sidecar source SHA-256;
- intended deployment target;
- deployment and rollback procedure;
- privacy-reviewed public model card.

Models issue assertions. Captures remain review candidates until a human confirms them.

## Initial gated reconciliation plan (superseded by final reconciliation)

No step below has been executed yet.

1. Recover immutable copies of the Pi-only sidecar and model variants into a private local provenance vault, without activating anything.
2. Create a clean local clone of `vortexpjeff/insectnet` for managed work.
3. Add tests around artifact loading, dimensions, class order, per-class thresholds, multi-window inference, no-overwrite capture, single-instance operation, ledger append, and failure cleanup.
4. Port the newer Pi evidence contract into tested source while removing credentials and private defaults.
5. Add versioned artifact/release manifests and register v0.1.0 as historical reference.
6. Register the curated five-class model as `v0.2.0-rc1`, preserving its original hash privately and creating a sanitized public package only after provenance review.
7. Rewrite public docs to remove private details, correct licenses, narrow performance claims, and explain review-only semantics.
8. Create GitHub releases and mirror validated model packages to Hugging Face from the same manifest.
9. Separately present a Pi deployment plan with backup, checksum, compile/load tests, rollback, bounded systemd service, disk guard, and BirdNET health checks.
10. Touch BirdNET-Pi only after explicit deployment approval.

## Initial decision boundary (superseded)

The audit and registry are complete. GitHub, Hugging Face, and BirdNET-Pi remain unchanged.

The next decision is whether to:

- prepare a local-only corrected source/release branch;
- publish corrected GitHub/Hugging Face state while leaving the Pi untouched;
- or stop at this audit.

## Final reconciliation — 2026-07-14

The user selected v0.1.0 as the sole canonical public model and approved public cleanup. The exact model bytes remain unchanged:

```text
SHA-256: 5e6ecfc68d78a2cf2e9e9e47da5cb58d696e8de354fd620cfcccc5db9da48702
Bytes:   474,892
Classes: background, bee, cicada_drone, cricket_katydid, frog, grasshopper
```

### Sanitized source release

- Canonical source: `https://github.com/vortexpjeff/insectnet`
- Clean root commit: `11b56fff9276fae9f9889cf561df247c5cd008d6`
- Tag and GitHub Release: `v0.1.0`
- Release assets: exact classifier, manifest, wheel, and source distribution.
- Python runtime boundary: Python 3.11+ and scikit-learn 1.8.0.
- Test result: 18 passed; Ruff passed.
- Fresh wheel verification/scoring and extracted-source-distribution tests passed.
- The verifier refuses to deserialize a joblib artifact if byte size or SHA-256 differs.
- Independent blocker/high re-review verdict: **APPROVE**.

GitHub was deleted and recreated at the same public URL because a force-push left the former commit directly retrievable. After recreation, the former raw revision returned 404 and its commit API lookup was unresolvable. A fresh scan of all 20 public blobs found zero prohibited location/access values. The downloaded GitHub Release classifier matched the canonical SHA-256.

### Hugging Face release mirror

- Model mirror: `https://huggingface.co/TheVortexProject/insectnet`
- Clean root commit: `96081fee19b1bfe9e480177d9be9751ec2818e4c`
- Tag: `v0.1.0`
- Public files: model card, exact classifier, manifest, provenance, privacy policy, runtime requirements, and LFS attributes.

Hugging Face was also deleted and recreated so the prior location-bearing history would not remain addressable. Both former revision lookups returned 404. The new seven-file surface produced zero prohibited location/access findings, and the downloaded classifier matched the canonical SHA-256.

### Local cleanup and retained boundary

- Eighteen non-v0.1 workstation files were quarantined, checksum-verified, then removed after both public surfaces passed verification.
- Temporary pre-cleanup GitHub/Hugging Face mirrors and authentication helpers were removed.
- Historical hashes and findings remain in the registry without retaining the removed workstation artifact bytes.
- Machine-readable final record: `docs/audit/insectnet_cleanup_ledger_2026-07-14.json`.
- BirdNET-Pi remained read-only and unchanged. Its inactive sidecar and private non-v0.1 backup artifacts remain a separate boundary requiring explicit write approval.
