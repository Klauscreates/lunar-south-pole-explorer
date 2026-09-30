# Interactive 3D draft — 2026-09-29

## Run

From the repository root, first create the validated simulation using the README
instructions. Then:

```bash
cd apps/web
npm install
npm run terrain:prepare
npm run build
npm run planner -- --production
```

The planner is at `http://127.0.0.1:3000`. Its launch script also owns the read-only
Python tile service at `127.0.0.1:8766` and terminates both children on shutdown.
For a preview that remains available after the launching terminal closes, run
`npm run planner:background`; use `npm run planner:status` and
`npm run planner:stop` to inspect or stop it. The web process starts only after
the terrain service passes its local health check.
Without `--production`, the same command runs the development server. The tile
service is local only; Next.js proxies an allowlisted set of tile/inspection paths.
`npm install` copies Cesium's runtime, workers and assets into public/cesium.
No Cesium ion token or third-party map service is used at runtime.

## Architecture and data

The original science implementation and canonical simulation exports are unchanged.
The browser consumes the existing schema 1.1.0 export and requires its SPICE PASS.
CesiumJS 1.145.0 uses an explicit `(1737400, 1737400, 1737400)` metre ellipsoid;
all Cartesian conversions, terrain tiling, globe and map projection use it.

`prepare_web_terrain.py` checks the original crop hashes, converts the NASA SVS
global float DEM from kilometres to metres, retains source URLs and hashes, and
prepares server-side average LOD pyramids. It fetches small thematic windows using
HTTP range requests. Failed optional datasets are recorded as unavailable.

| Layer | Exact NASA product | Coverage in this draft |
|---|---|---|
| Global elevation | SVS CGI Moon Kit `ldem_4.tif`, LOLA, 4 px/degree | Global; ~7.58 km latitude spacing |
| Global context imagery | SVS `lroc_color_2k.jpg`, 2048×1024 | Global; contextual, not landing-scale imagery |
| Regional elevation | PGDA `LDEM_60S_240MPP_ADJ.TIF` | Retained ~401 km square crop, 240 m pixels |
| Local elevation | PGDA `LDEM_83S_10MPP_ADJ.TIF` | Retained 20.04 km square crop, 10 m pixels |
| Slope | PGDA `LDSM_80S_20MPP_ADJ.TIF` | 24 km square crop, 20 m pixels |
| Permanent shadow | PGDA `LPSR_80S_20MPP_ADJ.TIF` | Same thematic crop, nearest-neighbour categories |
| Height uncertainty | PGDA `LDEM_80S_20MPP_ADJ_ERR.TIF` | Same thematic crop, metres |
| Slope uncertainty | PGDA `LDSM_80S_20MPP_ADJ_ERR.TIF` | Same thematic crop, degrees |
| Effective resolution | PGDA `LDEM_80S_20MPP_ADJ_EFFRES.TIF` | Same thematic crop, metres |
| Measurement count | PGDA `LDEC_80S_20MPP_ADJ.TIF` | Same thematic crop, returns/pixel |

References: [NASA PGDA product 90](https://pgda.gsfc.nasa.gov/products/90),
[NASA SVS CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/), and
[Cesium terrain provider API](https://cesium.com/learn/cesiumjs/ref-doc/CustomHeightmapTerrainProvider.html).
The rendered PGDA products are in MOON_ME tied to DE421. A 10 m pixel does not
guarantee 10 m effective resolution. The inspector explicitly reports the latter
where NASA supplies it. The source-product hashes are in `/terrain/manifest.json`;
display-atlas dimensions, footprint and hashes are in `/terrain/atlas.json`.

## Streaming and performance

Geographic height tiles are generated on demand from server-side arrays. Normal
tiles have 65×65 samples (16,900 bytes). Polar tiles whose northern edge is at or
south of 80°S use 17×513 samples (34,884 bytes), allocating more samples along latitude
to avoid the excessive longitude sampling of ordinary geographic tiles near 90°S.
Leaf masks stop subdivision at source-appropriate limits (global level 5,
regional 7, local 11). Screen-space error selects actual detail; the 10 m source
is not rendered at full resolution from every camera height. Up to 12 terrain
requests run concurrently, with 350 Cesium cached tiles and a 512-entry server LRU.
The local HTTP service uses persistent connections and a 128-connection backlog.
Rapid polar zoom testing exposed connection churn with the original stdlib
backlog of five. After this correction, 256 proxied polar tile requests at
32-way concurrency returned all 256 valid tiles in 0.344 s on this machine.

Regional relief imagery is tiled. The local 10 m relief and thematic overlays use
prepared 4096×2048 polar atlases (~10.36 m latitude display spacing) to avoid
thousands of tiny polar image requests. Relief is 5.16 MB, slope 7.89 MB, PSR
0.225 MB, and height error 6.26 MB. Atlases load only when approaching the site or
enabling their layer. Raw GeoTIFFs never enter the browser. Vertical exaggeration
is 1. A narrow visual-only seam blends the DEM crop boundaries; point inspection
uses the unblended source. Fixed hillshade is for reading terrain, not sunlight.

The local CPU benchmark (`scripts/profile_web_terrain.py`, 16 cold polar tiles)
measured median generation 0.75 ms and p95 1.07 ms on this machine. Cached lookup
median was below 0.001 ms. These figures exclude network and WebGL costs.
The UI exposes pending/cumulative requests and recent rendered frames/sec. It
renders on demand and deliberately sleeps when idle; idle 0 fps is expected.
An observed development camera flight showed about 35 rendered fps at 1280×720;
this is an observation, not a sustained frame-rate guarantee or mobile benchmark.

## Scientific and visual boundaries

At 2026-10-01 00:00 UTC the Sun is at azimuth 302.828959535°, elevation
1.037972508°, and Earth at 358.807428905°, 6.492099500°. Both disks are fully
visible. The stated 1 m², 30% efficient, Sun-tracking panel yields 406.103 W.

The inspector at Test Site A reads 628.229797 m elevation, 22.3145° slope,
0.1867 m height uncertainty, 0.3854° slope uncertainty, 15.5081 m effective
resolution, 2 returns/pixel, and NOT_PSR from the separate NASA thematic products.
These thematic values have a 20 m product basis; they are not lander-footprint
hazard estimates or mission-independent safety classifications.

Sun/Earth direction vectors use the exported azimuth/elevation transformed from
local east/north/up into the lunar body frame. Markers use shortened distances
and screen-sized disks. They disappear at globe scale to avoid overlapping labels.
Clear/partial/blocked ray labels and the horizon plot follow the backend result.
The closest 0.5° skyline sample supplies obstruction distance; it is labelled as
a skyline sample, not a precisely located blocking ridge.

Optional directional WebGL lighting and shadow maps follow the computed Sun vector.
They are visual approximations with finite shadow-map coverage. Static relief
texture is still present. Backend terrain/disk calculations determine mission
visibility and power. DTE means geometric opportunity, not a radio link budget.

The clock advances simulation seconds at 1×/10×/100×/1000× and displays the nearest
preceding 10-minute sample; it does not invent interpolated science between epochs.
At 1000×, a new epoch appears about every 0.6 real seconds. At 1×, it takes 10 real
minutes. Playback stops at the evaluated endpoint. Window boundaries retain the
10-minute cadence limit.

## Scope and extension seams

Search currently resolves Test Site A and its south-pole context. Other terrain
points can be inspected, but do not receive copied Test Site A mission results.
Resource evidence is disabled with an explicit dataset-not-loaded state. PSR is
not labelled as water. `mission-domain.ts` separates future candidate coordinates,
physical search constraints, and evidence types without inventing a site score.

Before operational use: quantify DEM/skyline convergence and propagate uncertainty,
validate shadows against time-matched observations, refine event transitions,
add a radio link budget, and evaluate more sites through the backend. The current
tile service is a local prototype, not a deployed multiuser terrain platform.

## Verification

46 Python tests pass, including the 38 pre-existing scientific tests plus eight
terrain-display tests: datum preservation, positive-east projection, tile edges,
tile shapes, global unit conversion, real thematic samples, provenance, and PNG
alpha support. ESLint, TypeScript and the optimized Next.js build pass. Ruff
checks the added Python files. A fresh complete all-epoch science run retains
SPICE PASS (Sun 0.000033716634″; Earth 0.001800101545″ maximum sky differences).
Its CSV is byte-identical to the original canonical CSV:
`a16bed59fafbf305437dd7e14ed9fc70faf68905dbf4294acb7503fb77ee80c0`.
The canonical JSON remains
`ae153ca4a28bfad02ca93fd93a64ded20dfe3e735dd4602fe2e4465b6e2d8016`.

Browser evidence is retained under `docs/screenshots/draft3d/`.

The production browser at 1280×720 was checked for Moon and site rendering,
camera fly-to/low-angle presets, wheel zoom and drag pan, terrain-point inspection,
slope/PSR/height-error toggles, and optional Sun-driven lighting. Playback advanced
from sample 1 to 14, with corresponding Sun/Earth values. Home/End scrubbing,
forward/backward steps and 10×/1000× selection worked. At the final epoch both
bodies are blocked, the horizon panel shows 0% visible disks, and power is 0 W.
The final browser warning/error log was empty. Navigation requested during Cesium
startup is retained and replayed after initialization.

Screenshots:

- `01-moon-overview.png`: global view, initial epoch.
- `02-site-terrain.png`: Test Site A terrain and initial directions.
- `03-sun-earth-los.png`: low-angle terrain/direction view.
- `04-timeline-horizon.png`: final epoch, both bodies occulted.
- `05-slope-overlay.png`: NASA slope overlay with degree legend.

These are application captures, not generated concept images. Right-drag tilt is
configured through Cesium; low-angle presets were visually tested, but an automated
right-drag gesture was not available in this browser-control interface.

## Render recovery — 2026-09-29

A later narrow-viewport camera interaction reached a nonfinite Cesium camera
state. Cesium then failed while sizing its frustum-command array and stopped
rendering. The scene now checks camera vectors, geodetic position, and frustum
distances before rendering, enforces 500 m clearance above loaded terrain, and
prevents nonfinite camera altitude from entering entity positions. A fatal
renderer error recreates the scene once; a repeat failure exposes a manual
restart control.

The rebuilt production app was checked at the narrow viewport with close zoom,
further zoom attempts, and a return to the site preset. The map stayed live and
the browser reported no new renderer errors. `render-recovery.png` captures the
recovered site view.
