# Earlier prototype notes (historical)

These earlier milestone notes are preserved for context. Use the root README and RELEASE_ACCEPTANCE.md for current setup and coverage; screenshots and numerical summaries below may be historical.

A scientifically traceable comparative prototype for one neutral validation
coordinate and four NASA-published lunar south-pole region reference points. It combines
NASA/JPL Horizons operational celestial geometry, an independent local
NASA/JPL NAIF SPICE implementation cross-check, and NASA GSFC PGDA/LOLA terrain
to answer, over a configurable time range:

- where the Sun and Earth appear in the local lunar sky;
- whether the real terrain skyline fully or partially blocks either disk;
- continuous direct-sunlight and geometric direct-to-Earth (DTE) windows;
- simultaneous sunlight + DTE availability;
- a per-epoch, center-line-of-sight communications screening index; and
- first-order direct solar input for configurable panel geometry.

The default reproducible run is Test Site A at `-89.9°`, `0° E`, with a 2 m
observer, from `2026-10-01T00:00:00Z` through `2026-10-08T00:00:00Z` at a
10-minute cadence. Each candidate uses that same interval and observer height.
The pipeline never substitutes synthetic science data when NASA/JPL sources fail.

NASA's [2025 Lunar Surface Data Book](https://ntrs.nasa.gov/api/citations/20250002845/downloads/M2M-30044%20Lunar%20Surface%20Data%20Book%20Baseline_Final.pdf?attachment=true)
supplies original DEM-polygon-center coordinates for Connecting Ridge,
Haworth, Malapert Massif, and Nobile Rim 1. These are reproducible **reference
points**, not approved landing spots or landing-safety assessments. Connecting
Ridge is in NASA's historical 2022 thirteen-region list; the other three are
in the [later nine-region Artemis cohort](https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/).

![Interactive lunar mission planner with real LOLA terrain](docs/screenshots/draft3d/02-site-terrain.png)

The interactive Cesium first draft adds a lunar globe, streamed terrain, NASA slope
and PSR overlays, point inspection, and time-synchronized mission geometry.
See [visual draft implementation and verification](docs/VISUAL_DRAFT.md).
The [candidate-array report](docs/CANDIDATE_ARRAY_2026-09-30.md) records the
five point outputs, site provenance, and model limits.

## Verified default result

The completed run contains 1,009 inclusive epochs, 720 horizon azimuth rays,
and a 360-ray, 1° mask selected from those actual DEM raycasts.
Every epoch is independently recomputed with the pinned local SPICE kernel set.
Maximum local-sky vector separation is **0.000033717 arcsec for the Sun** and
**0.001800102 arcsec for Earth**, both far inside the 1 arcsec release gate.
At the first epoch:

| Quantity | Sun | Earth |
|---|---:|---:|
| Apparent azimuth | 302.828959535° | 358.807428905° |
| Apparent elevation | 1.037972508° | 6.492099500° |
| Terrain horizon | -0.902556405° | 0.081940887° |
| Center clearance | +1.940528913° | +6.410158613° |
| Visible fraction | 100% | 100% |

Site elevation from the 10 m LOLA crop is 628.229797 m above the 1,737.4 km
reference sphere. The 2 m AGL observer is therefore sent to Horizons at
0.630229797 km above that same sphere.

Seven-day grid-resolved results:

- any direct sunlight: **68.5516%** / **115.1667 h**;
- geometric DTE: **91.8651%** / **154.3333 h**;
- both simultaneously: **68.5516%** / **115.1667 h**;
- longest terrain-shadow period: **52.8333 h**;
- longest DTE terrain blackout: **13.6667 h**.

Transitions use left-closed 10-minute sample intervals and therefore carry a
10-minute time-grid bound. This is geometric opportunity analysis, not a radio
link budget or a flight-qualified power analysis.

The interactive comms gauge reads each epoch's exported Horizons Earth
elevation and interpolated LOLA skyline. It maps a terrain-blocked Earth
*center* to index 0, a clear center at no more than 2° absolute elevation to 30,
and a clear center above 2° to 100. These user-specified numbers are
**illustrative screening categories, not measured signal percentages or
link reliability**. The existing DTE windows count any exposed part of Earth's
apparent disk, so an exposed limb can coexist with a center-blocked index 0.
See [the scientific method](docs/SCIENTIFIC_METHOD.md) for that distinction.

## Run the science pipeline

Python 3.10+ and `uv` are recommended:

```bash
uv venv
uv pip install -e '.[dev]'

.venv/bin/python run_simulation.py \
  --lat -89.9 \
  --lon 0 \
  --observer-height-m 2 \
  --start 2026-10-01T00:00:00Z \
  --end 2026-10-08T00:00:00Z \
  --step-minutes 10
```

The first run reads only two server-side COG windows, then caches their local
lossless crops, checksums, horizon profiles, raw Horizons responses, and exact
request parameters. It also downloads the five locked NAIF kernels into
`data/kernels`, rejects any byte-size or SHA-256 mismatch, verifies SPK/PCK time
coverage, and computes the SPICE comparison locally. Repeat runs are
offline-reproducible from those caches.

The locked kernel set can be fetched or verified separately:

```bash
.venv/bin/python -m science.ephemeris.kernels data/kernels
.venv/bin/python -m science.ephemeris.kernels data/kernels --verify-only
```

Observer heights of 0, 2, 5, or 10 m—and other non-negative values—are supported
through `--observer-height-m`. Panel modes are `sun_tracking`,
`horizontal_fixed`, `custom_normal` (`--panel-normal-enu E N U`), `fixed_tilt`
(`--panel-tilt-deg`, `--panel-azimuth-deg`), and `gimbal_limited`
(`--gimbal-tilt-min-deg`, `--gimbal-tilt-max-deg`,
`--gimbal-azimuth-center-deg`, `--gimbal-azimuth-half-range-deg`).
Tilt is the panel-plane inclination from local horizontal; azimuth points the
collecting face's outward normal clockwise from north.

To precompute the complete candidate array through the same live/cache-backed
LOLA, Horizons, and local SPICE pipeline:

```bash
.venv/bin/python run_candidate_array.py
```

The index is published only when every site passes its source and independent
SPICE validation. It links each retained 1,009-epoch JSON result by SHA-256.

Outputs:

- `outputs/simulation.json`: full provenance, assumptions, skyline, samples,
  windows, and validation record;
- `outputs/simulation.csv`: flat per-epoch operations table;
- `outputs/candidates/*.json`/`*.csv`: one fully validated export per NASA
  reference point;
- `outputs/simulation-index.json`: the five-site catalogue, source roles,
  provenance links, summary windows, and hashes;
- `apps/web/public/data/`: copies consumed by the local UI.

## Run the web application

```bash
cd apps/web
npm install
npm run terrain:prepare
npm run planner
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The Cesium Moon streams
real LOLA relief and connects site-specific Sun/Earth direction markers to each
validated simulation. NASA slope, PSR and uncertainty visual overlays remain
local to Test Site A; a candidate's **backend** horizon still uses its own
10 m local and 240 m outer LOLA crops. Click a site marker, scrub time, or open
the horizon and methodology panels.

`npm run planner` starts Next.js and the local read-only terrain service on
127.0.0.1:8766. For production, run `npm run build` followed by
`npm run planner -- --production`. No Cesium ion token is needed.

To leave the production preview running after closing the launching terminal:

```bash
npm run planner:background
npm run planner:status
# When finished:
npm run planner:stop
```

The background command waits until both the page and terrain proxy respond.
Its log and PID are under the ignored `apps/web/.runtime/` directory. It stays
running until stopped or the Mac session ends; rerun the command after a restart.
See [3D draft architecture and limitations](docs/VISUAL_DRAFT.md).

![Terrain-shadow state](docs/screenshots/dashboard-shadow-state.jpg)

![Expanded Horizons, SPICE, and LOLA provenance](docs/screenshots/dashboard-spice-provenance.jpg)

## Test and verify

```bash
python3 -m unittest discover -s tests -v
cd apps/web
npm run lint
npm run build
```

The verification suite includes provider, frame, coverage, corrupt-kernel,
secure-download, all-epoch comparison, terrain, visibility, power, export, and
window tests, plus ESLint, a Next.js production build, and an interactive
browser check. Details are in [docs/VALIDATION.md](docs/VALIDATION.md).

## Architecture

```text
NASA PGDA 10 m COG ── crop 10 km ── spherical raycast ─┐
                                                       ├─ maximum skyline
NASA PGDA 240 m COG ─ crop 200 km ─ spherical raycast ─┘
                                                               │
NASA/JPL Horizons (Sun + Earth lunar topocenter) ───────────────┤
                                                               ▼
extended-disk occultation → panel model → window extraction
                                │
                                ├─ JSON / CSV
                                └─ Next.js interactive dashboard

Pinned NAIF DE440s + lunar PCK/FK ─ local SPICE az/el/range ─┐
NASA/JPL Horizons DE441 observer rows ────────────────────────┴─ all-epoch error gate
```

The ephemeris layer implements two `EphemerisProvider` backends. Horizons is the
operational source driving the displayed simulation. SPICE is deliberately kept
validation-only: its values are never substituted, blended, or averaged into
the terrain visibility, power, or window outputs.

For equations, frame conventions, exact datasets, assumptions, and known
limits, see [docs/SCIENTIFIC_METHOD.md](docs/SCIENTIFIC_METHOD.md). For the
opt-in spacecraft self-shadow/thermal model and its strict vehicle-data and
certification limits, see [docs/SPACECRAFT_MODEL.md](docs/SPACECRAFT_MODEL.md).

Open **Spacecraft lab** for the five-site reference lander design study:
mesh self-occlusion, five body poses, two assumed thermal environments, and
timeline-linked power/temperature/visibility. Surveyor VII archival evidence
is presented separately, not as validation of this design. See
[the reference lander guide](docs/REFERENCE_LANDER.md) for reproducibility
and the remaining physical-validation limits.

To inspect sourced candidate-cell properties, remaining assembly assumptions,
and temperature-range coverage, run `.venv/bin/python audit_reference_inputs.py`.
This read-only audit does not promote cell datasheet values into the panel model.

Open **Native terrain** for source-pinned 2 m Connecting Ridge stereo and
1 m Haworth shape-from-shading diagnostics, local roughness and exact-epoch
near-field rays. Coverage/quality failures remain unknown, not safe or clear.
See [native terrain methodology and limits](docs/NATIVE_TERRAIN.md).
