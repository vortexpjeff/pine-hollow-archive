# 12. Git and release record

## Packet identity

| Field | Value |
|---|---|
| title | Pine Hollow Field Listener and Physical-Ecology Data Factory — Two-day research and engineering handoff |
| version | `2026-07-16.final.1` |
| covered period | 2026-07-15 through 2026-07-16 |
| fixed live snapshot | 2026-07-16 19:40:42 UTC |
| public repository | `https://github.com/vortexpjeff/pine-hollow-archive` |
| repository visibility | public, verified through GitHub API |
| packet location | `docs/handoffs/2026-07-16-field-listener-data-factory-research-handoff/` |
| local mirror | Hermes Audio directory with the same packet title/date |
| privacy class | public aggregate documentation; no raw/private evidence |

The Git publication commit is the commit containing this directory. Resolve it without relying on a self-referential hash in the file:

```bash
git log -1 --format='%H %ad %s' -- \
  docs/handoffs/2026-07-16-field-listener-data-factory-research-handoff
```

`SHA256SUMS.txt` verifies packet content independently of Git history and excludes itself.

## Source repository heads before packet publication

| Repository | Branch | Verified head | Visibility/source |
|---|---|---|---|
| Pine Hollow Archive | `master` | `7afc63dda3f4847f09cad43197a8b4d4f3624b21` | public API + remote |
| private field listener | `main` | `333f4f9c9b07d9202c21ceb30ce6fc07747ef173` | authenticated remote; prior record confirms private |
| public InsectNet code | `main` | `6b4dd53d5bf1d9810f5c824cd333ad7c6c111f40` | public remote |

The packet publication advances the archive head only. It does not modify or republish the private field repository or public model code.

## Model publication identities

| Object | Identity |
|---|---|
| public InsectNet artifact | `27bf603a6dec2df2789b3bf9241f5e035ccdea5909c4ecf252623ff9304afe32` |
| public InsectNet Hub revision | `b435c9baa95e5726cb03b57707b1a6c24291f934` |
| public ChickenNet artifact | `a5b83b648b19d2837fe775161cf35fce22f2a717e630c08253f2b9c6d2fe58d0` |
| public ChickenNet Hub revision | `2487e6c010aa3553ce6c1172ae7f51194f35379f` |
| private InsectNet dev2 source artifact | `9cd5f753db357220a180ead0d13019d46f69d469898b9a88bfdb12ca38fecf14` |
| private ChickenNet dev2 source artifact | `d1595cc65a484ea963172dcc3c8d4b20e0fb6fbc0771883b40105b77668d6686` |
| deployed Insect dev2 runtime bundle | `ff8d28f5e8d0416eb63e7b958b6b950b69dd89a0baca0089f399b20cbc3c529f` |
| deployed Chicken dev2 runtime bundle | `d81cd5aee82176065f79abe4ae19db69f5c52c0ca4818d43fd981bf7781dcc41` |

## Build commit chain

### Field listener

| Commit | Time EDT | Record |
|---|---|---|
| `fb732c8db368f8f641d7e2964fd9359c70cb153a` | July 15 21:58 | durable private listener |
| `383fd456250699375212cc963dcbc89c07588664` | July 15 22:00 | verified Git publication |
| `333f4f9c9b07d9202c21ceb30ce6fc07747ef173` | July 15 22:09 | expanded durability/research record |

### Factory and weekly desk

| Commit | Time EDT | Record |
|---|---|---|
| `f833e32eb0b2594dc1c18bf427969f154ea6f309` | July 16 11:50 | hardened factory |
| `f0ef51dfa67e17ba157c75d409b06a1788bc4f29` | July 16 11:53 | unattended production cycles |
| `4a10f940e794ce4a51cfe3f737dae10d85b9414c` | July 16 15:13 | weekly blinded validation desk |
| `16c2344e2d6af4daee171fe5aa25d3390d9c5414` | July 16 15:22 | protocol/audio integrity fixes |
| `7afc63dda3f4847f09cad43197a8b4d4f3624b21` | July 16 15:27 | validated factory restart |

## Final software verification

### Field listener gate

Executed in the private field checkout:

```text
uv run pytest -q                         15 passed in 2.58 s
uv run ruff check src tests              passed
uv run python -m compileall -q src tests passed
bash -n bin/sandbox-run                  passed
```

### Factory gate

Executed in the archive checkout:

```text
python3 -m unittest discover -s tests -q 72 passed in 17.09 s
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest  72 passed in 194.62 s
python3 -m compileall ...                passed
git diff --check -- packet-directory    passed
```

#### Pytest environment note

The first final pytest invocation failed before test collection because a globally installed unrelated `launch_testing` plugin declared an obsolete `pytest_pycollect_makemodule(path, parent)` hook under the installed pytest version. The application unittest suite had already passed.

The factory pytest suite was rerun with third-party plugin autoload disabled:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

All 72 project tests then passed under the repository's configured pytest interpreter. No application code or test was skipped or altered. The global plugin conflict is an environment issue, and this record preserves it rather than reporting an uninterrupted gate.

## Live operational verification

Fixed snapshot observations:

- field health true;
- capture connected;
- both field units active;
- field SQLite quick-check `ok`;
- producer drops/gaps zero;
- all local field queues empty;
- factory schema 7;
- factory timer enabled and active;
- one-shot service inactive between runs;
- 68/68 jobs successful;
- active validation packet complete 24/24.

The timer had been deliberately paused during final production-code review. It was re-enabled only after closing the two final findings and rerunning full suites. Immediate due cycle `run_f74d6677628c45e5ada1f85e5d366c2a` succeeded.

## Packet contents

- `README.md`
- `01-executive-synthesis.md`
- `02-chronology-and-state-transitions.md`
- `03-model-dataset-and-deployment-dossier.md`
- `04-architecture-and-truth-contracts.md`
- `05-field-listener-engineering.md`
- `06-factory-schema-and-data-dictionary.md`
- `07-weekly-validation-methods-and-results.md`
- `08-validation-evidence-and-claim-boundaries.md`
- `09-operations-and-recovery.md`
- `10-incidents-and-hardening-record.md`
- `11-reproducibility-and-evidence-index.md`
- `12-git-and-release-record.md`
- `13-fixed-live-snapshot-sanitized.json`
- `SHA256SUMS.txt`

## Privacy and content gate

The packet is scanned for:

- machine-specific Windows/user-home paths;
- street address and exact coordinates;
- known LAN identifiers;
- private-key material;
- obvious token/password assignments;
- raw media and individual source-recording identities;
- broken local Markdown links;
- invalid JSON.

The machine-readable snapshot is sanitized and aggregate. It contains packet ID, manifest hash, bundle IDs, Git heads, counts, coverage, and aggregate review results; it contains no raw audio, source-recording IDs, local paths, coordinates, credentials, or notes.

## Deliberately excluded

Not committed or mirrored into this final packet:

- raw/candidate/control WAVs;
- private evidence sidecars;
- field and Commons databases;
- WAL/SHM files and backups;
- private model joblibs/bundles/manifests/embeddings;
- service config and SSH material;
- exact location or private context payloads;
- earlier Hermes Audio packet media files;
- unrelated working-tree changes.

## Working-tree isolation

At packet construction, unrelated pre-existing working-tree changes existed in legacy Streamlit launcher/review scripts. The documentation release stages only this new handoff directory. Those unrelated edits/deletions remain outside the packet commit.

## Mirror contract

The Hermes Audio copy is generated from the repository packet after content freeze. Verification requires:

1. identical relative file list;
2. `sha256sum -c SHA256SUMS.txt` in both locations;
3. per-file hash equality between repository and local mirror.

The local mirror is a convenience handoff. Git is the versioned public record.

## Release interpretation

The documentation release records a working private evidence pipeline and its limitations. It does not publish private evidence and does not change model, threshold, service, timer, review, or database state.