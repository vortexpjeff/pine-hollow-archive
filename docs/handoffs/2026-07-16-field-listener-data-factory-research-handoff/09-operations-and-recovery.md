# 9. Operations and recovery

## Scope

This is the concise cross-system runbook. The field-listener and factory repositories contain the full component-specific procedures.

Use placeholders:

- `<field-repo>` = private `insectnet-field` checkout;
- `<archive-repo>` = `pine-hollow-archive` checkout.

Do not copy private paths, credentials, database content, or raw evidence into public reports.

## Normal state

### Field listener

The target and both services should be enabled/active continuously:

```bash
cd <field-repo>
bin/fieldctl health
bin/fieldctl status
systemctl --user is-enabled insectnet-field.target
systemctl --user is-active insectnet-field.target
```

Healthy means more than `active`:

- capture `connected=true`;
- capture/listener timestamps fresh;
- producer drops/gaps zero;
- producer and receiver queues below guards and moving;
- no dead letters/drop evidence;
- SQLite quick-check `ok`;
- WAL below limit;
- review WAV/JSON pairs match;
- disk/review capacity safe.

### Factory

The timer should be enabled and active. The service is a short one-shot and should normally be inactive between runs:

```bash
cd <archive-repo>
python3 scripts/run_data_factory.py status
python3 scripts/run_data_factory.py validation-status
systemctl --user is-enabled pine-hollow-data-factory.timer
systemctl --user is-active pine-hollow-data-factory.timer
systemctl --user status pine-hollow-data-factory.timer --no-pager
journalctl --user -u pine-hollow-data-factory.service -n 100 --no-pager
```

A continuously active factory service can indicate a stuck cycle; an inactive timer means unattended work is off.

## Field controls

```bash
cd <field-repo>
bin/fieldctl start
bin/fieldctl stop
bin/fieldctl restart
bin/fieldctl status
bin/fieldctl health
bin/fieldctl logs
```

Stopping the private target does not stop BirdNET.

## Factory controls

### Read-only source validation

```bash
cd <archive-repo>
python3 scripts/run_data_factory.py dry-run
```

This uses an in-memory schema and verifies source ledger/evidence/bundles/context without persistent writes.

### One bounded manual CPU cycle

```bash
python3 scripts/run_data_factory.py cycle --trigger manual
```

The cycle takes a nonblocking process lock, checks disk, migrates additively, schedules changed CPU work, runs at most eight jobs, and cannot claim GPU jobs.

### Pause production safely

```bash
systemctl --user disable --now pine-hollow-data-factory.timer
systemctl --user stop pine-hollow-data-factory.service
```

Stopping the timer does not stop BirdNET, the field listener, or other Commons capture.

### Resume production

```bash
systemctl --user daemon-reload
systemctl --user enable --now pine-hollow-data-factory.timer
systemctl --user is-enabled pine-hollow-data-factory.timer
systemctl --user is-active pine-hollow-data-factory.timer
```

Enabling may immediately trigger a due cycle. Verify the one-shot result and next timer entry:

```bash
systemctl --user show pine-hollow-data-factory.service \
  -p ActiveState -p SubState -p Result -p ExecMainStatus
systemctl --user list-timers pine-hollow-data-factory.timer --all --no-pager
```

## Weekly desk

### Status/report

```bash
cd <archive-repo>
python3 scripts/run_data_factory.py validation-status
python3 scripts/run_data_factory.py validation-report
```

### Start locally

```bash
./launch_validation_desk.sh
```

Or:

```bash
python3 scripts/run_validation_desk.py --host 127.0.0.1 --port 8765
```

Open `http://localhost:8765`.

The desk is intentionally not a daemon. Stop it with `Ctrl+C` after review.

### Launcher readiness caveat

The current Windows launcher may open the browser before the server has completed startup. If the first page is a connection error or JSON `not_found`, wait for the terminal to show the listening server and refresh once. This is a remaining launcher UX issue, not an evidence/database failure.

### Review discipline

- use exact five-second player as the judged unit;
- use full recording only as context;
- do not inspect model details elsewhere before saving;
- choose `uncertain` when needed;
- do not change thresholds from one packet;
- do not copy review audio or notes into public surfaces.

## Integrity checks

### Field

```bash
cd <field-repo>
bin/fieldctl health
```

If deeper inspection is needed, preserve database + WAL + SHM together before intervention.

### Factory

```bash
cd <archive-repo>
sqlite3 archive.db 'PRAGMA integrity_check;'
sqlite3 archive.db 'PRAGMA foreign_key_check;'
python3 scripts/audit_labels.py
```

Interpret the 32 known legacy violations according to the canonical operations record; new Commons violations are the release gate.

## Backup before risky work

### Factory SQLite

Use SQLite’s backup API so WAL state is included consistently:

```bash
cd <archive-repo>
stamp=$(date -u +%Y%m%dT%H%M%SZ)
python3 - "$stamp" <<'PY'
import sqlite3, sys
from pathlib import Path
out = Path('private/backups') / f'archive-{sys.argv[1]}.db'
out.parent.mkdir(parents=True, exist_ok=True)
src = sqlite3.connect(f'file:{Path("archive.db").resolve()}?mode=ro', uri=True)
dst = sqlite3.connect(out)
src.backup(dst)
dst.close()
src.close()
print(out)
PY
sha256sum private/backups/archive-${stamp}.db
```

Do not commit private backups.

### Field state

Before field recovery, preserve together:

- `events.sqlite3`;
- WAL and SHM;
- incoming/ready/processing/failed spools;
- capture/listener status;
- review evidence;
- incident ledgers;
- Pi producer ledger/spool when relevant.

## Recovery decision tree

### Capture disconnected

1. Run field health/logs.
2. Confirm the Pi sidecar remains active.
3. Do not delete Pi state or ready files.
4. Restart only the private field target if needed.
5. Verify ready count drains and received sequence catches observed sequence.
6. Treat nonzero drop or unexplained gap as an incident.

### Receiver queue full

Do not remove ready files. The correct mechanism is no ACK and upstream retention. Restore throughput/storage and allow replay.

### `processing` remains after crash

Restart recovery should return uncommitted work to ready. Preserve exact state before manual rename.

### `failed` nonempty

Preserve source/error record. Determine whether audio, artifact, storage, or code caused failure. Deleting the failed item is not recovery.

### Field SQLite unhealthy

1. Stop private target.
2. Preserve DB/WAL/SHM and spools.
3. Never repair the only copy.
4. Analyze a copy.
5. Compare counts, keys, and evidence pairs before restore.

### Factory job failed/stuck

Inspect state and immutable transitions:

```bash
sqlite3 archive.db '
SELECT job_id,job_type,energy_class,state,attempts,max_attempts,not_before,error
FROM commons_jobs
ORDER BY updated_at DESC LIMIT 50;'

sqlite3 archive.db '
SELECT transitioned_at,job_id,from_state,to_state,actor,reason
FROM commons_job_transitions
ORDER BY transitioned_at DESC LIMIT 100;'
```

Correct source/code first. Prefer a new explicit idempotency key after correction. Do not directly falsify job state.

### Validation audio rejected

The desk rejects missing, symlinked, hash-mismatched, or invalid-span audio. Do not bypass. Investigate media identity and packet provenance.

### Validation submission failed

The transaction should leave no partial review. Check packet status and SQLite/Commons integrity before retry.

### Sentinel drift

Do not overwrite expected values. Preserve the appended drift record and determine whether media bytes, archived context, or an artifact changed. Current sentinel checks do not perform fresh inference.

## Rollback boundaries

### Field listener retirement

1. Stop/disable only the private field target.
2. Preserve all field ledgers, spools, incidents, and evidence.
3. Stop/disable only the independent Pi sidecar.
4. Account for every ready sequence before removing helpers/key capability.
5. Do not modify BirdNET.

### Factory rollback

1. Disable timer/service.
2. preserve current database with SQLite backup;
3. verify selected backup hash/integrity;
4. restore only after scope confirmation;
5. rerun migration, dry-run, tests, and one manual cycle;
6. re-enable timers separately and inspect logs.

Additive schema objects can remain dormant. Never delete evidence to make old code appear clean.

## Change-control gates

### New model

- retain BirdNET separation;
- freeze/hash backbone and export bundle;
- deploy shadow/review-only;
- add factory bundle configuration;
- dry-run and import exact evidence;
- build independent queues/controls;
- review multiple days and conditions;
- document results before threshold changes.

### New automated job

Requires:

- allowlisted type/energy class;
- fixed handler;
- deterministic source watermark/key;
- idempotency/lease/failure/privacy/energy tests;
- operations and rollback docs;
- manual verification before timer inclusion.

### Protocol change

Create a new protocol version and packet manifest. Do not rewrite a reviewed historical packet.

## Never do these

- delete ready/failed audio to clear health;
- reset sequence counters;
- ACK before durable ownership;
- edit historical review/packet rows;
- treat a score as calibrated probability;
- infer abundance/absence from candidate counts;
- automatically add weekly reviews to training;
- expose raw audio, exact location, credentials, or private context;
- enable unattended GPU work without a new explicit decision.