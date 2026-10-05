import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, renameSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const publicData = fileURLToPath(new URL("../public/data/", import.meta.url));
const indexSource = `${root}/outputs/simulation-index.json`;

function copyAtomic(source, destination) {
  const temporary = `${destination}.tmp`;
  copyFileSync(source, temporary);
  renameSync(temporary, destination);
}

const index = JSON.parse(readFileSync(indexSource, "utf8"));
if (index.schema_version !== "1.0.0" || !Array.isArray(index.sites) || index.sites.length !== 5)
  throw new Error("Validated five-site simulation index is missing; run run_candidate_array.py");

const files = [];
const ids = new Set();
for (const entry of index.sites) {
  if (!/^[a-z0-9-]+$/.test(entry.id) || ids.has(entry.id))
    throw new Error("Simulation index contains an invalid or duplicate site ID");
  ids.add(entry.id);
  const expectedName = entry.id === "test-site-a" ? "simulation.json" : `${entry.id}.json`;
  if (entry.data_url !== `/data/${expectedName}` || !/^[a-f0-9]{64}$/.test(entry.sha256))
    throw new Error(`Simulation index link/hash is invalid for ${entry.id}`);
  const source = entry.id === "test-site-a"
    ? `${root}/outputs/simulation.json`
    : `${root}/outputs/candidates/${expectedName}`;
  const digest = createHash("sha256").update(readFileSync(source)).digest("hex");
  if (digest !== entry.sha256)
    throw new Error(`${entry.id} export failed SHA-256 validation`);
  files.push({ source, destination: `${publicData}/${expectedName}` });
}
if (!ids.has("test-site-a") || [...ids].filter((id) => id !== "test-site-a").length !== 4)
  throw new Error("Simulation index does not contain Test Site A plus four candidates");

mkdirSync(publicData, { recursive: true });
for (const file of files) copyAtomic(file.source, file.destination);
copyAtomic(`${root}/outputs/simulation.csv`, `${publicData}/simulation.csv`);
copyAtomic(indexSource, `${publicData}/simulation-index.json`);
console.log("Synced five SHA-256-validated simulation exports into public/data");

const orbitalIndex = JSON.parse(readFileSync(`${root}/outputs/orbital-index.json`, "utf8"));
const orbitalBytes = readFileSync(`${root}/outputs/orbital-scene.json`);
if (orbitalIndex.url !== "/data/orbital-scene.json" || orbitalBytes.length !== orbitalIndex.bytes ||
    createHash("sha256").update(orbitalBytes).digest("hex") !== orbitalIndex.sha256)
  throw new Error("Orbital scene failed integrity verification; run python -m scripts.export_orbital_scene");
copyAtomic(`${root}/outputs/orbital-scene.json`, `${publicData}/orbital-scene.json`);
copyAtomic(`${root}/outputs/orbital-index.json`, `${publicData}/orbital-index.json`);

// Vehicle studies have their own provenance and cannot replace a site export.
const vehicleRoot = `${root}/outputs/spacecraft`;
const digestFile = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const designSha = digestFile(`${root}/data/spacecraft/reference-lander-v1/design.json`);
const evidenceSha = digestFile(`${root}/data/spacecraft/surveyor7/evidence.json`);
const implementationNames = ["run_reference_lander.py", "science/spacecraft.py", "science/spacecraft_analysis.py",
  "science/thermal.py", "science/power.py", "science/visibility.py"];
const vehicleIndex = JSON.parse(readFileSync(`${vehicleRoot}/index.json`, "utf8"));
if (vehicleIndex.schema_version !== "1.0.0" || vehicleIndex.model_id !== "open_reference_lander_v1" ||
    !Array.isArray(vehicleIndex.sites) || vehicleIndex.sites.length !== index.sites.length)
  throw new Error("Reference lander studies are missing; run run_reference_lander.py");
const vehicleFiles = [];
const vehicleIds = new Set();
for (const entry of vehicleIndex.sites) {
  const parent = index.sites.find((site) => site.id === entry.site_id);
  if (!parent || vehicleIds.has(entry.site_id) || entry.parent_sha256 !== parent.sha256 ||
      entry.url !== `/data/spacecraft/${parent.id}.json` || !/^[a-f0-9]{64}$/.test(entry.sha256))
    throw new Error("Reference lander index has stale or invalid lineage");
  vehicleIds.add(entry.site_id);
  const source = `${vehicleRoot}/${parent.id}.json`;
  const bytes = readFileSync(source);
  if (createHash("sha256").update(bytes).digest("hex") !== entry.sha256)
    throw new Error(`Reference lander checksum failed: ${parent.id}`);
  const study = JSON.parse(bytes.toString("utf8"));
  if (study.parent_sha256 !== parent.sha256 || study.site_id !== parent.id ||
      study.flight_certified !== false || study.analysis_status !== "DESIGN_STUDY_UNVALIDATED" ||
      study.design_sha256 !== designSha || study.evidence_sha256 !== evidenceSha ||
      implementationNames.some((name) => study.implementation_sha256?.[name] !== digestFile(`${root}/${name}`)))
    throw new Error(`Reference lander contract failed: ${parent.id}`);
  vehicleFiles.push({ source, destination: `${publicData}/spacecraft/${parent.id}.json` });
}
mkdirSync(`${publicData}/spacecraft`, { recursive: true });
for (const file of vehicleFiles) copyAtomic(file.source, file.destination);
copyAtomic(`${vehicleRoot}/index.json`, `${publicData}/spacecraft/index.json`);
copyAtomic(`${vehicleRoot}/reference.obj`, `${publicData}/spacecraft/reference.obj`);
copyAtomic(`${vehicleRoot}/geometry.json`, `${publicData}/spacecraft/geometry.json`);
console.log("Synced separately labeled reference lander studies for all five sites");

// Publish the source-pinned cell reference without promoting it to R1 physics.
const componentPath = `${root}/data/spacecraft/reference-lander-v1/component-spec.json`;
const componentSpec = JSON.parse(readFileSync(componentPath, "utf8"));
if (componentSpec.automatic_promotion_to_active_model !== false ||
    componentSpec.source.path !== "sources/xtj-prime.pdf" ||
    digestFile(`${root}/data/spacecraft/reference-lander-v1/sources/xtj-prime.pdf`) !== componentSpec.source.sha256)
  throw new Error("Cell reference source integrity failed");
copyAtomic(componentPath, `${publicData}/spacecraft/component-spec.json`);

const terrainRoot = `${root}/outputs/local-terrain`;
const terrainIndex = JSON.parse(readFileSync(`${terrainRoot}/index.json`, "utf8"));
if (terrainIndex.schema_version !== "1.0.0" || terrainIndex.sites.length !== index.sites.length)
  throw new Error("Local terrain catalogue missing; run run_local_terrain.py");
const terrainIds = new Set();
const terrainFiles = [];
for (const entry of terrainIndex.sites) {
  const parent = index.sites.find((site) => site.id === entry.site_id);
  if (!parent || terrainIds.has(entry.site_id) || entry.parent_sha256 !== parent.sha256 ||
      entry.url !== `/data/local-terrain/${parent.id}.json`)
    throw new Error("Invalid local terrain lineage");
  terrainIds.add(entry.site_id);
  const source = `${terrainRoot}/${parent.id}.json`;
  if (digestFile(source) !== entry.sha256) throw new Error("Local terrain checksum mismatch");
  const report = JSON.parse(readFileSync(source, "utf8"));
  if (report.schema_version !== "1.1.0" || report.parent_sha256 !== parent.sha256 || report.site_id !== parent.id ||
      report.landing_safety_certified !== false || report.operational_visibility_changed !== false ||
      report.manifest_sha256 !== digestFile(`${root}/data/nac-products.json`) ||
      ["run_local_terrain.py", "science/terrain/nearfield.py"].some((name) =>
        report.implementation_sha256?.[name] !== digestFile(`${root}/${name}`)))
    throw new Error("Stale or unsupported local terrain report");
  terrainFiles.push({source,destination:`${publicData}/local-terrain/${parent.id}.json`});
}
mkdirSync(`${publicData}/local-terrain`, {recursive:true});
for (const file of terrainFiles) copyAtomic(file.source,file.destination);
copyAtomic(`${terrainRoot}/index.json`,`${publicData}/local-terrain/index.json`);
console.log("Synced confidence-aware native terrain diagnostics");
