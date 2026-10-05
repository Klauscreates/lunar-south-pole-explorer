# Reference lander and Surveyor VII evidence

The app's **Spacecraft lab** runs a fully specified, project-authored reference
design over the existing five Horizons/SPICE/LOLA site exports. Surveyor VII
provides an archival evidence record alongside it. These are different vehicles:
Surveyor observations do not calibrate or validate the reference design.

## What is implemented

- R1 geometry: six cuboids for the body, array backing, forward payload, mast,
  and two leg supports. `data/spacecraft/reference-lander-v1/design.json` defines
  every dimension, panel surface and sensor point. Generated OBJ and manifest
  are in `outputs/spacecraft/`. There is no hidden visualization-only rover mesh.
- One 1 m² vertical array, sampled at 64 equal-area cell centers. Five poses
  (north/east/south/west level and north with +10° pitch/+5° roll) exercise the
  existing rigid-mesh raycaster and one-node thermal-electrical solver.
- Two constant panel-plane environmental sensitivity cases. Their wall solar,
  lunar IR, mount and sky-sink values are explicit **assumptions**, not measured
  site radiometry and not lower/upper confidence bounds. The added-wall case
  can supply reflected power during local terrain shadow; it does not claim a
  terrain-facet illumination calculation has been performed.
- Every combination covers every epoch at every site: 5 × 2 × 5 × 1,009 =
  **50,450 scenario epochs**. Initial cell temperature is 250 K in each run;
  the prior epoch's boundary is held over the next interval. No pre-run thermal
  equilibrium or historical temperature reconstruction is assumed.
- The lab follows the main site selection and timeline. It shows modeled
  panel power, temperature, efficiency, incidence, structurally clear sample
  fraction, and combined terrain/body Earth-center LOS. The graphic rotates
  independently as a viewing control, not as a change to the body pose.
- Parent data, design, evidence, mesh and kernel code hashes provide lineage.
  Site studies are checksum-verified in the browser. The build refuses stale
  parent/design/kernel outputs. No spacecraft result overwrites the site's
  existing illustrative panel or terrain-only communications data.

## Evidence and limits

The downloaded source is **JPL TR 32-1264, Surveyor VII Mission Report, Part I**,
15 February 1969, NTRS `19690008977`. The source PDF SHA-256 is
`6e30b5af05ce9d0170bac1702a5da6d999d385b1eac90bfdc0cf59403543dc89`.
Its raw PDF is cached locally (excluded from Git); the source URL, digest,
printed pages, PDF pages and transcribed values are in
`data/spacecraft/surveyor7/evidence.json`.

Visually checked source pages:

| Printed / PDF page | Evidence | Interpretation |
|---|---|---|
| 64 / 81 | Table IV-12: 84 W predicted versus 89 W reported coast-phase average solar power; text: 30.3 V and 2.93 A averages | Transit data, not a lunar-surface output rating. Product of averages is only an approximate arithmetic cross-check. |
| 64 / 81 | Battery-charge-regulator efficiency listed as 94.6% | Text explicitly calls this an estimate, not a direct flight measurement. |
| 65 / 82 | Solar panel generally 15–45° ahead of Sun; fully sun-oriented in final 24 hours | Operational shading and charge control invalidate a universal perfect-tracking assumption. |
| 161 / 179 | 23 January 1968 camera sunset at 06:06 GMT; panel zero output at 06:24 GMT | Two distinct observables. We have not reconstructed that mission's terrain, pose and commanded joint history. |

An initially inspected NTRS `19680009190` report proved to be **Surveyor IV**,
not Surveyor III. It is not used as evidence for the Surveyor VII configuration.

The R1 thermal properties (including 30% reference efficiency and -0.003/K
relative efficiency coefficient) are declared design-study assumptions. There
is no measured cell curve, as-built hardware, RF antenna gain pattern, battery
or heater-control model, electrical-string mismatch calculation, multi-node
thermal network, or physical test correlation. Radiating area is an effective
parameter, not a view factor computed from the mesh. All components reuse the
parent site's observer-height terrain mask; height-specific skyline changes
are unresolved. Structural shadow uses point rays to the Sun center multiplied
by the parent terrain disk fraction, not a joint full-disk occultation solution.
Sampling uncertainty is not quantified.

The output is `DESIGN_STUDY_UNVALIDATED`, with `flight_certified: false`.
Surveyor correlation remains `NOT_RUN`. The missing historical inputs are
explicitly listed in the evidence record and the app.

## Reproduce

With the existing Python environment and five validated site exports:

```bash
mkdir -p data/spacecraft/surveyor7/sources
curl --fail --location \
  https://ntrs.nasa.gov/api/citations/19690008977/downloads/19690008977.pdf \
  -o data/spacecraft/surveyor7/sources/19690008977.pdf
.venv/bin/python run_reference_lander.py
npm --prefix apps/web run data:sync
.venv/bin/python -m unittest discover -s tests -q
```

The generator checks the source PDF digest, verifies all parent hashes, and
creates temporary, fully pinned hardware/environment inputs for the existing
`analyze_spacecraft_files` runner. The exact mesh is retained; environment files
are reproducible from the design constants and parent timestamps. The compact
web exports declare column names, timestamps and scenario input digests. The
index is published after all site results are complete.

After modifying geometry, assumptions, parent data or a science kernel, rerun
the generator. Rebuild and restart the production planner to serve UI changes.

## Verification

### Component sourcing first pass - 2026-10-02

`data/spacecraft/reference-lander-v1/component-spec.json` selects Spectrolab
XTJ Prime BOL cells as the initial candidate and records the manufacturer PDF
revision (2018-07-16), SHA-256, source pages, units and reference conditions.
Both source pages were visually reviewed. This is a component selection,
**not a completed bill of materials or buildable panel assembly**. Nothing in
the active R1 thermal parameters or the existing web studies was replaced.

The source gives 30.7% production-average efficiency at 28 C and AM0
1353 W/m2, cell absorptance 0.88 and emittance 0.85. Its BOL Vmp and Jmp
temperature coefficients apply from 15 to 125 C. `science/component_spec.py`
provides a separately callable cell reference over that interval, normalized
to the reported efficiency. It refuses extrapolation. This is not a full
I-V, low-light, aging, panel packing or string-mismatch model. The rounded
Vmp/Jmp table implies 421.05 W/m2 whereas the separately reported efficiency
implies 415.371 W/m2; both are retained rather than silently made consistent.
The datasheet does not supply uncertainty intervals; `null` means unknown,
not zero. Optical-property temperature/angle ranges are also unresolved.

Run the source-integrity check and live assumption audit with:

```bash
.venv/bin/python audit_reference_inputs.py
```

The audit covers all 18 active thermal, initial-state and environmental inputs,
plus the selected cell evidence and outstanding assembly/environment tasks.
The source PDF is retained under `sources/xtj-prime.pdf` for checksum validation
in the private repository; its manufacturer terms still apply.
It fails on a changed source PDF, study checksum or stale design.

All 50,450 existing scenario temperatures are outside (below) the cell
coefficient range: approximately 177.44 to 285.50 K across the array versus a
288.15 K lower limit. These are temperatures predicted using the old assumed
R1 properties, not measured XTJ temperatures. They show why copying these
datasheet coefficients into the current lunar model would be unsupported.

Outstanding assembly choices include cell size/layout, coverglass, adhesive,
substrate/backing thickness and mass, front/rear finishes, fasteners/contact
conductance, wiring/MPPT and temperature-dependent material data. Cold-cell
measurements and thermal-balance tests remain necessary for validation.
Diviner ingestion and time-dependent terrain radiative loads are the next
environment stage, not implemented by this component audit. The source entry
point is https://www.diviner.ucla.edu/data; its maps cannot simply be treated
as epoch-matched panel irradiances.

121 Python tests pass after adding reference-condition, valid-range,
non-mutation/completeness and corrupted-source regression checks.

The reference tests independently check the analytic zero-elevation payload
and mast shadow (14 of 64 panel samples blocked), sensor self-occlusion, all
50,450 exported epoch rows, site/timestamp/hash alignment, energy closure,
thermal sensitivity, heading sensitivity, and the limited archival arithmetic
check. These establish software behavior and export integrity; they do not
establish agreement with flight hardware.
