# 11. Reproducibility and evidence index

## Reproducibility statement

This packet is reproducible at three different levels:

1. **Document integrity:** every packet file can be rehashed against `SHA256SUMS.txt`.
2. **Software verification:** source commits, tests, static checks, and installed-state comparisons can be rerun by an authorized operator.
3. **Evidence verification:** private ledgers, artifacts, audio, manifests, and packet rows can be rehashed locally.

It is not fully publicly reproducible at the raw-data level because private audio, exact site context, row-level training manifests, and some source media cannot be redistributed. The packet distinguishes retained-private verification from public reproduction.

## Evidence hierarchy

### E1 — immutable public artifacts

Publicly retrievable, exact identity:

- Git commits;
- Hugging Face revisions;
- public joblib SHA-256;
- public dataset hashes;
- public model cards;
- public aggregate evaluation reports.

### E2 — immutable private artifacts

Retained locally, exact identity but not redistributed:

- dev2 joblib artifacts;
- strict runtime bundle members;
- private row-level manifests/embeddings;
- field WAV/sidecars;
- field and Commons SQLite databases;
- packet manifests and reviews;
- incident ledgers.

### E3 — automated verification observations

- test outputs;
- integrity/foreign-key checks;
- replay/fault tests;
- systemd state;
- sandbox probes;
- live service cycles;
- checksum comparisons.

### E4 — human observations

- exact-span append-only v4 review labels;
- quality/confounder metadata;
- measured review burden;
- hidden-repeat agreement.

### E5 — interpretation

Aggregate summaries and bounded scientific conclusions derived from E1–E4. Interpretations are not new observations.

## First-party source index

### Public model/training repository

Repository: <https://github.com/vortexpjeff/insectnet>

Key release commit:

- `16c71e04ea8b9c34dec79df55f7fb8552af5dfd5` — public privacy/hierarchy/reproducibility correction.

Public model cards:

- <https://huggingface.co/TheVortexProject/insectnet-research-0.2.0-perch2>
- <https://huggingface.co/TheVortexProject/chickennet-research-0.1.0-perch2>

Verified public revisions:

- InsectNet: `b435c9baa95e5726cb03b57707b1a6c24291f934`;
- ChickenNet: `2487e6c010aa3553ce6c1172ae7f51194f35379f`.

The model cards are canonical for public artifact scope, data summaries, evaluation, rights, and limitations.

### Private model-training evidence

Retained-private run reports:

- `insectnet-research-0.3.0-perch2-publicdata-dev2/run_report.json`;
- `insectnet-research-0.3.0-perch2-publicdata-dev2/oxfordshire_locked_test_report.json`;
- `insectnet-research-0.3.0-perch2-publicdata-dev2/inat_dog_negative_report.json`;
- `chickennet-research-0.2.0-perch2-publicdata-dev2/run_report.json`;
- `chickennet-research-0.2.0-perch2-publicdata-dev2/inat_chicken_weak_positive_report.json`;
- `chickennet-research-0.2.0-perch2-publicdata-dev2/private_frog_activation_report.json`.

These files contain private paths; only sanitized aggregates and exact artifact/dataset hashes appear in this public packet.

### Private field-listener repository

Repository: `https://github.com/vortexpjeff/insectnet-field` (private).

Canonical commits:

- `fb732c8db368f8f641d7e2964fd9359c70cb153a` — durable private listener;
- `383fd456250699375212cc963dcbc89c07588664` — verified Git publication record;
- `333f4f9c9b07d9202c21ceb30ce6fc07747ef173` — expanded durability/bioacoustic research.

Canonical documents:

- `docs/2026-07-15-engineering-report.md`;
- `docs/2026-07-15-architecture-and-durability.md`;
- `docs/2026-07-15-validation-results.md`;
- `docs/2026-07-15-incident-report.md`;
- `docs/2026-07-15-research-notes.md`;
- `docs/2026-07-15-operations-runbook.md`.

### Public archive/factory repository

Repository: <https://github.com/vortexpjeff/pine-hollow-archive>

Canonical build commits:

- `f833e32eb0b2594dc1c18bf427969f154ea6f309` — hardened physical-ecology factory;
- `f0ef51dfa67e17ba157c75d409b06a1788bc4f29` — unattended production cycles;
- `4a10f940e794ce4a51cfe3f737dae10d85b9414c` — weekly blinded validation desk;
- `16c2344e2d6af4daee171fe5aa25d3390d9c5414` — active-protocol and descriptor-safe audio fixes;
- `7afc63dda3f4847f09cad43197a8b4d4f3624b21` — validated factory restart.

Canonical documents:

- `docs/physical_ecology_data_factory_architecture.md`;
- `docs/physical_ecology_data_factory_operations.md`;
- `docs/physical_ecology_data_factory_research_2026-07-16.md`;
- `docs/physical_ecology_data_factory_validation_2026-07-16.md`;
- `docs/physical_ecology_data_factory_development_log_2026-07-16.md`;
- `docs/weekly_field_validation_desk.md`.

This handoff directory is the synthesis layer. Earlier documents remain evidence for their dated states.

### Fixed live snapshot

Captured 2026-07-16 19:40:42 UTC using read-only commands:

```bash
<field-repo>/bin/fieldctl health
python3 scripts/run_data_factory.py status
python3 scripts/run_data_factory.py validation-status
python3 scripts/run_data_factory.py validation-report --packet-id vpk_31d5158ef95e1fe35caff3e4
systemctl --user is-enabled/is-active ...
git rev-parse HEAD
```

The sanitizer retained counts, unit states, hashes/IDs needed for provenance, and removed local paths/configuration details.

## External primary and technical sources

### Perch and transfer learning

- Google Research Perch repository: <https://github.com/google-research/perch>
- Ghani et al. (2023), “Global birdsong embeddings enable superior transfer learning for bioacoustic classification,” *Scientific Reports*. <https://doi.org/10.1038/s41598-023-49989-z>
- Perch BIRB domain-generalization benchmark: <https://arxiv.org/abs/2312.07439>

Use in this build: frozen feature representation and transfer-learning context. These sources do not validate the Pine Hollow heads.

### BirdNET

- Kahl, Wood, Eibl & Klinck (2021), “BirdNET: A deep learning solution for avian diversity monitoring,” *Ecological Informatics*. <https://doi.org/10.1016/j.ecoinf.2021.101236>
- BirdNET-Analyzer: <https://github.com/birdnet-team/BirdNET-Analyzer>

Use in this build: existing recorder/analyzer boundary. BirdNET’s published evaluation does not validate InsectNet/ChickenNet.

### Modular edge bioacoustics context

- Vuilliomenet et al., “acoupi: An Open-Source Python Framework for Deploying Bioacoustic AI Models on Edge Devices,” DOI <https://doi.org/10.1111/2041-210X.70208>, arXiv <https://arxiv.org/abs/2501.17841>.

acoupi is relevant prior work on modular edge deployment. This build does **not** use acoupi.

### Passive-acoustic claim boundaries

- Gibb et al. (2019), “Emerging opportunities and challenges for passive acoustics in ecological assessment and monitoring.” <https://doi.org/10.1111/2041-210X.13101>
- Sugai et al. (2019), “Terrestrial Passive Acoustic Monitoring: Review and Perspectives.” <https://doi.org/10.1093/biosci/biy147>
- Navine et al. (2024), “All thresholds barred: direct estimation of call density in bioacoustic data.” <https://doi.org/10.3389/fbirs.2024.1380636>

Use: distinction among recorded events, detectability, and ecological population claims.

### SQLite durability

- Atomic commit: <https://www.sqlite.org/atomiccommit.html>
- Write-ahead logging: <https://www.sqlite.org/wal.html>
- `PRAGMA synchronous`: <https://www.sqlite.org/pragma.html#pragma_synchronous>

Use: WAL/`FULL`, backup, ownership, and transaction reasoning.

### Linux filesystems

- `rename(2)`: <https://man7.org/linux/man-pages/man2/rename.2.html>
- `fsync(2)`: <https://man7.org/linux/man-pages/man2/fsync.2.html>
- `openat(2)`: <https://man7.org/linux/man-pages/man2/openat.2.html>

Use: atomic namespace publication, directory durability, and descriptor-relative no-symlink traversal.

### systemd and OpenSSH

- `systemd.exec`: <https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html>
- OpenSSH `sshd(8)` authorized-key options: <https://man.openbsd.org/sshd.8>

Use: sandbox limitations and forced-command capability design.

## Public dataset/source citations

- InsectSet459: `academic-datasets/InsectSet459`, pinned revision in retained provenance.
- ESC-50: Piczak, DOI <https://doi.org/10.1145/2733373.2806390>.
- Ross-308: Díaz de Cerio et al., DOI <https://doi.org/10.34810/DATA3437>.
- Other private-dev2 sources and rights are enumerated in retained run/manifests; audio is not redistributed here.

## Reproduction recipes

### Verify this packet

From the packet directory:

```bash
sha256sum -c SHA256SUMS.txt
```

`SHA256SUMS.txt` excludes itself.

### Verify public model revisions

```bash
curl -fsSL \
  https://huggingface.co/TheVortexProject/insectnet-research-0.2.0-perch2/raw/main/README.md
curl -fsSL \
  https://huggingface.co/TheVortexProject/chickennet-research-0.1.0-perch2/raw/main/README.md
```

Use the public repository/Hugging Face inventory procedure to download every listed object and rehash against the published inventory.

### Verify runtime bundle identity privately

For each strict bundle:

1. rehash `model.json` and `weights.npz` against `SHA256SUMS`;
2. compute bundle ID as SHA-256 of concatenated member checksum strings;
3. compare source artifact, dataset/training hash, Perch tree, preprocessing, class, threshold, shape, dtype, and finite values;
4. compare loaded IDs with `fieldctl health`.

### Verify field listener

```bash
cd <field-repo>
uv run pytest -q
uv run ruff check src tests
uv run python -m compileall -q src tests
bash -n bin/sandbox-run
bin/fieldctl health
```

Systemd verification and live namespace probes require the deployed user manager.

### Verify factory

```bash
cd <archive-repo>
python3 -m unittest discover -s tests -q
pytest -q
python3 -m compileall -q commons_lab scripts tests
python3 scripts/run_data_factory.py dry-run
python3 scripts/run_data_factory.py status
python3 scripts/run_data_factory.py validation-status
sqlite3 archive.db 'PRAGMA integrity_check;'
```

Use the repository’s configured Python environment; do not install into a mismatched system interpreter.

### Reproduce packet report privately

```bash
python3 scripts/run_data_factory.py validation-report \
  --packet-id vpk_31d5158ef95e1fe35caff3e4
```

The report is derived from immutable packet/items, append-only reviews, exact source-recording identity, and stored model context.

## Reproducibility gaps

- public bundles omit private row-level manifests/audio;
- dev2 training reports record a dirty code worktree;
- runtime bundles are private and only their identities are public here;
- current live counts change after snapshot;
- physical power-cut behavior depends on the real storage stack and is not fully tested;
- human review is one reviewer/one packet;
- no complete bounded-time recall study exists.

## Citation rule for future summaries

When quoting this work, include:

- exact artifact or bundle identity;
- exact protocol version;
- snapshot or review date;
- whether the statement is machine score, human observation, or interpretation;
- the relevant limitation.

Avoid “the model was deployed” without naming which artifact, runtime bundle, purpose, and time.