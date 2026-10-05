# Spacecraft-specific self-shadow and thermal analysis

This is an **opt-in engineering prototype**, separate from the five-site
Horizons/SPICE/LOLA baseline. The baseline describes the sky and terrain at a
surface coordinate; it does not identify a lander or rover. Spacecraft-specific
results require a separately supplied, versioned vehicle configuration. A CAD
mesh is useful for geometric screening, but importing one does not make the
output flight-certified.

## Vehicle identity and evidence boundary

NASA describes VIPER as a four-wheel lunar south-pole rover with independently
oriented mobility, solar charging, and X-band direct-to-Earth communications.
Its public [rover and instruments page](https://science.nasa.gov/mission/viper/rover-and-instruments/)
and [technical briefing](https://assets.science.nasa.gov/content/dam/science/psd/lunar-science/documents/2025-02-13_VIPER_Updated_Technical_Briefing_Presentation-Shared.pdf)
provide selected dimensions and subsystem facts, **not** a complete,
configuration-controlled flight CAD assembly with sensor, panel, articulation,
and thermal properties. No VIPER flight CAD is included in this repository.

The browser-navigable [JPL Open Source Rover Onshape model](https://github.com/nasa-jpl/open-source-rover#online-3d-model)
belongs to JPL's build-it-yourself, Mars-inspired educational rover. **It is
not VIPER.** It can support a clearly labeled geometry demonstration, but
substituting it for VIPER would invalidate vehicle-specific self-blocking,
panel-power, and antenna-visibility claims. A third-party visualization or an
Apollo/Orion mesh is likewise not VIPER flight hardware.

## Required inputs and provenance

Each run binds a supplied configuration to one site/time simulation; no
missing physical parameter should silently inherit a VIPER-like value. A
**vehicle-specific flight interpretation** would also require the evidence
below. Some of it, such as time-varying articulation and a measured antenna
pattern, is outside the current static-mesh model even if the runner accepts
all of its own required fields:

| Input | Minimum evidence needed | Why it matters |
|---|---|---|
| Mesh assembly | Source URL or controlled release ID, license, SHA-256 of every mesh, units, body axes, component IDs, watertightness/repair log | Prevents a visually plausible but incorrectly scaled or oriented proxy from being treated as hardware. |
| Vehicle pose | Landing/rover position, body heading, roll, pitch, local surface normal, articulation state for each moving array/mast/antenna, uncertainties | A small attitude or joint change can alter polar low-Sun shadow and Earth boresight clearance. |
| Panel geometry | Active-cell polygons or sampling surfaces, normals, area, mounting transforms, gimbal limits, electrical string topology | Total vehicle silhouette alone cannot yield cell-level self-shadow or bus power. |
| RF sensor geometry | Antenna phase center, boresight/scan limits, field of view, articulation, keep-out and gain pattern | A clear ray is only a geometric prerequisite, not a link budget. |
| Thermal-electrical properties | Cell technology, measured reference efficiency and temperature coefficient or performance curve, thermal mass, absorptivity/emissivity, conduction paths, heater/control states, losses | Temperature-dependent panel output depends on actual materials, coupling, and control design. |
| Lunar boundary conditions | Site- and time-specific illuminated wall geometry, measured or bounded wall reflectance/BRDF, view factors, wall temperatures/emissivity, regolith contact and sky sink assumptions | LOLA heights alone do not determine reflected solar flux or emitted infrared flux. |

For each external artifact retain source, version/date, license/authority,
units/frame, acquisition timestamp, and SHA-256. Record any mesh decimation or
repair as a new derived artifact with its own hash. The operational Horizons
epochs, independent SPICE comparison, and terrain DEM provenance remain those
of the parent simulation; the optional vehicle analysis must identify exactly
which parent JSON/hash it consumed.

## Implemented opt-in kernels

`science/spacecraft.py` accepts a strict version-`1.0.0` JSON manifest through
`load_spacecraft_geometry(manifest_path)`. Its required top-level fields are
`schema_version`, `model_id`, `provenance`, `mesh`, `panels`, and `antennas`;
provenance requires `source`, `revision`, and `spacecraft`. The mesh record
specifies a relative `path`, SHA-256, `format` (`obj` or `stl`), `units` (`m`),
and an explicit `scale_to_m`. Raw mesh coordinates are multiplied by
`scale_to_m`; the resulting body coordinates are meters (for example, a
centimeter-authored mesh uses `0.01`). Each named panel requires `area_m2`, a
unit `normal_body`, a finite set of `sample_points_m`, and positive
`sample_weights` summing to one. Each antenna requires an ID and body-frame
`phase_center_m`. At least one panel or antenna is required. The loader
rejects checksum mismatches, path escapes, malformed/degenerate triangles,
and oversized inputs; it does not infer missing hardware.

`evaluate_spacecraft_geometry(...)` takes the parent simulation's Sun and
Earth azimuth/elevation plus explicit yaw/pitch/roll. It reports per-panel
incidence cosine, weighted unoccluded and illuminated sample fractions,
effective direct-collection area, and obstruction IDs, plus Earth-**center**
self-line-of-sight from each antenna phase center. The output status is
`CONFIGURED_UNVALIDATED`; panel rays carry `ray_target: SUN_CENTER` and
antenna rays carry `ray_target: EARTH_CENTER`. Ray tests use a finite panel
sample set and a triangle acceleration structure, so the result is a
**sampled approximation**, not an exact continuous self-shadow profile. The
current mesh is static;
articulated state must already be embodied in the supplied mesh and sensor
coordinates. These outputs do not apply terrain occultation, Earth/Sun disk
extent, thermal response, or RF antenna gain.
OBJ object/group names and ASCII STL solid names can identify an obstruction;
binary STL has only the generic `mesh` obstruction ID.

`science/thermal.py` supplies `PanelThermalParameters`, `PanelEnvironment`,
`evaluate_panel_thermal_electrical(...)`, and
`advance_panel_thermal_electrical(previous_temperature_k, dt_s, ...)`.
Its nine required panel parameters include collecting/radiating area, heat
capacity, optical absorptivity/emissivity, reference PV efficiency/temperature,
a **relative** temperature coefficient, and mount conductance. Its required
environment includes direct normal irradiance, terrain-visible solar fraction,
incidence cosine, structural-unobstructed fraction, reflected-wall solar
irradiance, lunar IR irradiance, mount temperature, and radiative sink
temperature. The latter four boundary conditions are supplied externally;
this module does not compute them from LOLA or a universal albedo.

The single cell-temperature node is advanced with bounded implicit-Euler
substeps and an energy-closure check. Its heat balance is

```text
C dT/dt = alpha_s (P_direct + P_reflected) - P_electrical
          + epsilon_IR A_cell F_lunar_IR
          - epsilon_IR sigma A_radiating (T^4 - T_sink^4)
          + G_mount (T_mount - T)
```

The output separates direct and reflected electrical power, cell temperature,
temperature-adjusted efficiency, absorbed solar/IR heat, radiative loss,
conductive exchange, stored energy, and integration residual. Direct-beam
pointing/terrain/self-occlusion factors apply only to direct solar input.
Reflected-wall solar and lunar-IR inputs must already be **panel-plane incident
fluxes** with their own view factors and blockage represented; applying the
direct factors to them again would double-count occlusion. The radiative sink
must exclude any lunar IR already provided as a separate input.

`science/wall_albedo.py` can construct the reflected-solar boundary from
**supplied** terrain facets. For each facet the caller provides its ENU
centroid, normal and area, broadband reflectance, facet-specific Sun
visibility, and optionally wall-to-panel visibility; the panel's ENU position
and normal and the epoch's direct-normal solar flux are also required. It
uses single-bounce [Lambertian reflection](https://pages.nist.gov/SCATMECH/docs/lambert.htm)
and a [centroid view-factor approximation](https://ntrs.nasa.gov/api/citations/20050206360/downloads/20050206360.pdf).
Its output `wall_reflected_solar_irradiance_w_m2` feeds the thermal boundary
without another direct-beam incidence multiplier. Near-field facets that are
too large for centroid quadrature and a summed view factor over one fail
closed. This helper does **not** obtain real site reflectance from LOLA,
infer wall shadowing, resolve spectral BRDF, or auto-populate the environment
profile. A profile built from it still needs a documented source and SHA-256.

## Integrated runner and file contract

Once **actual, source-backed** vehicle and boundary files exist, the opt-in
runner is:

```bash
.venv/bin/python run_spacecraft_analysis.py \
  --simulation outputs/simulation.json \
  --hardware /path/to/controlled-hardware/hardware.json \
  --output /path/to/spacecraft-analysis.json
```

The output path must not already exist unless `--overwrite` is explicit. The
runner requires a v1.3 simulation export carrying Horizons/local-SPICE `PASS`
records, increasing UTC timestamps, and range-consistent solar flux; it does
not rerun the independent ephemeris calculation. It recomputes each exported
Sun/Earth skyline clearance and apparent-disk fraction, but a `PASS` field and
SHA-256 lineage do not authenticate an arbitrary parent file. The output
therefore calls the parent Horizons/SPICE provenance **declared, not
independently reverified** by this layer. It writes a **separate**
result with `analysis_status` equal to
`CONFIGURED_UNVALIDATED`, `flight_certified` equal to `false`,
parent/mesh/config/environment SHA-256 values, one analysis record per parent
epoch, per-panel geometry and thermal/electrical state, and per-antenna
Earth-center geometry.
It does not modify `outputs/simulation.json` or the five-site UI gauges.
The CLI rejects an output path that resolves to any input artifact or to the
baseline planner's output/index and web-data locations, even with
`--overwrite`. It publishes through a unique same-directory temporary file,
preserves an existing destination's permissions when replacing it, and
atomically refuses an existing destination without `--overwrite`. Epoch
exports contain aggregate panel shadow fractions rather
than every point-ray diagnostic, and a bounded BVH work budget fails an
overly expensive mesh/sample run instead of hanging indefinitely.

The following is a **schema illustration, not a runnable VIPER configuration**.
Every angle, temperature, material coefficient, flux, and digest token must be
replaced by controlled input; the parser deliberately rejects missing or
nonnumeric values. Relative referenced files must stay inside the hardware
directory.

```jsonc
// hardware.json — illustrative field shape only; not flight data
{
  "schema_version": "1.0.0",
  "geometry_manifest": {
    "path": "geometry/manifest.json",
    "sha256": "<64-hex-digest-of-manifest>"
  },
  "attitude_deg": {
    "yaw": "<surveyed-heading-deg>",
    "pitch": "<surveyed-pitch-deg>",
    "roll": "<surveyed-roll-deg>",
    "source": "<pose-survey-or-commanded-attitude-provenance>"
  },
  "panels": {
    "<panel-id-from-manifest>": {
      "thermal_parameters": {
        "collecting_area_m2": "<source-backed-number>",
        "radiating_area_m2": "<source-backed-number>",
        "heat_capacity_j_k": "<source-backed-number>",
        "solar_absorptivity": "<source-backed-number>",
        "ir_emissivity": "<source-backed-number>",
        "reference_efficiency": "<source-backed-number>",
        "reference_temperature_k": "<source-backed-number>",
        "efficiency_temperature_coefficient_per_k": "<source-backed-number>",
        "mount_conductance_w_k": "<source-backed-number>"
      },
      "initial_cell_temperature_k": "<measured-or-justified-number>"
    }
  },
  "environment_profile": {
    "path": "boundary/site-and-epoch-profile.json",
    "sha256": "<64-hex-digest-of-profile>"
  }
}
```

The referenced geometry manifest has this **non-runnable field shape**; the
mesh hash is for the exact OBJ/STL bytes, and all sensor coordinates are in
the post-scale body frame:

```jsonc
// geometry/manifest.json — illustrative fields, not a VIPER model
{
  "schema_version": "1.0.0",
  "model_id": "<controlled-model-id>",
  "provenance": {
    "source": "<CAD-release-source>",
    "revision": "<controlled-revision>",
    "spacecraft": "<actual-vehicle-identity>"
  },
  "mesh": {
    "path": "vehicle.obj",
    "sha256": "<64-hex-digest-of-mesh>",
    "format": "obj",
    "units": "m",
    "scale_to_m": "<numeric-raw-coordinate-to-meter-factor>"
  },
  "panels": [{
    "id": "<panel-id>",
    "area_m2": "<source-backed-number>",
    "normal_body": ["<unit-x>", "<unit-y>", "<unit-z>"],
    "sample_points_m": [["<x-m>", "<y-m>", "<z-m>"]],
    "sample_weights": ["<positive-weights-summing-to-one>"]
  }],
  "antennas": [{
    "id": "<antenna-id>",
    "phase_center_m": ["<x-m>", "<y-m>", "<z-m>"]
  }]
}
```

The environment JSON has exactly `schema_version: "1.0.0"`, `provenance`
(`source`, `revision`, `method`), and `samples`. There must be **one sample for
every parent simulation timestamp, in the same order**, each with exactly
`timestamp` and `panels`. Every manifest panel ID needs all four required
per-epoch boundaries:

```jsonc
// One illustrative samples[] entry; repeat for every parent UTC timestamp.
{
  "timestamp": "<exact-parent-simulation-timestamp>",
  "panels": {
    "<panel-id-from-manifest>": {
      "wall_reflected_solar_irradiance_w_m2": "<panel-plane-flux>",
      "lunar_ir_irradiance_w_m2": "<panel-plane-flux>",
      "mount_temperature_k": "<source-backed-number>",
      "radiation_sink_temperature_k": "<source-backed-number>"
    }
  }
}
```

The mesh manifest requires exact top-level keys `schema_version`, `model_id`,
`provenance`, `mesh`, `panels`, and `antennas`, as described above. Hardware
panel IDs must match every mesh-manifest panel ID; its thermal collecting area
must equal the corresponding panel area. The runner gets direct solar flux,
terrain-visible fraction, and Sun/Earth angles from the validated parent JSON,
then combines them with panel self-occlusion and the externally supplied
thermal boundaries. Boundary values at epoch `i` are held over `[i, i+1)` for
temperature integration. No measured wall-reflectance or wall-temperature
product is currently generated by the terrain pipeline.

## Frames and geometry contract

The local science frame is East/North/Up (ENU) at the selected lunar surface
site: azimuth is clockwise from north, elevation is above the local horizontal,
and direction is `(cos(e) sin(A), cos(e) cos(A), sin(e))`. The implemented
**body frame** is defined below; an incoming mission CAD assembly must be
converted and documented in that frame, including unit scale. The
body-to-ENU transform must include heading and surface roll/pitch; articulated
components need their own body-to-joint transforms.
Never infer those transforms from a rendered 3D pose or a model filename.

The implemented static-body convention is right-handed `+X` right, `+Y`
forward, `+Z` up; at zero attitude it aligns with ENU. Yaw is clockwise from
north for body `+Y`, positive pitch raises the nose, and positive roll lowers
the right side. For column vectors, `body → ENU = Rz(-yaw) Rx(pitch) Ry(roll)`.
Thus attitude order is not interchangeable, and a mission's native CAD frame
must be converted into this convention before analysis.

For each epoch, transform the Horizons Sun/Earth directions into the body
frame. A surface-sample ray test from each active panel patch toward the Sun
can flag direct self-shadow from other mesh triangles; a ray from the antenna
phase center toward Earth can flag spacecraft structural obstruction. Terrain
skyline occultation remains a separate test. The current output exposes a
sampled unobstructed fraction but does **not** quantify its uncertainty;
neither this fraction nor one Boolean is a full RF or electrical prediction.
Sampling density, triangle quality, ray origin bias, grazing-angle tolerances,
and moving-part state are
numerical sensitivities that require convergence tests.

An Earth-center ray test is not an Earth-disk or antenna-beam test. Even a
structurally clear Earth-center ray says nothing about antenna gain, pointing
error, polarization, surface multipath, ground-station availability, link
margin, modulation/coding, or relay service. The existing planner's 0/30/100
"comms potential" remains an illustrative terrain-only screening index.

## Thermal-electrical interpretation

NASA's [thermal-control overview](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/)
distinguishes direct solar heating, reflected solar heating (albedo), planetary
infrared heating, internally generated heat, stored heat, and emitted radiation.
NASA also notes the [large thermal range at the lunar south pole](https://www.nasa.gov/centers-and-facilities/johnson/bringing-the-heat-abigail-howard-leads-thermal-systems-for-artemis-rovers-tools/).
An opt-in model should therefore distinguish **direct cell-plane irradiance**,
**reflected wall irradiance**, **radiative/thermal boundary fluxes**, **cell
temperature**, and **electrical output**. Reflected light may heat a cell yet
produce different useful electrical power than direct sunlight because its
angular and spectral distribution differs. A site-wide scalar "albedo" is not
a resolved crater-wall source.

Temperature correction requires a cell-specific measured efficiency curve (or
an explicitly bounded first-order coefficient), a reference temperature, and
an actual thermal boundary-condition model. The sign and magnitude of a
coefficient must not be generalized to all technologies. A lumped panel-node
model may be useful for a sensitivity study, but it is not a complete active
thermal-control system: it cannot represent heater logic, radiator switching,
multi-node conduction, battery and load behavior, or flight hardware margins
unless those are explicitly modeled and correlated with test data.

The main planner's current `science/power.py` scenarios remain illustrative
direct-solar inputs. A vehicle-specific result should be exported separately
and labeled with its configuration provenance and assumption flags; it must
not silently replace the five-site baseline power, DTE windows, or UI gauges.

## Acceptance path toward a flight claim

This repository can verify software invariants, mesh parsing, frame
transformations, analytic ray-intersection cases, thermal energy accounting,
determinism, provenance, and sensitivity/convergence. Those tests establish
correct implementation of an explicitly limited model—not certification.
Before any operational/flight assertion, a mission team would need controlled
flight geometry and joint states, material/optical/electrical test data,
site-specific radiometric boundary conditions, correlated thermal-vacuum and
illumination tests, uncertainty margins, and independent review against the
mission's applicable requirements. [ECSS-E-ST-31C](https://ecss.nl/standard/ecss-e-st-31c-thermal-control/)
defines thermal-engineering requirements, and its [thermal-analysis handbook](https://ecss.nl/home/ecss-e-hb-31-03a-15november2016/)
emphasizes model credibility, verification, and maintainability. The presence
of these references does not certify this prototype.
