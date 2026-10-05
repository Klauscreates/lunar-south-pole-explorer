# Mobile planner

At widths up to 950 CSS pixels (including iPhone 16 landscape), the planner
uses an unobstructed globe and five bottom navigation controls: Globe, Sites,
Gauges, Time, Tools. Sites/layers, gauges, timeline and tools appear in mutually
exclusive scrollable sheets. Tap the selected tab again or Globe to collapse;
navigation also dismisses analysis overlays. Desktop panels are unchanged.

The layout uses dynamic viewport height and safe-area insets, 44px minimum
button/select targets, and 16px form inputs. Browser zoom is not disabled.
Globe touch gestures are contained in the canvas; sheets retain native scrolling.
Mobile startup fetches one simulation instead of prefetching all five. Selected
sites are still hash-verified and cached. The mobile terrain tile cache is 100
tiles instead of 350; scientific terrain calculations are unchanged.

## Verification

- Chromium viewport checks: 393x852 portrait and 852x393 landscape.
- No horizontal overflow; persistent navigation does not overlap sheets.
- Confirmed only simulation.json loads initially, not the four candidate exports.
- Site selection, model selection, Unknown coverage, Tools/native terrain and
  timeline controls remain available.
- Desktop 1440x900 regression check; lint, TypeScript/production build and
  four terrain-gauge regression tests.

These checks emulate layout, not an actual iPhone. Before a device-qualified
release, test Safari on iPhone 16 for pinch/rotate gestures, browser-toolbar and
keyboard transitions, safe-area behavior, sustained GPU load, and memory pressure.
Use HTTPS for remote device access: integrity checks require Web Crypto's secure
context. The development localhost address is local to the computer running it.
