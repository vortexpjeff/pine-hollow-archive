# 3. Model, dataset, and deployment dossier

## Scope

This dossier distinguishes six objects that must not be called “the model” interchangeably:

1. public InsectNet Research 0.2.0 joblib artifact;
2. public ChickenNet Research 0.1.0 joblib artifact;
3. later private InsectNet Research 0.3.0 dev2 joblib artifact;
4. later private ChickenNet Research 0.2.0 dev2 joblib artifact;
5. strict InsectNet dev2 broad-head runtime bundle;
6. strict ChickenNet dev2 broad-head runtime bundle.

All use frozen 1,536-dimensional Perch 2 embeddings under the same five-second, 32 kHz mono float32 feature contract. The Perch model-tree SHA-256 is:

```text
3fb2d54b3e34534f1130052b25737e54bbb5ebfd340ec040d4510772b64c81ff
```

The Perch weights are not redistributed here.

## Artifact identity matrix

| Object | Status | Exact identity |
|---|---|---|
| Public InsectNet Research 0.2.0 | Public research artifact; not deployed | artifact SHA-256 `27bf603a6dec2df2789b3bf9241f5e035ccdea5909c4ecf252623ff9304afe32` |
| Public ChickenNet Research 0.1.0 | Public research artifact; not deployed | artifact SHA-256 `a5b83b648b19d2837fe775161cf35fce22f2a717e630c08253f2b9c6d2fe58d0` |
| Private InsectNet Research 0.3.0 dev2 | Private successor candidate; source of field export | joblib SHA-256 `9cd5f753db357220a180ead0d13019d46f69d469898b9a88bfdb12ca38fecf14` |
| Private ChickenNet Research 0.2.0 dev2 | Private successor candidate; source of field export | joblib SHA-256 `d1595cc65a484ea963172dcc3c8d4b20e0fb6fbc0771883b40105b77668d6686` |
| Insect dev2 field bundle | Private deployed broad head | bundle ID `ff8d28f5e8d0416eb63e7b958b6b950b69dd89a0baca0089f399b20cbc3c529f` |
| Chicken dev2 field bundle | Private deployed broad head | bundle ID `d81cd5aee82176065f79abe4ae19db69f5c52c0ca4818d43fd981bf7781dcc41` |

### Public release identities

| Artifact | Dataset hash | Public revision |
|---|---|---|
| InsectNet 0.2.0 | `d59cde46a933b85c1cd46f944c6df5c9c6a7587efe7c354b5cbe22b2d0698240` | Hugging Face `b435c9baa95e5726cb03b57707b1a6c24291f934` |
| ChickenNet 0.1.0 | `974df55df9a3262944e32563e1111cf6f32cf52a128548a39aab5d69852bc3b0` | Hugging Face `2487e6c010aa3553ce6c1172ae7f51194f35379f` |

### Private dev2 training identities

| Artifact | Dataset hash | Training-report state |
|---|---|---|
| InsectNet 0.3.0 dev2 | `825c40602fe65611c3bef36c4fc8f7b120913b62a56728b355ccf8f775e178a5` | `research_candidate_not_deployed` at report creation |
| ChickenNet 0.2.0 dev2 | `eae3953337fa2014596d5e95f0c63387421366196fed38888a5723da01f33935` | `research_candidate_not_deployed` at report creation |

### Strict runtime member identities

| Bundle | `model.json` SHA-256 | `weights.npz` SHA-256 | Derived bundle ID |
|---|---|---|---|
| Insect dev2 field probe | `cacff9ab9f91686ab30b762dbbeae0030a55354c084a35354bbf6fed572eed5a` | `a57b8eb341cce154d27b5cbcd33100b6abcb4a989e5f5d08d59855dd588c5d58` | `ff8d28f5…c529f` |
| Chicken dev2 field probe | `55f90ded3c634191614b7a1db418b7062529765a985397572d83213490e3a809` | `fc000e6a253cee2163379bbc6ec533522402cc88755ec35c8188eb62db8e0a61` | `d81cd5ae…cc41` |

The runtime computes bundle identity as SHA-256 over the concatenated member checksum strings. The strict bundle metadata records the source joblib hash, training dataset hash, preprocessing recipe, Perch tree hash, feature dimension/dtype, threshold, and environment versions.

## Public InsectNet Research 0.2.0

### Training frame

| Source | Windows | Role |
|---|---:|---|
| InsectSet459 | 2,096 | insect positives |
| ESC-50 | 1,960 | environmental negatives; insect class excluded |
| Ross-308 | 317 | poultry/ventilation hard negatives |
| iNaturalist Domestic Chicken | 42 | observer-grouped hard negatives |
| iNaturalist Domestic Cat | 26 | observer-grouped hard negatives |
| **Total** | **4,441** | mixed research lane |

InsectSet459 observations were grouped by contributor, not split by window. Source rights were tracked, with ESC-50 retained in a noncommercial research lane.

### Internal grouped test

| Head | Support | AP | F1 |
|---|---:|---:|---:|
| insect presence | 236 | 0.987 | 0.963 |
| cicada | 102 | 0.959 | 0.892 |
| Orthoptera | 134 | 0.943 | 0.875 |

Macro AP was 0.963; macro F1 was 0.910. These establish source-partition learnability, not stationary-microphone reliability.

### Material external limitation

On a locked 26-observer Domestic Dog challenge, the broad head activated on 11/26 windows (42.3%). Incidental insects may exist in outdoor recordings, but this rate was correctly treated as evidence that the artifact was not field-ready.

A private frog-reviewed archive produced insect activations in 1,207/1,308 windows. Because that archive was reviewed for frogs rather than insect absence, 92.3% is an activation rate—not a false-positive rate.

## Public ChickenNet Research 0.1.0

### Training frame

| Source | Windows | Role |
|---|---:|---|
| Ross-308 | 317 | chicken contexts and animal-free ambient recordings |
| ESC-50 | 2,000 | rooster, hen, and environmental examples/negatives |
| **Total** | **2,317** | mixed research lane |

Ross-308 was grouped by bird. ESC-50 was grouped by original Freesound source ID rather than published fold because the audit found source IDs crossing folds.

### Internal grouped test

The three heads had AP/F1 of 1.0 in the internal grouped test, but the crow head had only four positive test examples. The result is a fit check with weak support, not field-readiness evidence.

### External diagnostics

A locked 42-window iNaturalist Domestic Chicken weak-positive challenge produced 33 broad-head passes (78.6%). It had no negative examples and call type was not annotated, so it cannot estimate precision or crow/other-call accuracy.

A private frog-reviewed stationary-microphone archive produced 10/1,308 broad candidate activations. Chicken absence was not separately reviewed, so this is an upper-bound diagnostic, not a confirmed false-positive rate.

## Private InsectNet Research 0.3.0 dev2

### Why it is a distinct artifact

The dev2 frame added a full Oxfordshire PAM training source and additional iNaturalist negatives. It contains 6,097 samples:

| Source | Samples |
|---|---:|
| InsectSet459 | 2,096 |
| ESC-50 | 1,960 |
| Ross-308 negatives | 317 |
| iNaturalist chicken negatives | 42 |
| iNaturalist cat negatives | 26 |
| Oxfordshire full-train | 1,656 |

Partition counts were 4,703 train, 796 validation, and 598 test. The recorded rights lanes were 4,137 core-releasable and 1,960 research-noncommercial samples.

### Internal test

| Head | AP | F1 | Support |
|---|---:|---:|---:|
| insect presence | 0.969 | 0.919 | 236 |
| cicada | 0.956 | 0.873 | 102 |
| Orthoptera | 0.897 | 0.834 | 134 |

Macro AP was 0.941; macro F1 was 0.875.

### Locked Oxfordshire cross-site test

Thresholds were frozen before downloading the test audio. Across 197 recordings from three held-out sites:

- broad insect presence: AP 0.988, precision 0.979, recall 0.829, F1 0.898;
- 141 true positives, 3 false positives, 29 false negatives at recording-event level.

This is the strongest independent domain result in the build. It still does not evaluate Pine Hollow, the deployed 0.9995 threshold, seasonal variation, or local confounders.

### Locked dog negative diagnostic

The dev2 broad head activated on 6/26 dog windows (23.1%) at its frozen training threshold. This improved the public artifact’s 11/26 diagnostic but did not eliminate cross-domain activation.

## Private ChickenNet Research 0.2.0 dev2

### Expanded frame

The dev2 frame contains 5,492 samples:

| Source | Samples |
|---|---:|
| SmartEars public frame | 3,000 |
| ESC-50 | 2,000 |
| Ross-308 | 317 |
| Laying-hen control tranche | 96 |
| Poultry-health tranche | 79 |

Partition counts were 3,787 train, 840 validation, and 865 test. The recorded rights lanes were 3,492 core-releasable and 2,000 research-noncommercial samples. Per-head unknown-label semantics prevented unreviewed call types from becoming negatives automatically.

### Internal test

| Head | AP | F1 | Support |
|---|---:|---:|---:|
| chicken presence | 0.985 | 0.947 | 305 |
| crow | 1.000 | 0.857 | 4 |
| other vocalization | 1.000 | 1.000 | 58 |

The crow support limitation remains.

### External diagnostics

- Locked 42-window chicken weak-positive challenge: 31/42 broad passes (73.8%) at the dev2 training threshold.
- Private frog-reviewed archive: 23/1,308 broad activations (1.76%) at the dev2 training threshold.

Neither diagnostic directly evaluates the deployed 0.9999 field threshold.

## Training reproducibility caveat

Both private dev2 run reports record:

- Git commit `16c71e04…`;
- a dirty worktree affecting the training script, candidate code, and tests.

Therefore the dev2 artifacts are strongly identified by exact artifact, dataset, embedding, window-manifest, and runtime-export hashes, but the original training executions are **not clean-commit reproductions**. The final runtime does not rely on source reconstruction: it loads strict checked bundles and verifies exact Perch identity. A future formal model release should rerun dev2 from a clean pinned commit and publish the resulting artifact comparison.

## Deployment contract

Only the broad heads are active:

| Runtime bundle | Active class | Training threshold | Deployed review threshold |
|---|---|---:|---:|
| Insect dev2 field probe | `insect_present` | 0.85 | 0.9995 |
| Chicken dev2 field probe | `chicken_vocalization_present` | 0.47 | 0.9999 |

Subtype heads are not deployed. A retained event means:

> At least one exact five-second Perch window crossed the private operational threshold for the broad head, producing a candidate for review.

It does not mean:

- a calibrated probability;
- a confirmed audible target;
- species/call subtype identity;
- complete detection of all target sounds;
- ecological occurrence outside the exact recording/span;
- abundance or occupancy.

## Published and private surfaces

### Public

- model cards and public joblib artifacts for InsectNet 0.2.0 and ChickenNet 0.1.0;
- public source/training code and aggregate reports;
- exact public hashes and disclosed limitations.

### Private

- dev2 joblib artifacts and row-level manifests;
- embeddings and raw/source audio;
- runtime field bundles;
- local field scores, events, and review evidence;
- exact machine configuration.

The public handoff documents identities and aggregate evidence without redistributing private artifacts or extending source licenses.