import test from 'node:test';
import assert from 'node:assert/strict';
import {getMissionInsight} from '../components/missionInsight.ts';
import {celestialRadius} from '../components/celestialGeometry.ts';
const state = (powerW, comms, earthDiskPct=100, cellTempC=28) => getMissionInsight({powerW,comms,earthDiskPct,cellTempC});
test('mission matrix covers generation, obstruction, grazing and good screening windows',()=>{
  assert.equal(state(0,0).tone,'blackout');
  assert.match(state(0,100).title,/Quiet arrays/);
  assert.match(state(200,0).title,/blocked/);
  assert.match(state(120,30).title,/grazes/);
  assert.equal(state(200,100).tone,'clear');
  assert.match(state(80,100).title,/Collecting/);
});
test('unknown inputs fail closed and thermal or partial disk cautions cannot produce green',()=>{
  assert.equal(getMissionInsight().tone,'unknown');
  for(const s of [state(NaN,100),state(-1,100),state(10,50),state(10,100,101)]) assert.equal(s.tone,'unknown');
  assert.equal(state(200,100,99).tone,'warning');
  assert.match(state(200,100,100,-100).caveat,/Unknown/);
  assert.equal(state(200,100,100,126).tone,'warning');
  assert.equal(state(200,100,100,15).tone,'clear');
});
test('celestial sphere preserves apparent angular radius and rejects invalid range',()=>{
  const r=celestialRadius(384400,.95);
  assert.ok(Math.abs(Math.asin(r/384400000)*180/Math.PI-.95)<1e-12);
  for(const [d,a] of [[0,1],[-1,1],[NaN,1],[1,90],[1,0]]) assert.equal(celestialRadius(d,a),null);
});
