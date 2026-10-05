# NASA south-pole reference-point array — 2026-09-30

The planner now evaluates one neutral pipeline coordinate and four
NASA-published lunar south-pole region reference points over the same
`2026-10-01T00:00Z`–`2026-10-08T00:00Z` interval at 10-minute cadence, with a
2 m-above-terrain observer. These are **point calculations, not region-wide
lighting claims or landing recommendations**.

## Coordinate provenance

NASA's [Lunar Surface Data Book, Baseline (2025), Table A2.1-1](https://ntrs.nasa.gov/api/citations/20250002845/downloads/M2M-30044%20Lunar%20Surface%20Data%20Book%20Baseline_Final.pdf?attachment=true)
publishes the DEM-derived centers of original site polygons. The book gives
5–10 m coordinate accuracy for those centers; this does not establish safe
terrain, a certified touchdown spot, or membership in later revised boundaries.
Signed longitude below is east-positive. NASA's [2024 nine-region update](https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/)
names Haworth, Malapert Massif, and Nobile Rim 1; NASA's [Artemis IV page](https://www.nasa.gov/mission/artemis-iv/)
now frames the nine as Artemis campaign candidates. [Connecting Ridge](https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/)
is retained as a clearly historical 2022 candidate, not mislabeled as a member
of that later cohort.

| Evaluated point | Latitude | East longitude | NASA region status |
|---|---:|---:|---|
| Test Site A | −89.9000° | 0.0000° | Neutral pipeline-validation coordinate |
| Connecting Ridge | −89.4632° | −137.4900° | Historical 2022 cohort |
| Haworth | −86.7639° | −22.7770° | Later nine-region cohort |
| Malapert Massif | −85.9948° | −0.23578° | Later nine-region cohort |
| Nobile Rim 1 | −85.4381° | +37.36667° | Later nine-region cohort |

## Verified seven-day point outputs

These percentages come from the 1,009 retained Horizons epochs and each
point's own LOLA skyline, not a copied Test Site A trajectory. The 10-minute
grid bounds window transitions. Every site has 720 geodesic skyline rays
(0.5°) and an exported mask of 360 original integer-azimuth rays (1°).

| Point | Any direct Sun | Geometric direct-to-Earth | Max Horizons–SPICE Sun / Earth sky separation |
|---|---:|---:|---:|
| Test Site A | 68.5516% | 91.8651% | 0.000034″ / 0.001800″ |
| Connecting Ridge | 56.1508% | 86.5079% | 0.000034″ / 0.001800″ |
| Haworth | 63.9881% | 76.0913% | 0.000034″ / 0.001800″ |
| Malapert Massif | 0.0000% | 86.1111% | 0.000034″ / 0.001800″ |
| Nobile Rim 1 | 0.0000% | 55.8532% | 0.000034″ / 0.001800″ |

Malapert and Nobile's zero direct Sun is **only** for these polygon-center
points during this particular week. The separate NASA PGDA PSR map labels all
five points `NOT_PSR`; a non-PSR point can still be dark for this one week.
Neither result should be extrapolated across a whole named region or season.

## Orientation-sensitive power, not flight power

At Test Site A's first epoch, the 1 m², 30%-efficient ideal tracking reference
is 406.103 W. With the **same** area and cell efficiency, the north-facing
fixed vertical panel yields 220.126 W; a fixed 80° panel yields 218.059 W;
and the illustrative limited gimbal yields 401.145 W. These differences are
the actual geometric cosine losses of the configured normals relative to the
Horizons Sun vector, then multiplied by terrain-visible disk fraction. The
scenarios are not identified with any real lander hardware; thermal, dust,
self-shadowing, wiring, battery, and load losses remain outside this model.

## Per-epoch communications screen added 2026-10-01

Every retained epoch now also contains a center-based `comms_potential`
classification derived from its own Horizons Earth elevation and interpolated
LOLA terrain skyline. Index 0 means the Earth *center* does not clear the
terrain; 30 means it clears but is at or below 2° absolute elevation; 100
means it clears and is above 2°. These are user-specified visualization
categories, **not** measured signal percentages. The existing disk-aware DTE
windows remain unchanged and can report an exposed Earth limb while the new
center-based index is zero. See [the scientific method](SCIENTIFIC_METHOD.md)
for the exact boundary and limitations.

## Rebuild and verify

```bash
.venv/bin/python run_candidate_array.py
.venv/bin/python -m unittest discover -s tests -v
cd apps/web
npm run build
npm run lint
```

`outputs/simulation-index.json` is the retained five-site catalogue. Its
entries link complete per-site JSON files and contain SHA-256 hashes; the web
app verifies each file before accepting it. `npm run build` and the planner
startup sync only hash-matching canonical exports into `apps/web/public/data`.
`run_candidate_array.py` fails closed when any upstream terrain, Horizons,
SPICE, or validation dependency fails; it does not fill a failed site with
interpolated or synthetic mission data.

The web globe's 10 m local visual terrain and 20 m thematic overlays still
cover Test Site A. Candidate *backend* horizons use their own 10 m local and
240 m outer LOLA crops, but candidate viewer detail is the 240 m regional
layer. A flight-grade decision still needs per-site terrain uncertainty,
grid-radius convergence, illumination observations, slope/hazard maps,
hardware-specific power and direct-to-Earth link analysis.
