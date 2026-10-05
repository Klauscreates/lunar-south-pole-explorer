# Validation report

Run date: 2026-09-28 UTC  
Default interval: 2026-10-01 00:00 UTC – 2026-10-08 00:00 UTC  
Cadence: 10 minutes, inclusive endpoints

## Result

`PASS`. NASA/JPL Horizons remains the operational series, while a pinned local
NAIF SPICE provider independently recomputes and compares every requested epoch.

## Automated checks

- 38/38 Python unit and artifact-integration tests pass.
- a `+45°` east-longitude canary matches independently retained Horizons Sun
  and Earth values and verifies the body-fixed observer has positive, equal
  X/Y coordinates; an east/west sign reversal misses the azimuths by about 90°.
- canonical hashes prove the validator-enabled export preserves the pre-SPICE
  Horizons-derived sample series, window summary, and CSV bytes exactly.
- 1,009 expected Sun rows and 1,009 expected Earth rows parsed.
- first and last timestamps match the request; maximum cadence-grid error: 0 s.
- every exported azimuth, elevation, horizon, clearance, and fraction is finite.
- all four combined-state durations sum to exactly 604,800 s (seven days).
- 720 finite horizon azimuths match the configured 0.5° grid.
- local and outer crop SHA-256 hashes are retained and checked before cache use.
- all 1,009 Sun and Earth samples independently recomputed with local SPICE;
- maximum Horizons/SPICE local-sky separation: Sun 0.000033717 arcsec;
- maximum Horizons/SPICE local-sky separation: Earth 0.001800102 arcsec;
- maximum range error: Sun 0.007388 km / 0.0000494 ppm;
- maximum range error: Earth 0.0000813 km / 0.0002147 ppm;
- maximum angular-diameter error: Sun 0.000500 arcsec;
- maximum angular-diameter error: Earth 0.000500 arcsec;
- all SPICE metrics pass the 1 arcsec position/elevation, 1 ppm range, and
  0.01 arcsec angular-diameter release gates;
- all five local NAIF kernels match their locked byte sizes and SHA-256 hashes;
- DE440s SPK and lunar binary-PCK coverage contain the complete requested run;
- published NASA PGDA 20 m PSR map value at the site: `0` (`NOT_PSR`),
  consistent with direct sunlight found during the requested interval.
- Next.js TypeScript production build succeeds.
- ESLint reports no errors or warnings.
- browser verification: meaningful content rendered, time slider updates the Sun,
  Earth, terrain, visibility, timeline cursor, and power state; provenance panel
  expands; no console warnings/errors and no Next.js error overlay.

The local SPICE provider independently computes topocentric azimuth, elevation,
apparent range, and disk diameter. Disk size is reconstructed as:

```text
2 × asin(physical equatorial radius / apparent SPICE range)
```

and compared with Horizons quantity 13. Sky-vector separation uses
`atan2(||u × v||, u · v)` for precision at sub-milliarcsecond residuals, and
azimuth errors are circular across north.

## Reference epochs retained in the result

The JSON validation record stores the first, middle, and final Horizons samples
for both targets. The first final-pipeline epoch (observer height includes the
10 m DEM elevation) is:

```text
2026-10-01T00:00:00Z
Sun   az 302.828959535°  el 1.037972508°
Earth az 358.807428905°  el 6.492099500°

Local SPICE at the same epoch and physical observer point:

Sun   az 302.828959528°  el 1.037972508°
Earth az 358.807428664°  el 6.492099487°
```

These differ slightly in elevation from a reference-sphere-only 2 m test because
the final site altitude is 628.229797 m terrain + 2 m AGL, not 2 m above the
reference sphere.

## Visual evidence

- [Initial visible Sun + Earth state](screenshots/dashboard-initial.jpg)
- [Current SPICE-validated dashboard](screenshots/dashboard-spice.jpg)
- [Expanded Horizons/SPICE/LOLA provenance](screenshots/dashboard-spice-provenance.jpg)
- [Later terrain-shadow state with zero panel output](screenshots/dashboard-shadow-state.jpg)

## Later validation milestones

### Opt-in spacecraft geometry and thermal kernel — 2026-10-01

The baseline candidate exports and UI power gauges remain unchanged. A
separate, checksum-pinned hardware runner now validates OBJ/STL geometry,
body-to-ENU yaw/pitch/roll, weighted panel self-shadow rays, antenna
Earth-center self-LOS, explicit wall-reflected/IR boundary inputs, and a
time-stepped temperature-dependent PV model. A separate Lambertian
crater-wall facet helper produces panel-plane reflected flux only when the
caller supplies facet geometry, broadband reflectance, and illumination.
No VIPER flight CAD or site radiometry was supplied or inferred.

The Python suite passes 114 tests. Synthetic analytic cases cover ray
occlusion, attitude, wall view factors, thermal energy closure, tampered
hashes, missing boundaries, output-path protection, and atomic-export temp-file
collisions. One regression drives
all 1,009 **real Test Site A Horizons/SPICE/LOLA epochs** through temporary
**synthetic vehicle inputs**; it revealed and then guarded a near-equilibrium
thermal root-precision error. The test creates no persistent vehicle output.
The integrated result remains `CONFIGURED_UNVALIDATED`, with
`flight_certified: false`; it does not independently authenticate the parent
source labels or replace flight thermal-vac correlation.

### Center-LOS comms screen — 2026-10-01

All five canonical candidate exports were regenerated at schema 1.3.0. The
array validator recomputes the center-LOS classification from each epoch's
Earth elevation and LOLA skyline and rejects any mismatch. All 5,045 epochs
match; 68 Python tests pass. Next.js production build, TypeScript, and ESLint
pass. In the live browser, the Test Site A gauge showed index 100 at sample 0,
30 at sample 670, and 0 at sample 834. At sample 834 it displayed the exposed
Earth limb (49.8%) separately from the terrain-blocked Earth center. Switching
sites preserved the UTC epoch and loaded the candidate's own classification;
browser warnings/errors were absent. The numbers are an illustrative
geometric index, not validated RF signal percentages or link reliability.

### Native local terrain diagnostics — 2026-10-02

Application revision: 131 Python tests, ESLint and production build pass.
Connecting Ridge's internally screened translation is now applied; corrected
near-field terrain, observer elevation, roughness and regional rays are rebuilt
as a research fusion series. Haworth's application gates reject its correction.
Known-transform application/sign and missing-data fusion tests pass. This
supersedes the initial non-applied registration state described below; the
operational baseline remains unchanged and independent validation is pending.
Production-browser checks confirmed the applied Connecting Ridge fusion values,
timeline stepping and Haworth's rejected-application state. No page errors were
reported. The largest sampled Connecting Ridge Earth near-field skyline change
from registration is approximately 0.478 degrees over this evaluated week.

129 Python tests, ESLint and the production build pass. Native 2 m Connecting
Ridge stereo and 1 m Haworth SfS products are pinned and ingested with local
roughness, exact-epoch center rays and a non-applied registration diagnostic.
Confidence gaps are unknown; Haworth classifications remain unknown because
its fine-scale pixel provenance is unresolved. Production-browser site/time
switching and invalid-catalogue failure behavior were checked. Operational
LOLA results remain unchanged. See [NATIVE_TERRAIN.md](NATIVE_TERRAIN.md) for
coverage, reproducibility and limits; no sub-meter safety claim is made.

### Reference lander study — 2026-10-01

The separate Spacecraft lab evaluates project-defined R1 geometry over all five
site exports: five attitudes, two assumed environmental cases and 1,009 epochs
per case (50,450 scenario epochs). All 117 Python tests, ESLint, production
TypeScript/build and `git diff --check` pass. Tests cover analytic structural
shadow, thermal energy closure, all exported rows and parent/design/kernel
hash lineage. See [REFERENCE_LANDER.md](REFERENCE_LANDER.md).

Production-browser verification exercised attitude/environment selection,
timeline stepping, site switching, and the Surveyor VII evidence disclosure.
Haworth at 2026-10-01 00:10 UTC displayed the exported north/low-load values:
259.5 W and -18.6°C. Switching sites retained the timeline epoch and reset the
study controls to their declared defaults. No page errors were reported.
An intercepted invalid spacecraft catalogue produced a visible lineage error
and no numerical vehicle results; no fallback data were substituted. The
final production build was restarted and the lab loaded successfully.

These are software checks, not hardware validation. Thermal properties and
site radiometry remain assumed; Surveyor VII records are separately sourced
archival observations, with model correlation explicitly NOT_RUN.

### Five-point comparative run — 2026-09-30

The current array adds four NASA-published region reference points and retains
the Test Site A canary. All five have 1,009 Horizons Sun/Earth epochs, a
site-specific 720-ray merged LOLA skyline, a 360-ray mask using exact
integer-azimuth DEM rays, and all-epoch local SPICE PASS. The JSON index
contains per-file SHA-256 values, and the UI verifies those before loading a
point. Four orientation scenarios expose incidence cosine and pointing-limit
losses without claiming flight-hardware fidelity. The project suite now passes
63 Python tests; the Next.js production build and ESLint also pass. See
[the candidate-array report](CANDIDATE_ARRAY_2026-09-30.md) for the values and
reference-point caveats.

Remaining science work is DEM uncertainty/convergence, time-matched shadow
validation, hardware power losses, and a DTE radio link budget. No region
ranking or touchdown safety determination has been made.

### Interactive draft verification — 2026-09-29

The 3D interface preserves the canonical simulation JSON and CSV byte for byte.
The expanded suite passes 46 tests (38 existing scientific tests and eight display
terrain tests). Production TypeScript/build, ESLint, and new Python Ruff checks
pass. A fresh all-epoch SPICE comparison still passes. Browser interactions,
streaming stress results, limitations, and actual screenshots are recorded in
[VISUAL_DRAFT.md](VISUAL_DRAFT.md).

The five-point array now repeats the Horizons/SPICE/LOLA contract across the
four NASA-reference candidate points. Before introducing comparative
landing-site rankings, quantify terrain-grid/search-radius convergence and
propagate PGDA height-error, effective-resolution, and LOLA return-count
uncertainty into visibility-window bounds.
