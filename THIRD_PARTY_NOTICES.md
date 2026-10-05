# Third-party data and software

- **NASA/JPL Horizons and NAIF SPICE:** geometry and kernel sources are retained in export provenance and `science/ephemeris/kernels.lock.json`. Upstream terms apply; do not imply NASA endorsement.
- **NASA LRO LOLA/LROC and GSFC PGDA:** bounded elevation grids and imagery. Source URLs, processing records and checksums are in the terrain manifests and study exports.
- **Solar System Scope / INOVE:** Earth day/cloud and Sun maps, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). [Provider](https://www.solarsystemscope.com/textures/). Artist-adjusted maps resized/re-encoded to 4096×2048, not live observations. Original/output hashes and dimensions: `apps/web/public/celestial/texture-manifest.json`. Attribution also appears in the app.
- **Spectrolab XTJ Prime datasheet:** manufacturer-owned reference retained for checksum verification. Source/revision: `data/spacecraft/reference-lander-v1/component-spec.json`. No open-license or calibrated flight-array claim is made.
- **Surveyor archival documents:** source catalogue and limits: `data/spacecraft/surveyor7/evidence.json`. Bulk archival PDFs are not included.
- **CesiumJS, Next.js, React and Python dependencies:** upstream licenses apply. Dependency versions are recorded in the npm lockfile and Python metadata; installed dependency trees are excluded.

The project has not been relicensed. Before making this repository public or redistributing third-party documents, review upstream terms and required permissions.
