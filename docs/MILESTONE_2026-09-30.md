# Lunar mission planner milestone — 2026-09-30

## Saved state

This is the first Git baseline for the science pipeline and interactive 3D
prototype. The repository commit contains code, configuration, tests, method
documentation, screenshots, and the canonical simulation JSON and CSV.

The source checkout alone does not contain the large NASA inputs or generated
browser terrain. Those are saved separately at
`milestones/2026-09-30-lunar-planner-data.tar.gz` (133 MiB). This archive is
intentionally Git-ignored so the initial source commit stays manageable.
Its SHA-256 is:

```text
ab0bc6f670d5dd79bf6623224aed6fe1a4b9ec47efc51d3e062067c2496ae0cc
```

The archive contains 67 entries under `data/kernels`, `data/cache`,
`data/processed`, `data/web_terrain`, `apps/web/public/terrain`,
`apps/web/public/data`, and `outputs`. It includes the exact cached Horizons
responses, NAIF kernels, LOLA source crops, web display rasters and canonical
simulation files. `node_modules`, `.venv`, Next build files, and the background
service PID/log are generated runtime state and are not included.

Check the archive before restoring it into a clean checkout:

```bash
shasum -a 256 milestones/2026-09-30-lunar-planner-data.tar.gz
tar -tzf milestones/2026-09-30-lunar-planner-data.tar.gz
```

Extract only into a fresh checkout, because extraction replaces files with
matching names:

```bash
tar -xzf milestones/2026-09-30-lunar-planner-data.tar.gz
uv venv
uv pip install -e '.[dev]'
cd apps/web
npm ci
npm run build
npm run planner:background
```

The canonical simulation hashes are:

```text
JSON ae153ca4a28bfad02ca93fd93a64ded20dfe3e735dd4602fe2e4465b6e2d8016
CSV  a16bed59fafbf305437dd7e14ed9fc70faf68905dbf4294acb7503fb77ee80c0
```

## Working capabilities

- Site A at 89.9°S, 0°E, 2 m above a real LOLA elevation is evaluated for
  October 1–8, 2026, at 1,009 ten-minute epochs.
- JPL Horizons apparent Sun/Earth azimuth, elevation, apparent range and disk
  size drive the mission states. Local NAIF SPICE recomputes every epoch as an
  independent implementation check; the result passes its quantitative gates.
- NASA PGDA 10 m local and 240 m outer DEMs produce a 720-ray, curvature-aware
  skyline to 200 km. Extended-disk visibility, idealized solar input and
  sunlight/geometric direct-to-Earth windows follow from that skyline.
- The Cesium browser uses a 1,737.4 km lunar reference sphere, NASA LOLA relief
  at global/regional/local detail, LROC global context imagery, 20 m NASA slope,
  PSR and height-error overlays, and real point inspection metadata.
- Camera presets, pan/zoom/tilt controls, site inspection, the horizon panel,
  ten-minute stepping, time scrubbing and playback are interactive. A local tile
  service streams data to the browser. The background launcher checks service
  readiness and supports start/status/stop.

## Representations, assumptions and missing work

There are no synthetic orbit or terrain samples in the evaluated Site A run.
Nevertheless, several displays and models are simplified:

- Test Site A is a neutral pipeline-validation coordinate, not a selected or
  approved landing site. Search currently returns only this evaluated site.
  Clicking other ground points inspects terrain but does not evaluate their
  Sun/Earth windows.
- Sun/Earth map markers have screen-sized disks and shortened direction rays.
  They indicate bearing/state; their drawn distance and size are not physical.
- Fixed DEM hillshade and optional time-varying WebGL lighting/shadows are
  visual aids. The backend skyline/disk calculation determines mission states.
  Neither visual effect is an observed, time-matched lunar illumination map.
- The 1 m², 30% efficient Sun-tracking panel is a declared scenario assumption.
  The power estimate omits temperature, batteries, dust, losses and loads.
- Direct-to-Earth means geometric visibility only. Antennas, radio propagation,
  ground stations and schedules are not modeled.
- PSR is a real NASA classification, but water/ice or other resource evidence
  has not been loaded. The resource layer is explicitly disabled.
- Nominal 10 m or 20 m pixel spacing is not guaranteed resolving power.
  Height/slope uncertainty, effective resolution and measurement count are
  displayed but not yet propagated into window confidence bounds.
- Visibility transitions are resolved only to the ten-minute simulation grid.
  The horizon ray step, 200 km search limit and disk approximation still need
  convergence and uncertainty studies for mission use.
- High-resolution terrain is a bounded local patch. The full Moon is shown at
  coarser resolution. This prototype has no multi-site ranking or operational
  landing-hazard assessment.

## Verification at checkpoint

The canonical JSON and CSV hashes above were checked against the copies used
by the browser. The science/terrain suite passed 46 tests. See
`docs/VALIDATION.md`, `docs/SCIENTIFIC_METHOD.md` and `docs/VISUAL_DRAFT.md` for
the detailed gates and visual evidence.
