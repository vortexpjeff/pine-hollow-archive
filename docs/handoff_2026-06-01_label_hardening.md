# Handoff — label hardening pass, 2026-06-01

## State

Archive is not broken.

Verified after changes:

```bash
python3 -m py_compile scripts/schema_hardening.py scripts/migrate_schema.py scripts/audit_labels.py scripts/review_app.py scripts/retrain.py
python3 tests/test_audit_labels.py
python3 scripts/audit_labels.py
python3 scripts/retrain.py --track insectnet --dry-run
```

Results:

- tests: 9 OK
- label audit: 0 BLOCK, 0 WARN
- insectnet dry-run: 2877 training samples
- background examples: 500
- dry-run next version: v0.3.0

No Pi touched.

## Files added

- `scripts/schema_hardening.py`
  - shared idempotent schema migration
  - adds/backfills `label_certainty`, `review_notes`, `review_source`
  - creates `label_events`
  - defines `training_eligibility_sql()`

- `scripts/migrate_schema.py`
  - manual migration CLI
  - live DB already migrated once successfully

- `scripts/audit_labels.py`
  - pre-retrain audit gate
  - blocks invalid training labels

- `tests/test_audit_labels.py`
  - 9 focused tests now

- `docs/labeling_contract.md`
  - label authority/training-gate contract

- `docs/handoff_2026-06-01_label_hardening.md`
  - this file

## Files modified

- `scripts/review_app.py`
  - now imports `ensure_review_hardening_schema` from `schema_hardening.py`
  - duplicate local schema function removed
  - confirm/delete/2nd-pass actions still write audit events
  - skip remains in-memory only

- `scripts/retrain.py`
  - runs schema migration before audit/training
  - all training queries now use `training_eligibility_sql()`
  - training gate requires:
    - `review_status IN ('confirmed', 'corrected')`
    - `label_certainty IN ('certain', 'probable')`
    - `review_source != 'batch_auto_accept'`
  - added `sanity_check_known_clips()` before artifact save

## Live DB migration

Ran:

```bash
python3 scripts/migrate_schema.py
```

Output:

```text
Schema migration OK. Added columns: ['label_certainty', 'review_notes', 'review_source']. label_events=True
```

Backfill behavior:

- legacy `confirmed/corrected` rows get `label_certainty='probable'`
- public rows get `review_source='public_dataset'`
- other legacy reviewed rows get `review_source='legacy_reviewed'`

This preserves current training counts while making provenance explicit.

## Important caution

`models/` appears untracked in git status. It existed as model artifacts; I did not touch it. Do not blindly `git add .` unless you intentionally want model artifacts tracked.

Recommended add list:

```bash
git add scripts/retrain.py scripts/review_app.py scripts/audit_labels.py scripts/schema_hardening.py scripts/migrate_schema.py tests/test_audit_labels.py docs/labeling_contract.md docs/handoff_2026-06-01_label_hardening.md
```

## Latest verification before context reset

Ran again after UI testing:

- `python3 -m py_compile scripts/schema_hardening.py scripts/migrate_schema.py scripts/audit_labels.py scripts/review_app.py scripts/retrain.py`
- `python3 tests/test_audit_labels.py` → 9 OK
- `python3 scripts/audit_labels.py` → 0 BLOCK, 0 WARN

Recent UI saves confirmed in DB and `label_events`:

- clip 121: Louisiana Waterthrush / Parkesia motacilla, certain, note `AC noise`
- clip 113: Louisiana Waterthrush / Parkesia motacilla, certain, note `good clip`
- clip 126: Sayornis phoebe / Chicken, possible, `needs_second_pass`, note `faint animal sounds`
- clip 127: Chicken / pig, probable, confirmed, note `faint animal sounds`

`archive.db-shm` and `archive.db-wal` may appear while SQLite/Streamlit has the DB open. They are untracked runtime files; do not commit them.

## Final small follow-up pass

Additional cleanup before handoff:

- removed unused `_has_column()` from `scripts/audit_labels.py`
- changed `retrain.py --list-tracks` counts to use the same training eligibility gate as retrain
- custom tags in `review_app.py` now insert into the multiselect after pressing Enter, so they can be removed before saving
- fixed insectnet WAV spectrograms by handling float audio dtype before normalization
- restaged safe files only; `models/` remains untracked

Review diff, then commit the code/docs only. Do not include `models/` unless intentional.

Suggested commit message:

```text
Harden label provenance and retrain eligibility
```
