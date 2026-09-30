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

## Remaining validation milestones

### Interactive draft verification — 2026-09-29

The 3D interface preserves the canonical simulation JSON and CSV byte for byte.
The expanded suite passes 46 tests (38 existing scientific tests and eight display
terrain tests). Production TypeScript/build, ESLint, and new Python Ruff checks
pass. A fresh all-epoch SPICE comparison still passes. Browser interactions,
streaming stress results, limitations, and actual screenshots are recorded in
[VISUAL_DRAFT.md](VISUAL_DRAFT.md).

Quantify terrain-grid/search-radius convergence; propagate PGDA height-error,
effective-resolution, and LOLA return-count uncertainty into visibility-window
bounds; and repeat the same immutable Horizons/SPICE/LOLA contract across Site B
before introducing comparative landing-site rankings.
