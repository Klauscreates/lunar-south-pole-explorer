# Lunar South Pole Explorer

Explore the Moon, compare evaluated south-pole points, and visualize how sunlight and Earth visibility change over time.

**Research and education—not flight certification.** Geometric visibility is not RF link quality. Modeled generation is not guaranteed power or battery charge.

![Dual-site comparison](docs/screenshots/current-comparison.png)

## Features and coverage

- Interactive Cesium Moon, terrain inspection and apparent Sun/Earth sky view.
- Five evaluated points: Connecting Ridge, Haworth, Malapert Massif, Nobile Rim 1, and the neutral **Test Site A** validation coordinate—not five certified landing sites.
- **October 1–December 31, 2026 UTC**, with 13,249 ten-minute epochs per point (final boundary: January 1, 2027 at 00:00 UTC). Unsupported dates remain unavailable.
- Liquid-glass mission planner with month shortcuts, custom cross-month windows, and interval-specific visual energy/visibility cards.
- Synchronized dual-site comparison, modeled generation, Earth-center visibility, disk exposure and thermal-model limitations.
- Reference lander R1: five attitudes and two assumed thermal environments—not exact flight hardware.
- SPICE-driven orbital view with 4K Earth/Sun textures. Displayed sizes and distances are compressed, not to scale.
- Checksummed exports and prepared terrain grids for running the included snapshot without regenerating the science.

## Quick start

Prerequisites: Python 3.12+, Node.js 22.6+ (Node 24 LTS recommended), npm and Git. No Cesium ion token is required.

```sh
git clone https://github.com/Klauscreates/lunar-south-pole-explorer.git
cd lunar-south-pole-explorer
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cd apps/web
npm ci
npm run build
npm run planner -- --production
```

Open **http://127.0.0.1:3000**. The launcher starts Next.js and the read-only Python terrain service together. Keep the terminal running; Ctrl+C stops both. Dependency installation needs internet access. Installation copies Cesium workers; the build verifies and copies the committed study exports.

For development, use `npm run planner` from `apps/web`. Do not run terrain preprocessing merely to view this snapshot: the required bounded grids and imagery are included. The verification commands below are run from the repository root.

### First visit

1. Open **Plan your mission**, pick UTC dates, then choose a location from its energy and visibility cards.
2. Expand its name card and scrub the UTC timeline. Instantaneous values and selected-window totals are labeled separately.
3. Choose **Compare this location** and pick a second point.
4. Open **How to use · methods & data** for limits, or **＋** for detailed instruments.

## Repository map

| Folder | Contents |
| --- | --- |
| `apps/web/` | Next.js/React/Cesium interface and frontend tests |
| `science/` | Ephemerides, horizon, visibility, power, thermal and vehicle models |
| `scripts/` | Terrain service, asset preparation and orbital export |
| `data/` | Source catalogues, vehicle specifications and prepared runtime terrain |
| `outputs/` | Checksum-indexed precomputed study snapshots |
| `tests/` | Python scientific and integration tests |
| `docs/` | Methods, provenance, limits and acceptance evidence |

Raw download caches, environments, logs and unrelated media are excluded. Local paths retained in provenance describe the generating machine; they are not runtime requirements. Kernels are downloaded separately using `science/ephemeris/kernels.lock.json`.

### Rebuilding date coverage

With the pinned kernels, source DEMs, and vehicle evidence already acquired:

```sh
.venv/bin/python run_candidate_array.py --end 2027-01-01T00:00:00Z
.venv/bin/python run_reference_lander.py
.venv/bin/python run_local_terrain.py
.venv/bin/python -m scripts.export_orbital_scene
npm --prefix apps/web run build
```

Horizons requests are batched into at most 9,000 epochs, with raw provenance retained and contiguous timestamps checked. The independent SPICE comparison runs over every epoch. Thermal states are integrated continuously from October 1, not restarted at month boundaries. Reference-design environmental loads remain assumptions, not measured lunar conditions. Extended coverage is not a new terrain-accuracy or flight-certification claim.

## Verification

The full Python suite requires the pinned NAIF kernels (downloaded separately, not committed). Fetch them once before testing; checksum mismatches fail closed.

```sh
.venv/bin/python -m science.ephemeris.kernels data/kernels
.venv/bin/python -m pytest -q
npm --prefix apps/web run lint
node --experimental-strip-types --test apps/web/scripts/*.test.mjs
npm --prefix apps/web run build
```

Browser acceptance: run `apps/web/scripts/acceptance.mjs` with `PLAYWRIGHT_MODULE` pointing to an installed Playwright ESM entry point. Chrome is the default browser; `APP_URL` selects the target server. See [acceptance evidence and limitations](docs/RELEASE_ACCEPTANCE.md). Raw-source regeneration and some audit checks require separately downloaded source material or kernels.

## Science and provenance

Operational site geometry uses JPL Horizons, cross-checked with local NAIF SPICE, and LRO LOLA terrain masks. Both geometry implementations share JPL ephemeris lineage. Registered NAC is a separately labeled experimental study; absent qualified coverage stays Unknown.

- [Scientific method](docs/SCIENTIFIC_METHOD.md) and [SPICE integrity](docs/SPICE_INTEGRITY.md)
- [Candidate coordinates](docs/CANDIDATE_ARRAY_2026-09-30.md)
- [Reference lander assumptions](docs/REFERENCE_LANDER.md)
- [Native terrain limitations](docs/NATIVE_TERRAIN.md)
- [Celestial imagery and attribution](docs/CELESTIAL_VISUALS.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

Root `run_*.py` entry points regenerate their respective studies. Read the methods before running them: downloads can be substantial, and changed inputs require rebuilding dependent checksum indexes. The frontend rejects stale or altered exports.

## Hosting

**Live app: [Lunar South Pole Explorer](https://lunar-south-pole-explorer.onrender.com)** — hosted on Render's free tier, independently of the development Mac. Free instances sleep when idle; allow about a minute for a cold start. Usage limits apply.

Both Next.js and the terrain backend run in one container. Server-only `TERRAIN_SERVICE_URL` also supports a separate backend. See [deployment requirements](docs/RELEASE_ACCEPTANCE.md). Temporary tunnel links are no longer needed for public access.

A single-service Docker configuration and explicit **Free** Render Blueprint are included. See [free deployment instructions and limits](docs/FREE_HOSTING.md).

## License

No open-source license has been assigned to original project code. Third-party software, imagery and documents retain their respective terms. Repository visibility does not change those rights.
