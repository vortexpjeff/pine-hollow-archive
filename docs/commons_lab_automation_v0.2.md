# Pine Hollow Commons Lab Automation v0.2

**Built:** 2026-07-14  
**State:** Active local systemd user timer  
**Scientific boundary:** Private evidence collection only  
**Motto:** We are solarpunk citizen scientists searching for abundant systems.

## Current operating system

Commons Lab v0.2 is a bounded local instrument on Athena, the daily-use Windows/WSL workstation.

```text
systemd user timer
→ single-instance lock
→ 20 GiB free-space guard
→ Windows DirectShow camera warmup
→ one 180°-normalized JPEG
→ collision-resistant finalized path
→ atomic no-overwrite file promotion
→ private event and media ingest
→ 64×36 CPU quality sample
→ seven measurements
→ durable run record
→ silence on success / journal entry on failure
```

It does not use an LLM, GPU model, network request, Pi, website process, or Discord gateway.

## Schedule

```text
Every 30 minutes from 06:00 through 21:30 local time
```

Systemd calendar expression:

```text
*-*-* 06..21:00,30:00
```

`Persistent=false` is deliberate. If Athena is asleep, Windows is off, WSL is stopped, or the timer misses a tick, the system does not create a catch-up storm.

The corrected v0.2 timer's first observed calendar fire occurred at 18:30:01 on 2026-07-14 and completed successfully at 18:30:05. This verified the actual `OnCalendar` path rather than only a manual service start.

## Resource budget measured on Athena

A complete real capture, ingest, quality-analysis, and run-ledger tick measured:

| Resource | Measured result |
|---|---:|
| Wall time | 4.26 seconds |
| User CPU | 0.13 seconds |
| System CPU | 0.08 seconds |
| Peak resident memory | 69 MiB |
| GPU | Not used |
| Network | Not used |

The service runs with:

```text
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=90
```

Four initial v0.2 frames averaged 932,784 bytes. At 32 scheduled frames per day, that projects to approximately 10.15 GiB per year at the present scene and JPEG settings. This is an early measured estimate, not a storage guarantee.

## Durable private evidence

Root:

```text
/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive/private/commons_lab/
```

Layout:

```text
private/commons_lab/window_camera/YYYY/MM/DD/window_<timestamp>.jpg
```

`/private/` is excluded through `.git/info/exclude`. Raw frames remain outside version control even if someone runs a broad `git add`.

No automatic deletion is enabled. Capture stops safely when free space falls below 20 GiB.

## Camera behavior

- Camera: EMEET SmartCam Nova 4K
- Acquisition boundary: Windows DirectShow through FFmpeg
- Warmup: two seconds for auto-exposure and white balance
- Physical position: unchanged
- Raw orientation: upside down
- Canonical derivative: 180° rotation
- Raw unrotated frame: not retained
- Output: private 3840×2160 JPEG
- Final name: local timestamp with microseconds plus a random suffix
- Promotion: FFmpeg writes a unique `*.partial.jpg`; after validation, an atomic same-directory hard link creates the finalized path
- No-overwrite rule: existing finalized evidence raises `FileExistsError` before camera access, and atomic link creation also refuses a race-time collision

The full scene includes private buildings, fencing, equipment, garden layout, and other property details. It is not a public camera product.

## Quality measurements

Each successful v0.2 event receives seven transparent measurements computed from a 64×36 area-downsampled RGB sample:

| Phenomenon | Meaning |
|---|---|
| `image_mean_luma` | Mean normalized brightness |
| `image_bright_fraction` | Fraction of sample at or above 95% luma |
| `image_dark_fraction` | Fraction at or below 5% luma |
| `green_chromatic_coordinate` | Mean `G / (R + G + B)` for valid pixels |
| `excess_green` | Normalized `2G - R - B` signal |
| `image_edge_energy` | Mean neighboring-pixel luma difference |
| `capture_quality_state` | `accepted` or `degraded` |

Initial degraded flags:

- bright fraction above 0.55: `high_clipping`;
- dark fraction above 0.85: `mostly_dark`;
- edge energy below 0.01: `low_detail`.

These are transparent initial gates. They do not delete frames and are not yet calibrated scientific phenology thresholds. The bright lower foreground and sky remain a known view-specific limitation. A canopy region of interest belongs in v0.3.

## Run ledger

Schema version 3 adds `commons_runs`.

Every tick records:

- run ID;
- pipeline name;
- trigger type;
- start and completion timestamps;
- status: `running`, `success`, `skipped`, or `failed`;
- linked event ID when available;
- error text;
- device, path, disk state, quality result, and dimensions in metadata.

If a later stage fails after a file was captured, the run records whether the file was retained and its private path.

## Concurrency and failure behavior

### Overlap

The shared pipeline uses a non-blocking file lock:

```text
~/.cache/pine-hollow-commons/window-camera.lock
```

The lock wraps every capture entry point, including the systemd wrapper and manual CLI. A real CLI-versus-scheduler overlap test produced one run and one camera access. The overlapping process exited successfully and silently.

### Camera busy or unavailable

- Partial output is removed.
- The run is marked failed.
- The systemd service exits nonzero.
- The timer waits for the next normal tick.
- No immediate retry loop runs.

### Low disk

- No camera access occurs.
- The run is marked skipped with `minimum free-space guard`.
- Existing evidence remains untouched.

### Machine asleep or WSL stopped

- No frame is captured.
- The timer does not wake Windows.
- The missed frame is not replayed later.

## Operations

Run from:

```bash
cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
```

### Health and latest quality

```bash
python3 scripts/commons_lab_cli.py status
```

### Recent run history

```bash
python3 scripts/commons_lab_cli.py run-history --limit 10
```

### One manual complete tick

```bash
python3 scripts/commons_lab_cli.py capture-camera
```

### Timer status

```bash
systemctl --user status pine-hollow-commons-capture.timer
systemctl --user list-timers pine-hollow-commons-capture.timer
```

### Service journal

```bash
journalctl --user -u pine-hollow-commons-capture.service -n 50 --no-pager
```

### Pause collection

```bash
systemctl --user disable --now pine-hollow-commons-capture.timer
```

This does not delete media, measurements, events, or run history.

### Resume collection

```bash
systemctl --user enable --now pine-hollow-commons-capture.timer
```

### Stop an in-progress capture

```bash
systemctl --user stop pine-hollow-commons-capture.service
```

FFmpeg's partial file is removed by the shared camera boundary on handled failures. After an external forced kill, any `*.partial.jpg` is not ingested and can be audited safely.

### Remove automation without removing data

```bash
systemctl --user disable --now pine-hollow-commons-capture.timer
rm ~/.config/systemd/user/pine-hollow-commons-capture.timer
rm ~/.config/systemd/user/pine-hollow-commons-capture.service
systemctl --user daemon-reload
```

## Installed files

Repository implementation:

```text
commons_lab/automation.py
commons_lab/camera.py
commons_lab/ingest.py
commons_lab/pipeline.py
commons_lab/schema.py
scripts/commons_lab_cli.py
scripts/run_commons_lab_capture.py
deploy/systemd/pine-hollow-commons-capture.service
deploy/systemd/pine-hollow-commons-capture.timer
tests/test_commons_automation.py
tests/test_commons_camera.py
tests/test_commons_lab.py
```

Installed user units:

```text
~/.config/systemd/user/pine-hollow-commons-capture.service
~/.config/systemd/user/pine-hollow-commons-capture.timer
```

## Version and expansion ledger

| Version | Date | Added | Verification |
|---|---|---|---|
| v0.1 | 2026-07-14 | Additive event/evidence/assertion schema, privacy/publication guards, DirectShow bridge, one private baseline frame | Live ingest, schema checks, label audit, independent blocker reviews |
| v0.2 | 2026-07-14 | Atomic no-overwrite private capture, collision-resistant names, shared capture lock, systemd timer, run ledger, disk guard, CPU quality metrics, operational controls | Real timed capture, silent tick, real systemd service, CLI-versus-scheduler overlap, preserved-hash overwrite refusal, 25-test regression suite, blocker/high review fixes |

Add future expansions to this table when they become operational. Do not mark planned hardware as installed.

Final blocker/high re-review result: **APPROVE**. The reviewer confirmed that finalized evidence cannot be overwritten and that the shared lock covers manual and scheduled capture entry points. No blocker or high-severity issues remain; the reviewer modified no files.

## Clean expansion sequence

### v0.3 — View-specific visual baseline

Build with existing hardware:

1. Define a versioned canopy region of interest.
2. Record region geometry in deployment configuration.
3. Compute canopy-only luma, GCC, excess green, and clipping.
4. Add frame-shift/obstruction detection against a reviewed reference frame.
5. Produce a private daily camera-health summary.
6. Collect enough days to calibrate quality thresholds before changing exposure or camera position.

No GPU is required.

### v0.4 — Environmental context projection

Use existing local/website-source data without changing the website:

1. Read existing Observatory/weather cache as a source.
2. Attach nearest temperature, humidity, rain, wind, pressure, and daylight context to events.
3. Store the source timestamp and age so stale weather is visible.
4. Keep this one-way: Commons reads context; it does not alter website jobs or payloads.

No Pi changes are required.

### v0.5 — Existing archive linkage

1. Audit the 32 pre-existing orphaned `label_events → clips` references.
2. Link legacy audio clips to Commons events through `commons_legacy_links`.
3. Map BirdNET/InsectNet detections to model assertions, not reviewed truth.
4. Keep BirdNET-Pi recording and deletion behavior unchanged.

### v0.6 — Bounded local curation

Only after a useful evidence backlog exists:

1. Run image/audio embeddings in explicit batches.
2. Limit GPU jobs by duration, VRAM budget, and idle window.
3. Rank novelty, disagreement, and seasonal gaps.
4. Never run continuous high-resolution vision inference on Athena.
5. Keep training manual until resource impact is measured.

### Hardware expansion order

Purchase only when a current bottleneck is measured:

1. **Dedicated external SSD or NAS target** — when retention/backup becomes the bottleneck.
2. **UPS and power telemetry** — when continuity through outages matters.
3. **Local weather station** — when regional weather context is too coarse.
4. **Second fixed outdoor camera** — after privacy masks and camera protocol are proven.
5. **Soil/water sensors** — tied to explicit intervention/outcome questions.
6. **Jetson or another edge accelerator** — only when a stable model needs low-power continuous inference away from Athena.

The RTX 4090 remains an opportunistic curation/training resource, not a permanent background appliance.

## Explicitly deferred

- Raspberry Pi modifications;
- BirdNET lifecycle changes;
- website changes;
- public camera imagery;
- Discord delivery;
- continuous GPU inference;
- model-generated species or phenology claims;
- automatic deletion;
- purchasing hardware before a measured need.
