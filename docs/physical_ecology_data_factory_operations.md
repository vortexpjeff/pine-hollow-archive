# Pine Hollow Physical-Ecology Data Factory Operations

## Paths

```text
Repository:       /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
Database alias:   archive.db
Canonical DB:     private/commons_lab/runtime/archive.db
Private data:     private/commons_lab
Field ledger:     ~/.local/share/insectnet-field/events.sqlite3 (read-only)
Field evidence:   ~/.local/share/insectnet-field/review (read-only)
Field incidents:  ~/.local/share/insectnet-field/incidents (read-only)
Observatory:      ~/vortex-site/data/observatory.json (read-only source)
Lock:             ~/.cache/pine-hollow-commons/data-factory.lock
User units:       ~/.config/systemd/user/pine-hollow-data-factory.*
```

Run commands from the repository root unless shown otherwise.

`archive.db` is a relative symlink to the canonical database. SQLite resolves it before creating WAL/SHM, so all database write artifacts remain inside `private/commons_lab/runtime/`. Do not replace the link with an independent database file.

### One-time runtime layout migration

For an older checkout where `archive.db` is still a regular file, first follow **Backup before risky work**, then run with the data-factory timer stopped:

```bash
systemctl --user stop pine-hollow-data-factory.timer pine-hollow-data-factory.service
test -f archive.db
test ! -L archive.db
test ! -e private/commons_lab/runtime/archive.db
sqlite3 archive.db 'PRAGMA integrity_check;'
mkdir -p private/commons_lab/runtime
mv archive.db private/commons_lab/runtime/archive.db
ln -s private/commons_lab/runtime/archive.db archive.db
sqlite3 archive.db 'PRAGMA integrity_check;'
```

Both integrity checks must return `ok`. The move must stay within the same filesystem. Do not run this while any archive process has the database open.

## Routine status

```bash
python3 scripts/run_data_factory.py status
systemctl --user status pine-hollow-data-factory.timer --no-pager
systemctl --user status pine-hollow-data-factory.service --no-pager
journalctl --user -u pine-hollow-data-factory.service -n 100 --no-pager
```

## Source validation without writes

```bash
python3 scripts/run_data_factory.py dry-run
```

This verifies all retained WAVs, sidecars, field-ledger rows, deployed bundle checksums, bundle identities, scores, source event IDs, and Observatory JSON. It uses an in-memory archive schema and reports `writes: false`.

## Manual bounded CPU cycle

```bash
python3 scripts/run_data_factory.py cycle --trigger manual
```

The cycle:

1. takes a non-blocking process lock;
2. checks free disk space;
3. migrates additively;
4. enqueues changed CPU stages;
5. runs at most eight jobs;
6. records run/job results;
7. never claims GPU jobs.

After newly imported events, one reconciliation context job may run once with zero inserted links because the archived-event watermark changed after scheduling. The following unchanged cycle must report zero created jobs and an empty outcomes list.

## Pause and resume automation

```bash
systemctl --user disable --now pine-hollow-data-factory.timer
systemctl --user enable --now pine-hollow-data-factory.timer
```

Stopping this timer does not stop BirdNET-Pi, the durable field listener, or Commons camera capture.

## Run one explicit GPU inventory probe

```bash
python3 scripts/run_data_factory.py gpu-probe --key manual-$(date -u +%Y%m%dT%H%M%SZ)
```

This enqueues one `deferrable_gpu` job and runs a worker authorized for that class. It executes a fixed `nvidia-smi` query only. The CPU timer cannot claim it.

## Build or refresh calibration queues

```bash
python3 scripts/run_data_factory.py queue-calibration --per-band 10
```

Queue creation is idempotent. It does not alter thresholds or training data.

## Record a human acoustic review

First query the pending item and exact windows:

```bash
sqlite3 archive.db '
SELECT q.queue_id,q.event_id,m.media_id,q.class_name,q.bundle_id,q.score_band,m.path
FROM commons_review_queue q
JOIN commons_media m ON m.event_id=q.event_id
WHERE q.state="pending"
ORDER BY q.priority DESC LIMIT 20;'

sqlite3 archive.db '
SELECT start_sample,end_sample,sample_rate,score,threshold,source_event_id
FROM commons_acoustic_windows
WHERE event_id="EVENT_ID" AND bundle_id="BUNDLE_ID"
ORDER BY start_sample;'
```

Append the review:

```bash
python3 scripts/run_data_factory.py record-review \
  --event-id EVENT_ID \
  --media-id MEDIA_ID \
  --bundle-id BUNDLE_ID \
  --class-name chicken_vocalization_present \
  --present \
  --certainty confirmed \
  --reviewer human:jeffrey \
  --start-sample 160000 \
  --end-sample 320000 \
  --notes 'Rooster audible in reviewed window'
```

To correct a review, append another and pass `--supersedes ASSERTION_ID`. Never update the earlier assertion.

## Add a research/development record

```bash
python3 scripts/run_data_factory.py research-log \
  --record-type experiment \
  --title 'Short experiment title' \
  --body 'Question, method, evidence, result, uncertainty, and next decision.' \
  --source 'https://example.org/source'
```

Also create a dated Markdown record under `docs/` when the work affects architecture, model interpretation, field practice, or operations.

## Job states and retries

Inspect queued/running/failed work:

```bash
sqlite3 archive.db '
SELECT job_id,job_type,energy_class,state,attempts,max_attempts,not_before,error
FROM commons_jobs
ORDER BY updated_at DESC LIMIT 50;'
```

Inspect immutable history:

```bash
sqlite3 archive.db '
SELECT transitioned_at,job_id,from_state,to_state,actor,reason
FROM commons_job_transitions
ORDER BY transitioned_at DESC LIMIT 100;'
```

Recoverable handler failures return to `queued` with exponential backoff. A job becomes terminal `failed` when attempts reach `max_attempts`. A background heartbeat renews an owned, unexpired running lease; each renewal is visible as a `running → running` transition. Completion or failure with an expired/foreign lease is rejected. Expired worker leases are recovered on the next claim.

## Current temporal context

Raw `commons_event_links` rows are immutable history. Query current nearest relationships through the view:

```bash
sqlite3 archive.db '
SELECT source_event_id,target_event_id,relation,method,offset_seconds
FROM commons_current_event_links
ORDER BY relation,source_event_id;'
```

Automated methods include the configured tolerance. Do not infer causation from these rows.

## Field incident provenance

The scheduled `field_incident_import` job preserves valid JSON/JSONL versions from the field incident directory under `private/commons_lab/field_incidents/`. It appends `incident` research records with SHA-256 and record counts. It does not create media or acoustic events for unavailable recordings.

Do not modify job state directly unless performing documented incident recovery. Prefer a new job with a new explicit idempotency key after correcting the source problem.

## Integrity checks

```bash
sqlite3 archive.db 'PRAGMA integrity_check;'
sqlite3 archive.db 'PRAGMA foreign_key_check;'
python3 scripts/audit_labels.py
```

Current known legacy condition: 32 `label_events → clips` violations predate schema version 4. New Commons violations remain a hard failure.

## Backup before risky work

Use SQLite's backup API so WAL state is included consistently:

```bash
stamp=$(date -u +%Y%m%dT%H%M%SZ)
python3 - "$stamp" <<'PY'
import sqlite3,sys
from pathlib import Path
out=Path('private/backups')/f'archive-{sys.argv[1]}.db'
out.parent.mkdir(parents=True,exist_ok=True)
src=sqlite3.connect(f'file:{Path("archive.db").resolve()}?mode=ro',uri=True)
dst=sqlite3.connect(out)
src.backup(dst)
dst.close();src.close()
print(out)
PY
sha256sum private/backups/archive-${stamp}.db
```

## Restore boundary

1. Disable the data-factory and camera timers.
2. Make another copy of the current database; do not delete it.
3. Verify the selected backup hash and `PRAGMA integrity_check`.
4. Restore only after confirming scope.
5. Re-run migration, dry-run, full tests, and one manual cycle.
6. Re-enable timers separately and inspect logs.

Schema rollback does not require dropping new tables. They can remain dormant. Never delete evidence to “roll back” code.

## Add a new model

- Keep BirdNET separate.
- Build a verified field bundle using the existing contract.
- Deploy it in shadow mode.
- Add the bundle directory to factory configuration.
- Run dry-run.
- Import changed retained evidence.
- Create a score-band queue.
- Review independent days and controls.
- Record the evaluation before changing any threshold.

## Add a new automated job

A new job requires code and tests. Do not insert an arbitrary job type into SQLite and expect it to execute.

Required work:

1. map job type to energy class in `commons_lab/jobs.py`;
2. implement fixed handler in `commons_lab/factory.py`;
3. define source watermark and priority;
4. test idempotency, lease, failure, resource and privacy behavior;
5. document operation and rollback;
6. verify manually before adding it to the CPU cycle.

## Weekly field validation

The factory now creates one deterministic blinded packet per local week when the archived frame passes the protocol readiness gate.

Quick status:

```bash
python3 scripts/run_data_factory.py validation-status
```

Open the private local desk from Windows with `launch_validation_desk.bat`, or from WSL:

```bash
./launch_validation_desk.sh
```

Packet and cumulative reports:

```bash
python3 scripts/run_data_factory.py validation-report --packet-id vpk_EXACT_ID
python3 scripts/run_data_factory.py validation-report
```

The normal review burden is 24 exact spans per week. Do not inspect model scores before saving a judgment, change thresholds from one packet, or promote weekly reviews directly into training data.

Full protocol, launcher, CLI, report interpretation, sentinel and recovery instructions are in [`weekly_field_validation_desk.md`](weekly_field_validation_desk.md).
