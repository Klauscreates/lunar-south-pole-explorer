# Date-first mission planning

The existing map, gestures, orbital view and scientific instruments are unchanged. The entry action is now **Plan your mission**:

1. Choose UTC start/end times at 10-minute boundaries.
2. See the five locations with modeled energy and Earth-center line-of-sight availability over that interval.
3. Select a location, expand its details, and use **Compare this location** to retain it as the initial comparison anchor.

The comparison timeline is bounded by the chosen dates. Each column shows interval totals, and accumulated generation is measured from the mission start, not October 1. The existing R1 scenario selection remains available.

Coverage has **not** been extended: committed datasets still run from 2026-10-01 00:00 UTC to 2026-10-08 00:00 UTC. Out-of-coverage, reversed, empty and off-grid windows cannot proceed. Kernel availability through year-end is not equivalent to generated/validated year-end studies. Energy is modeled generation, not guaranteed output or battery charge; LOS availability is not RF signal quality.

Verification: production build, lint, 27 frontend unit tests, 16 existing acceptance groups, and the new `apps/web/scripts/mission-flow.mjs` pass locally. The new test covers 390px and 1440px layouts, unsupported dates, source-derived interval totals, site selection, comparison target changes and selected timeline bounds. Browser emulation is not physical iPhone Safari qualification.
