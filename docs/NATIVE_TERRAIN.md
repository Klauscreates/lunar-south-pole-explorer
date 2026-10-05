# Native-resolution local terrain diagnostics

Implemented 2026-10-02 as a separate backend and **Native terrain** panel.
The operational skyline remains the 10 m local / 240 m regional LOLA model;
the roughly 200 m display grid was never the scientific visibility input.
This addition is not a sub-meter landing-safety solution.

## Ingested products

| Site | Product | Native spacing | Qualification |
| --- | --- | --- | --- |
| Connecting Ridge | DLR/LROC NAC_DTM_ESALL_CR1 stereo DTM | 2 m | Confidence IMG code 14 only; shadow/interpolated/outside pixels excluded |
| Haworth | NASA Ames/USGS Lunar_LROnac_Haworth_sfs-dem_1m_v3 | 1 m | Mixed shape-from-shading and LOLA-filled areas with no per-pixel origin/error map; diagnostic only, all visibility statuses UNKNOWN |

Source URLs, methods, checksums and caveats are pinned in
`data/nac-products.json`. Native rasters and the Connecting Ridge README and
PDS confidence IMG are cached in `data/cache/nac/`. The browse confidence TIFF
is contrast-scaled and is **not** used to interpret the original categorical
confidence codes. The DLR README gives codes 0=outside, 1=shadow, 4=interpolated,
14=successful correlation. Its reported 0.5 m RMS against corrected LOLA
controls is not independent absolute accuracy. It also warns that orthophotos
may differ from the DTM by 15 m or more. No image-derived boulder coordinates
are inferred from this product.

Primary source pages:

- https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_ESALL_CR1
- https://astrogeology.usgs.gov/search/map/lunar_lro_nac_haworth_photoclinometry_dem_1m

No verified covering fine-resolution DEM is enabled for Test Site A or Nobile
Rim 1. The inspected NOBILE01 extent ends west of our Nobile coordinate.
Malapert03 is a 4 m candidate product, not ingested in this milestone. This is
a coverage-limited first integration, not an exhaustive global product search
or a claim that these are the highest resolutions obtainable by reprocessing.
In particular, 0.5 m NAC imagery is not proof of a 0.5 m DEM.

## Computation and registration

The reader preserves native spacing, scale/offset, nodata, confidence and
pixel-center registration. It requires a projected 1737400 m lunar sphere,
matching confidence grids and bounded crop sizes. No interpolation across
missing/confidence-rejected pixels is permitted. Haworth data remain unqualified
even where numerical samples exist, because fill provenance is unresolved.

The input products are already tied to LOLA by their producers. The new local
co-registration diagnostic checks projection agreement and fits bounded dx/dy/dz
translations against the current 10 m LOLA crop in a 1 km square. Alternating
100 m spatial blocks are held out from the robust fit. It reports residuals,
fit bounds and a proposed translation. Following the user's application request,
Connecting Ridge now applies the internally screened correction to its local
terrain study; Haworth's correction is rejected. Resolution
differences and shared LOLA control remain; no independent accuracy claim or
sub-meter alignment certificate follows from small residuals. Ground-control
review and resolution-matched independent checks are still needed before
claiming independently validated fusion or replacing the operational baseline.

### Applied registration and research fusion

Connecting Ridge passes the explicit engineering gate: at least 100 held-out
samples, at least 20% held-out RMS reduction, no NMAD increase, no translation
bound reached, a finite Jacobian condition number below 10,000, and qualified
fine-scale pixels. These screening thresholds are not mission qualification
criteria or confidence bounds. The correction uses
`corrected(x,y) = original(x+dx,y+dy)+dz`, with dx=+4.80624 m, dy=-0.79687 m,
dz=-0.68522 m. The affine georeferencing and elevation values change without
resampling or modifying the original source file. Unknown cells remain unknown.
Held-out RMS is 1.14243 m before and 0.43890 m after; these are correlated-data
residuals, not absolute accuracy. The corrected site elevation is 1944.92908 m.

All local roughness and near-field rays are recomputed. For the applied case,
the 10 m LOLA raster is also raycast from 500 m to 10 km and the 240 m raster
from 10 to 200 km, at each source epoch's actual azimuth and the same corrected
observer elevation. The source topocentric body vector is rebased for the
observer-height difference. The maximum across scales forms a separate research
center-LOS series. A complete scale can demonstrate blockage; clearance requires
complete coverage at every scale. No fine-data gaps are filled with coarse data.
The unresolved first native pixel remains excluded. Original LOLA gauges are
preserved as the baseline; the new fused result is in **Native terrain**.

Haworth fails both pixel-provenance qualification and the RMS-improvement gate
(0.69887 to 0.66201 m), so no correction or fusion is applied there. Sub-meter
elevation and measured-boulder inputs remain unavailable for both sites.

Near-field rays follow spherical geodesics from the native DEM observer height,
from one native pixel out to 500 m. Radial sampling at half the native spacing
interpolates the input; it does not create finer information. Rays are evaluated
at each of the 1,009 actual Sun/Earth center azimuths, avoiding additional angular
interpolation from a sparse azimuth mask. Any missing sampled support or missing
pixel qualification produces UNKNOWN, even if some measured terrain is high.
The result CLEAR_SAMPLED_LOCAL_DOMAIN is restricted to that sampled domain; it
is not full-path visibility, a communications link, or evidence that no unresolved
boulder exists. No finite solar/Earth disk treatment is added here.

Local roughness uses a fitted plane in 10, 25 and 50 m radius footprints and
reports detrended RMS, peak-to-peak residual and plane slope only when all
sampled elevations exist. These are scale-dependent terrain metrics, not
boulder counts or lander-footpad roughness. No boulders are synthesized.

## Reproduce

```bash
.venv/bin/python run_local_terrain.py --download
.venv/bin/python -m unittest discover -s tests -q
npm --prefix apps/web run build
```

Existing verified downloads are reused. Missing sources require `--download`;
changed checksums stop the run. Source products total about 593 MB of native
terrain/quality inputs. Parent LOLA crops must already be present and match the
canonical exports. Results live in `outputs/local-terrain/`. The catalogue is
published last; the web sync verifies source-manifest, implementation and parent
hashes, and the browser verifies each report hash and site lineage. No canonical
simulation/spacecraft outputs are modified.

## Verification and remaining work

131 Python tests pass, including synthetic 5 m obstruction interception,
nodata and low-confidence rejection, unknown Haworth classifications,
plane roughness, known-translation recovery/application with sign verification,
rejected-fit gates, missing-near-field fusion behavior and generated-export lineage.
Production build and ESLint pass. This validates software contracts, not
physical terrain accuracy or landing safety.

The production browser was checked at 1440 x 1000: Test Site A reports no
qualified fine product; Connecting Ridge shows native 2 m data and changes
with the main timeline; switching to Haworth retains the selected UTC epoch
and shows unknown classifications. No page errors were reported. Intercepting
the terrain catalogue with invalid data produced an explicit lineage error
instead of numerical terrain results. The temporary interception was removed.

Remaining work: additional stereo/SfS coverage, source-origin/error masks,
independent co-registration review and uncertainty propagation, independent ground truth,
per-sensor terrain heights, sampling convergence, resolved boulder geometry
and validation of the recomputed near/local/regional series before promotion into
operational baseline visibility gauges. Sub-meter post spacing alone would not close
these gaps.
# Gauge model selection

The site card offers **LOLA baseline** and **Registered NAC + LOLA — experimental**.
The latter uses checksum-verified, parent-linked, epoch-aligned registered fusion
reports only. Complete qualified multiscale coverage is required per body; missing,
incomplete, rejected, loading, or failed reports display **Unknown**, never baseline
fallback. Even a proven obstruction in an incomplete research ray is conservatively
shown as Unknown in these gauges. Sun/Earth center geometry is not full-disk
illumination: experimental electrical output and disk windows remain Unknown.
The globe, catalogue summaries, timeline strips and 360-degree chart are explicitly
baseline references. Neither model assesses landing safety or RF link quality.
The report's `operational_visibility_changed: false` describes unchanged canonical
simulation exports, not the user's selected UI gauge model.
