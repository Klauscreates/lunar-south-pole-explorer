import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { qualifiedTerrainRay } from "../components/terrainGauge.ts";

const report = JSON.parse(readFileSync(new URL("../../../outputs/local-terrain/connecting-ridge.json", import.meta.url)));
const evaluate = (r, body = "earth", index = 0, time = report.samples[index].timestamp) =>
  qualifiedTerrainRay(r, report.site_id, report.parent_sha256, index, time, body);
test("registered clear Earth uses corrected geometry, not baseline", () => {
  const result = evaluate(report);
  assert.equal(result.status, "Clear");
  assert.equal(result.elevation, report.samples[0].earth.target_elevation_deg);
  assert.equal(result.clearance, result.elevation - result.horizon);
});
test("missing, wrong site, stale parent, wrong epoch and rejected registration fail closed", () => {
  for (const value of [null, {...report, site_id: "other"}, {...report, parent_sha256: "stale"},
    {...report, confidence_qualified: false}, {...report, coregistration: {applied: false}},
    {...report, samples: []}]) assert.equal(evaluate(value), null);
  assert.equal(evaluate(report, "earth", 0, "wrong epoch"), null);
});
test("incomplete or nonfinite rays are Unknown even if obstruction is reported", () => {
  assert.equal(evaluate(report, "sun"), null);
  for (const patch of [{complete: false, status: "BLOCKED"}, {horizon_deg: NaN}, {status: "UNKNOWN"}]) {
    const copy = structuredClone(report);
    Object.assign(copy.samples[0].earth.fused, patch);
    assert.equal(evaluate(copy), null);
  }
});
test("all exported epochs obey coverage gate, including known blocked epochs", () => {
  let blocked = 0;
  for (let i = 0; i < report.samples.length; i++) for (const body of ["sun", "earth"]) {
    const ray = report.samples[i][body];
    const result = evaluate(report, body, i);
    if (!ray.fused.complete || ray.fused.status === "UNKNOWN") assert.equal(result, null);
    if (result?.status === "Blocked") blocked++;
  }
  assert.ok(blocked > 0);
});
