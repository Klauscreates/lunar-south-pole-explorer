import test from 'node:test';
import assert from 'node:assert/strict';
import {coveredEpoch,coveredInput,COVERAGE_LAST} from '../components/coverage.ts';
test('all 13249 covered UTC epochs round-trip exactly',()=>{
  for(let i=0;i<=COVERAGE_LAST;i++) assert.equal(coveredEpoch(coveredInput(i)),i);
});
test('unsupported dates and off-grid times fail closed without rounding',()=>{
  for(const value of ['', '2026-09-30T23:50','2027-01-01T00:10','2026-10-01T00:01','2026-02-30T00:00','invalid','2026-10-01T00:00Z']) assert.equal(coveredEpoch(value),null);
  assert.equal(coveredEpoch('2026-10-01T00:00'),0);
  assert.equal(coveredEpoch('2026-10-08T00:00'),1008);
  assert.equal(coveredEpoch('2026-11-01T00:00'),4464);
  assert.equal(coveredEpoch('2026-12-01T00:00'),8784);
  assert.equal(coveredEpoch('2027-01-01T00:00'),13248);
});
