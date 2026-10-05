# Challenge release scope and acceptance

## User journey

Open Locations, choose one of five evaluated points, expand its name card and scrub a UTC epoch. Whole-week totals are separate from the selected-instant power and Earth-center LOS. Compare uses two different points at the same epoch and R1 configuration. The in-app methods disclosure links source agencies and the checksum index.

Coverage is 2026-10-01 00:00 through 2026-10-08 00:00 UTC inclusive, at ten-minute sample spacing (1,009 epochs per site). Dates outside that interval, invalid dates and off-grid times are unavailable. The relevant date-entry view hides its gauges rather than showing the previous values as predictions; the globe stays at the last supported epoch. Four candidate-region evaluation points plus Test Site A do not imply five certified landing sites.

## Scientific boundaries

- Power is modeled generation, not battery charge, guaranteed delivery or net energy after loads.
- Earth visibility and the 0/30/100 geometry index are not RF strength or a communications link budget.
- Terrain visualization and landing safety are distinct; unqualified experimental coverage stays Unknown.
- Orbital overview deliberately compresses size and distance. Earth/Sun maps are illustrative, not live observations.

## Reproducible checks

```sh
.venv/bin/python -m pytest -q
npm --prefix apps/web run lint
node --experimental-strip-types --test apps/web/scripts/*.test.mjs
npm --prefix apps/web run build
# With Playwright installed; Chrome is the default browser channel:
node apps/web/scripts/acceptance.mjs
```

Set `PLAYWRIGHT_MODULE` to an existing Playwright ESM entry point when it is not installed in the project. `APP_URL` selects a deployed URL instead of localhost. The UI suite covers all five selections, all ten R1 configurations, invalid dates, dual-site controls, orbital playback, desktop study panels, the terrain API and a missing-study failure. It is not a substitute for real iPhone Safari touch/GPU testing or an independent scientific audit.

## Stable-hosting handoff (not deployed yet)

This project needs both Next.js and the Python terrain service. A frontend-only deployment leaves `/api/terrain/*` broken. Prefer a full-stack host with Node, Python, HTTPS, persistent verified `data/web_terrain` assets and a supervised terrain process. The current terrain service binds localhost:8766; keep it behind the web proxy. The current planner launcher binds localhost:3000, suitable behind an HTTPS reverse proxy.

For separate frontend/backend hosting, configure server-only `TERRAIN_SERVICE_URL` to the HTTPS origin of the hosted terrain service. It must not point to this Mac or a temporary tunnel. Protect and rate-limit the terrain origin; the local Python development HTTP server is not a public edge server.

Build with the full validated repository inputs: `prebuild` verifies science source/output checksums and copies the public data. Do not upload `.env` files, `.venv`, raw caches, unrelated attachments or the entire workspace. Serve all required public data, Cesium workers, terrain imagery and celestial textures. No paid resources, DNS changes or account changes have been made.

Release remains blocked until an owner/hosting destination is confirmed, frontend and terrain backend are deployed, and the acceptance suite plus real-device tests pass on the stable HTTPS URL. The Cloudflare quick tunnel is only a temporary preview, not delivery.

## Execution results — October 4, 2026

- Python: 134 passed; 75 dependency deprecation/projection warnings, no failures.
- Frontend/data contracts: 21 passed, including all 5,045 site epochs and the ten R1 scenarios, date boundaries and texture integrity.
- ESLint, TypeScript/production build and `git diff --check`: passed.
- Chrome end-to-end: 16 acceptance groups passed at 1440×1000 and 390×844. All five site selections, invalid/covered dates, comparison targets, ten configurations, timeline limits, sky/reset, orbital playback, instrument panels and provenance were exercised. No uncaught browser errors or horizontal page overflow observed.
- HTTP: terrain health, inspection and all five tile kinds return 200; unsupported route and invalid latitude return 400.
- Fault injection: missing study stays Unknown, missing simulation index prevents predictions, altered study bytes fail checksum verification.
- Visual checks: desktop and phone-width comparison screenshots inspected. Fixed explorer controls intercepting the scientific toolbar and floating sky/orbital controls covering the comparison sheet. Updated the stale horizon-mask ray count to use the export.
- Temporary HTTPS preview returned 200; this is not a stable-hosting acceptance result.

Not tested/claimed: physical iPhone Safari touch/GPU behavior, every possible gesture or network failure, load/soak testing, penetration testing, independent validation of the research models, or cloud deployment. A passing automated suite is not flight certification or proof of universal correctness.
