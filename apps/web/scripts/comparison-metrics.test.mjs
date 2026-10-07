import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cellReference, comparisonSeries, terrainEvidence, EPOCHS, epochTime } from '../components/comparisonMetrics.ts';
import { weeklyMetrics } from '../components/weeklyMetrics.ts';
const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url)));
const catalogue = read('../public/data/simulation-index.json');
test('all 66245 indexed site epochs and ten R1 scenarios align; cumulative energy matches integration', () => {
  let count = 0;
  for (const site of catalogue.sites) {
    const simulation = read(`../public${site.data_url}`);
    const study = read(`../public/data/spacecraft/${site.id}.json`);
    count += simulation.samples.length;
    for (const scenario of study.scenarios) {
      const series = comparisonSeries(simulation, study, scenario.id);
      assert.ok(series);
      assert.equal(series.cumulative[0], 0);
      assert.ok(Math.abs(series.cumulative[EPOCHS - 1] - weeklyMetrics(study, scenario.id).kwh) < 1e-9);
      const months = [[0,4464],[4464,8784],[8784,13248]].map(([start,end])=>weeklyMetrics(study,scenario.id,start,end));
      assert.ok(months.every(Boolean));
      assert.ok(Math.abs(months.reduce((sum,m)=>sum+m.kwh,0)-series.cumulative[EPOCHS-1])<1e-8);
      assert.ok(Math.abs(months.reduce((sum,m)=>sum+m.hours,0)-2208)<1e-8);
      for (let i = 1; i < EPOCHS; i++) assert.ok(series.cumulative[i] >= series.cumulative[i - 1]);
    }
  }
  assert.equal(count, 66245);
  assert.equal(epochTime(1008), '2026-10-08T00:00:00.000Z');
});
test('XTJ cell reference respects both manufacturer coefficient limits and 28C reference', () => {
  assert.equal(cellReference(288.149), null);
  assert.equal(cellReference(398.151), null);
  assert.equal(cellReference(NaN), null);
  assert.ok(cellReference(288.15) > 0);
  assert.ok(cellReference(398.15) > 0);
  assert.equal(cellReference(301.15), .307);
});
test('mismatched timestamps and missing scenarios fail closed', () => {
  const simulation = read('../public/data/simulation.json');
  const study = read('../public/data/spacecraft/test-site-a.json');
  assert.equal(comparisonSeries(simulation, study, 'missing'), null);
  study.timestamps[1] = study.timestamps[0];
  assert.equal(comparisonSeries(simulation, study, study.scenarios[0].id), null);
});
test('trafficability never substitutes 50m roughness for missing 500m or unqualified slopes', () => {
  const ridge = terrainEvidence(read('../public/data/local-terrain/connecting-ridge.json'));
  assert.ok(ridge.slope > 0);
  assert.equal(ridge.roughness, null);
  assert.equal(ridge.complete, false);
  assert.equal(terrainEvidence(read('../public/data/local-terrain/haworth.json')).slope, null);
  assert.equal(terrainEvidence().complete, false);
});
