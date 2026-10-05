# Moon-first mission explorer

The scene background is black with a sparse, deterministic star cubemap behind
the Moon (six 1024px canvas faces, generated once per viewer, no downloads).
This is decorative visual context, not a time/frame-qualified lunar star
catalog or an input to visibility, energy, or navigation calculations. It uses
the existing render-on-demand loop and introduces no animation timer.

Retina correction: Cesium's `useBrowserRecommendedResolution` is explicitly
false, paired with `resolutionScale = min(1, 2 / devicePixelRatio)`. The previous
default ignored device pixel ratio and downscaled a 3x phone to 0.667 CSS
resolution. The corrected canvas targets 2 device pixels per CSS pixel (786x1704
for a 393x852, 3x display), not an unbounded native-resolution GPU load. Terrain
screen-space error is reduced from 5 to 2 for finer existing mesh sampling.
This improves rasterization and mesh selection, not source DEM precision.

Launch has no site card or Mission control. The top-right Locations button opens
five points with coordinates and battery/signal potential graphics. Compare is
inside Locations and opens the dual-site cross-examination dashboard. Both views
retain the evaluated week, R1 case and scientific qualifications.
Selecting a point flies to it and closes Locations. A collapsed details control
appears only when the camera is within 30 km of the selected point and the
center terrain pick is within 20 km, and not in Moon-overview mode. These are
UI proximity thresholds, not scientific accuracy claims. Expanding the control
reveals coordinates and weekly battery/signal metrics. Each site flight starts
collapsed; Moon overview clears the card. Unavailable data remains Unknown.
Scientific instruments remain accessible through +.

The default interface presents a full-screen Moon and stars without site metrics.
Five existing coordinates fly to the terrain viewer.
The + control opens the original scientific instruments, including the explicit
LOLA / experimental gauge selector. Returning preserves explorer configuration.

Only Open Reference Lander R1 is available: its ten attitude/thermal scenarios
are not ten different flight spacecraft. Only October 1–8, 2026 UTC is evaluated.
Weekly data loads through the existing SHA-256 and parent-linked study contract.

The R1 selector uses `SpacecraftControlPanel` inside `MoonExperience` (the current
explorer rendered by `MissionPlanner`). Its controlled value also drives every
weekly metric and ranking. Compass yaw and pitch/roll badges come from the
selected study's design metadata, not substring guesses or independent state.
Added load means assumed wall/IR heating (20/50 W/m²), not drill/RF electrical
demand; low load is 0/10 W/m². The offset alignment dot is schematic, with actual
angles shown in text. Unknown metadata stays Unknown. Transitions respect
reduced-motion preferences; no pulse timer is used.

## Graphic definitions

- Energy figure: integrate R1 electrical watts over the 168-hour export in kWh.
- Battery-shaped icon: fraction of evaluated time with modeled power >0 W;
  never state of charge. No battery capacity or spacecraft load is modeled here.
- Communications bars: fraction of time Earth-center LOS is clear through both
  baseline terrain and R1 self-occlusion; not RF signal strength.
- Left-endpoint, 10-minute intervals; terminal sample has no duration.
- The old weekly ranking is replaced by a synchronized dual-site comparison.
  No failed or missing result becomes zero. Test Site A is a validation point.

## Dual-site cross-examination

Site A starts at the selected location; Site B starts at the first different
indexed site. Both slots are selectable and cannot select the same site. The
shared 0–1008 slider updates the main planner epoch at exact ten-minute intervals
from October 1 to October 8, 2026 UTC. R1 scenario selection is shared. Five
checksum-validated exports provide 5,045 site epochs; the index is a manifest,
not itself a flat sample array. Abortable loads verify simulation and linked
vehicle/terrain report hashes before display. Timestamp mismatches fail closed.

The five pillars distinguish:

1. LOLA Sun/Earth elevation, skyline and clearance; SVG is an azimuth/elevation
   diagram, not a camera projection. The plotted skyline uses all 720 rays.
2. Existing assumed-input R1 watts and left-endpoint cumulative generation.
   Net after vehicle demand is Unknown. The battery is a power bar relative to
   the source-pinned XTJ AM0 reference times R1 area, not stored battery energy.
3. Modeled R1 cell temperature plus separately labeled XTJ BOL AM0 reference.
   `component-spec.json` and the manufacturer PDF SHA are checked at data sync.
   The normalized Vmp/Jmp calculation mirrors `science/component_spec.py` and
   refuses both below 15 C and above 125 C. R1 legacy generation is not silently
   replaced or claimed as calibrated XTJ array output.
4. 0/30/100 geometry index with R1 center self-occlusion, and the original
   terrain disk fraction. This fraction is a straight-skyline circular-disk
   approximation, not exact physical disk exposure or an RF link budget.
5. Confidence-qualified registered 10 m plane-fit slope where available.
   No export has 500 m radius roughness; 50 m is never substituted. Trafficability
   stays Unknown. Native diagnostics never overwrite the LOLA visibility model.

Both columns retain all five pillars side-by-side on phones. Count interpolation
is presentation-only (220 ms); numeric targets remain the selected samples.
Column entrances, fluid bars and warning pulses respect reduced-motion settings.
Green is geometric clearance only, never a landing-safety certification.

Tests: `node --test apps/web/scripts/*test.mjs` covers all 5,045 timestamps,
all ten R1 cases, integrated energy, thermal boundaries and provenance gates.

## Globe imagery

NASA SVS CGI Moon Kit's 2019 4096x2048 LROC/LOLA color mosaic replaces the 2K
render texture. Reproduce with `.venv/bin/python scripts/prepare_moon_texture.py`
(macOS sips format conversion, JPEG quality 90; no upscaling or generated detail).
Source: https://svs.gsfc.nasa.gov/4720/ . The source map is aesthetic context,
including coarse polar albedo fill and inpainting, not scientific radiometry or
new high-resolution terrain coverage. All backend science is unchanged.

Source TIFF SHA-256: `918649a7f8ed2f1329b2cd95bb0d25483befdcb60ae1a66db681a637cc21344f`.
Prepared JPEG SHA-256: `32d2f30822dd7fac0584d13f03f039a6914061449ee0342dc1958a81be1801cf`.

Regression: `node --test apps/web/scripts/weekly-metrics.test.mjs
apps/web/scripts/terrain-gauge.test.mjs`. Real R1 scenarios must all span 168 hours;
synthetic interval tests verify duration weighting and terminal-epoch handling.
