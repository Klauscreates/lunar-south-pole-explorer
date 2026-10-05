# Loading and interaction polish — October 4, 2026

## Findings and changes

- Desktop startup fetched four unused candidate exports (22,731,401 uncompressed bytes). These now load on demand, sharing the existing validated simulation cache.
- Closing/reopening Locations triggered five spacecraft-study downloads. Session-scoped promise deduplication now reuses validated results, keyed by site ID and parent SHA-256. Five entries maximum; failed requests are evicted for retry. Closing one panel cancels its subscription, not another panel's shared download. Network work times out after 60 seconds. Reloading the page starts a new snapshot.
- Weekly integrations are memoized by report/configuration, not recomputed on every timeline update.
- Spacecraft instrument rows now require the currently selected site ID and parent checksum; equal timestamps alone cannot admit the previous site's report.
- Camera site flights shortened from 3 to 1.6 seconds; overview/sky from 2.5 to 1.5 seconds, double-click from 1.8 to 1 second. Reduced-motion preference skips these flights. Camera destinations and scientific geometry are unchanged.
- Glass controls have visible keyboard focus. Busy location choices have progress feedback; reduced-motion panel transitions are disabled.
- Fault-test cleanup waits for active interceptions before closing the browser, eliminating a test-only teardown race.

## Evidence

`scripts/loading-check.mjs` uses a fresh Chrome browser cache and counts request URLs. Initial live baseline: 4 speculative candidate requests, 5 repeat study requests. Updated local build: **0 and 0**, asserted by `EXPECT_OPTIMIZED=1`. Uncompressed sizes describe avoided parsing/input volume, not compressed network bytes. Local and cloud timings are not a controlled speed comparison; no percentage speedup is claimed.

- 24 frontend tests pass, including shared-cache deduplication, cancellation isolation, checksum-key isolation, eviction and retry.
- 134 Python tests pass (75 existing warnings).
- ESLint and production build pass; data checksum synchronization passes.
- Baseline live acceptance: 16 groups pass at desktop 1440×1000 and mobile 390×844.
- Updated local acceptance: after fixing the test teardown race, a complete rerun passed all 16 groups cleanly. User-flow assertions include all sites, unsupported dates, comparison configurations, orbital playback and instruments.
- Render deployed `f00aa32` successfully. A full public-URL acceptance rerun passed all 16 groups, including desktop/mobile and fault injection. The hosted loading check also asserted **0 speculative candidate requests and 0 repeated study requests** (baseline 4 and 5). One warm-host run showed controls at 2,073 ms versus the earlier 2,435 ms baseline; this single uncontrolled timing is not a statistically established speedup.
- Mobile comparison screenshot reviewed; no horizontal overflow or uncaught errors in acceptance flows.

No scientific source/export bytes were changed. This check does not establish physical iPhone Safari GPU performance, sustained FPS, cellular-network performance, concurrent-user capacity, or free-host cold-start time. Render's idle sleep remains a hosting limitation.

Reproduce with `PLAYWRIGHT_MODULE` set to an installed Playwright entry point; set `APP_URL` for a hosted target. Run `scripts/loading-check.mjs`, `scripts/acceptance.mjs`, frontend `*.test.mjs`, lint, build and pytest as described in README.

## Touch navigation follow-up

- One finger rotates the lunar surface naturally; orbital view uses depth-scaled screen-space panning in all four directions. Two fingers remain delegated to Cesium's native pinch controls.
- Touching the canvas immediately cancels a camera fly-in. Canvas-only touch handling prevents browser scrolling from stealing gestures without disabling panel scrolling. Surface rotation and zoom inertia are shortened for more responsive stopping.
- Finite-value/jump guards reject invalid pan deltas. Pointer capture, cancellation, cleanup and switching between touch/mouse or surface/orbit are handled explicitly.
- Production build and lint pass; 26 frontend tests pass. `scripts/touch-check.mjs` exercises CDP touch swipes, pinch, orbit exit and location controls at 390×844 with no uncaught errors. Before/after screenshots confirm a 75-pixel rightward finger drag translates the Moon accordingly.
- These are emulated Chromium touch checks, not physical iPhone Safari feel or GPU qualification. Scientific exports and terrain geometry remain unchanged.
