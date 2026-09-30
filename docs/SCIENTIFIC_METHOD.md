# Scientific method and provenance

## 1. Coordinate and frame contract

The site is expressed in lunar Mean-Earth coordinates: planetocentric latitude,
positive-east longitude, and height above a spherical reference surface of
radius 1,737,400 m.

The local topocentric frame is:

- `+Up`: normal to the reference sphere;
- `+North`: tangent toward increasing planetocentric latitude;
- `+East`: tangent toward increasing positive-east longitude;
- azimuth: clockwise from north (`0° N`, `90° E`, `180° S`, `270° W`);
- elevation: above the plane perpendicular to `+Up`.

NASA PGDA declares the terrain in `MOON_ME`, JPL DE421. JPL Horizons documents
the lunar Mean-Earth DE421 frame for user-defined lunar topocenters. Horizons'
target trajectories in this run report DE441; this does not change the lunar
site map-frame convention.

The exact pole is intentionally avoided because azimuth is singular there.

## 2. Celestial geometry and independent local validation

Operational provider: NASA/JPL Horizons observer tables.

- API: `https://ssd.jpl.nasa.gov/api/horizons.api`
- observer center: `coord@301` (user-defined site on the Moon);
- targets: `10` (Sun), `399` (Earth center, not EMB `3`);
- requested quantities: `4,13,20` (apparent azimuth/elevation, angular
  diameter, apparent range);
- apparent coordinates: `AIRLESS`, with extra precision;
- time scale: `UT`, which is UTC for dates after 1962;
- site height: LOLA elevation + observer AGL height, converted to kilometres.

Horizons apparent azimuth/elevation includes light-time, gravitational
deflection, stellar aberration, precession, and nutation. The full JSON wrapper,
text result, request parameters, live API signature, source header, retrieval
time, and SHA-256 are cached. Requests are sequential, server-side, and retried
with backoff.

Independent implementation validator: NASA/JPL NAIF SPICE through SpiceyPy.

- local routine: `azlcpo` with an `ELLIPSOID` observer surface;
- targets: `SUN` (10) and `EARTH` (399), observer center `MOON` (301);
- explicit frame: `MOON_ME_DE440_ME421` (31009), not the mutable `MOON_ME`
  alias, `MOON_PA`, or `IAU_MOON`;
- apparent correction: reception-case `CN+S` converged light time and stellar
  aberration;
- local convention: clockwise azimuth and elevation positive toward +Up;
- observer position: `georec` using positive-east longitude, planetocentric
  latitude, and LOLA elevation plus AGL height above the 1,737.4 km sphere.

The five-file kernel set is pinned by filename, HTTPS NAIF URL, byte size, and
SHA-256 in `science/ephemeris/kernels.lock.json`: `naif0012.tls`,
`pck00011.tpc`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`, and
`de440s.bsp`. Acquisition is atomic and restricted to the NAIF HTTPS origin.
Every run verifies file integrity, exact frame identity, spherical lunar radii,
SPK coverage for target and Moon, binary-PCK coverage, and endpoint frame
transforms before calculating any sample.

Horizons values remain the operational series. SPICE recomputes all 1,009
epochs independently and is used only for validation; values are never blended
or substituted into terrain visibility, power, or window calculations. The
primary comparison metric is robust local-sky angular separation computed as
`atan2(||u × v||, u · v)`, with circular azimuth differences. Range, elevation,
and angular-diameter errors are also gated. The release limits are 1 arcsec sky
separation/elevation, 1 ppm range, and 0.01 arcsec disk diameter.

Horizons reports DE441 while the compact local SPK is DE440s. Both are related
JPL ephemerides, so this is independent code execution and kernel plumbing—not
an independent astronomical theory or measurement campaign. CSPICE `CN+S`
also omits relativistic light deflection included by Horizons.

## 3. Terrain sources

NASA GSFC PGDA Product 90, *A New View of the Lunar South Pole from LOLA*:

- product page: `https://pgda.gsfc.nasa.gov/products/90`
- dataset DOI: `10.60903/gsfcpgda-lola-spole`
- near field: `LDEM_83S_10MPP_ADJ.TIF`, 10 m grid, raycast to 10 km;
- outer field: `LDEM_60S_240MPP_ADJ.TIF`, 240 m grid, raycast to 200 km.

Both are Float32 cloud-optimized GeoTIFFs in south polar stereographic
coordinates and `MOON_ME`/DE421. The pipeline accesses them through serialized
HTTP byte-range reads because concurrent ranges from the 5.1 GB 10 m COG were
observed to fail intermittently. Only target-centered source windows are
retained locally; every crop is SHA-256 verified on reuse.

The nominal 10 m posting is not a guarantee of 10 m physical resolving power.
The available LOLA count, height-error, and effective-resolution ancillary
rasters are not yet propagated into visibility uncertainty. The older 5 m
Product 81 mosaic is not used: its DEM is NaN and its return-count layer is zero
near this exact coordinate.

For a broad independent check, V1 also samples PGDA's binary
`LPSR_80S_20MPP_ADJ.TIF` permanent-shadow map at the exact site. Its value is
`0` (`NOT_PSR`), consistent with the simulation finding direct sunlight during
the requested week. This is categorical consistency, not a time-matched
illumination validation.

## 4. Terrain horizon

There are 720 geodetic rays at 0.5° azimuth spacing. Points along each ray are
generated with spherical geodesics and bilinearly sampled from the local or
outer DEM.

For surface central angle `σ = distance / R`, observer radius `rₒ`, and terrain
point radius `rₜ`, apparent elevation is:

```text
elevation = atan2(rₜ cos σ − rₒ, rₜ sin σ)
```

This is lunar-curvature-aware spherical chord geometry. The local component is
sampled every 10 m to 10 km; the outer component every 240 m to 200 km. For each
azimuth, the higher obstruction from the two profiles becomes the final
skyline. Periodic linear interpolation supplies the skyline at an object's exact
azimuth.

The 200 km radius is explicit, configurable, and not equivalent to a global
horizon proof. At 200 km, spherical curvature depresses a same-radius surface by
approximately 11.5 km, making more distant relief unlikely to dominate at this
site, but a later global/multiresolution convergence study should quantify this.

## 5. Extended-disk occultation

Center clearance is:

```text
object center elevation − interpolated terrain horizon
```

Horizons quantity 13 supplies the full equatorial angular diameter. V1 treats
each body as a circle of radius half that value. For clearance-to-radius ratio
`x` within `[-1, 1]`, the visible circular-segment fraction is:

```text
[acos(−x) + x sqrt(1 − x²)] / π
```

Ratios below `−1` are blocked; above `+1` are fully visible. This assumes the
skyline is locally straight across the small disk. Earth oblateness, limb
position angle, Sun limb darkening, and sub-azimuth skyline variation across a
disk are not yet modeled.

## 6. Power model

The direct irradiance model uses 1,361 W/m² at exactly 1 AU and scales with the
inverse square of the live Horizons Sun range. Estimated electrical output is:

```text
irradiance × panel area × incidence cosine × visible disk fraction × efficiency
```

`sun_tracking` uses cosine 1. `horizontal_fixed` uses `max(0, sin elevation)`.
`custom_normal` takes an East/North/Up normal and dots it with the local Sun
unit vector.

This excludes temperature, degradation, dust, wiring/conversion losses,
batteries, and loads. It is an availability estimate, not certified spacecraft
power engineering.

## 7. Operations windows

Any nonzero visible fraction counts as geometric availability. Runs are
extracted from the fixed time grid using left-closed intervals: each sample's
state applies until the next sample. The final epoch has no duration beyond the
requested stop time. Transition precision is therefore bounded by the step,
10 minutes in the default run.

Earth availability is labeled **Geometric DTE Visibility**. It does not model
antenna patterns, pointing, transmitter power, frequency, propagation loss,
Earth ground stations, schedules, or operational constraints.

## 8. What is scientifically accurate now

- real NASA/JPL apparent lunar-topocentric Sun and Earth geometry;
- all-epoch independent local SPICE implementation validation with pinned
  kernels, coverage checks, and quantitative error gates;
- correct terrain-relative observer altitude rather than treating AGL as datum
  height;
- real, checksum-retained NASA LOLA terrain at two spatial scales;
- curvature-aware 360° horizon raycasting;
- partial/full/blocked extended-disk classifications;
- configurable panel orientation and range-scaled solar flux;
- deterministic window extraction, JSON/CSV export, and full provenance.

## 9. Deliberate V1 limits

- Horizons and local SPICE share JPL ephemeris lineage; the cross-check is an
  independent implementation path, not statistically independent source data.
- The compact DE440s validator is not byte-identical to Horizons' DE441 source,
  and SPICE `CN+S` omits relativistic light deflection; both differences are
  preserved in provenance rather than hidden.
- DEM height/error/effective-resolution layers are not propagated to confidence
  bounds.
- Search-radius and azimuth/radial-grid convergence are documented but not yet
  exhaustively quantified.
- No slope-derived site normal, local surface hazards, thermal model, radio link
  budget, or ground-station schedule.

## 10. Site B path

The science engine is already site-configurable. The correct next step is not a
second hard-coded page: add a batch orchestrator keyed by site/time/panel config,
run each site through the same immutable provider and terrain contracts, and
compare normalized metrics with provenance-equivalent inputs. Before ranking
sites, add uncertainty bands from the LOLA error/effective-resolution products
and batch the now-active SPICE/Horizons cross-provider gate across every site.
