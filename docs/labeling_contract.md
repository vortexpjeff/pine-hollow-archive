# Pine Hollow Labeling Contract

Goal: keep model suggestions, source labels, human review, derived tags, and training labels separate enough that the archive can improve without quietly poisoning itself.

## Label authority levels

| Level | Meaning | Training eligible? |
|---|---|---|
| Raw source | BirdNET/InsectNet/public dataset label | No, unless explicitly reviewed or trusted public foundation data |
| Model suggestion | Perch / retrained head output | No |
| Human-reviewed certain/probable | Listener chose tags in review app | Yes |
| Human-reviewed possible/unsure | Listener found a candidate but wants audit | No |
| Validated | Expert or explicit validation protocol | Yes; use the word only when true |

## Canonical fields

- `source_label`: original label from detector or dataset. Preserve highest resolution available.
- `human_tags`: JSON list; canonical post-review label field.
- `human_label`: comma-separated mirror for compatibility.
- `label_certainty`: `certain`, `probable`, `possible`, or `unsure`.
- `review_source`: `human`, `batch_auto_accept`, or future audit source.
- `label_events`: append-only audit trail of label actions.

## Training gate

A clip is training-eligible only when:

1. `review_status IN ('confirmed', 'corrected')`
2. `human_tags` is valid JSON or `human_label` can be parsed safely
3. certainty is absent/legacy or `certain` / `probable`
4. it is not deleted, skipped, or `needs_second_pass`
5. it does not mix `background` with target taxa/classes
6. its labels are not raw model output promoted without review

## AI boundary

AI may suggest, rank, and audit. AI does not create final training truth.

Allowed AI actions:

- propose candidate species/classes
- explain queue reason
- flag contradictions
- identify audit samples
- write `label_events` with `source='model'` or `source='batch_auto_accept'`

Not allowed:

- mark clips as human-reviewed
- use model predictions as final labels
- call field labels verified/validated without external validation

## Background semantics

`background` means environmental/non-target sound: wind, rain, water, silence, mechanical bed.

Bird vocalizations are not background. They may be useful negatives for some tracks only when explicitly reviewed for the training purpose. Never train the model to treat bird song as “nothing happening.”

## Batch mode

Batch mode is an acceleration tool, not a human-review substitute.

Batch-accepted clips are stored as `needs_second_pass` with `label_certainty='possible'` and must be audited before they become training-eligible.

## Audit script

Run before retrain:

```bash
python3 scripts/audit_labels.py
```

Retrain runs this automatically unless `--skip-label-audit` is passed for emergency use.
