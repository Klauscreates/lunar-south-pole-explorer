import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validateOrbitalData,displayPosition,earthTextureMatrix} from '../components/orbitalData.ts';
const bytes=readFileSync(new URL('../../../outputs/orbital-scene.json',import.meta.url));
const source=JSON.parse(bytes);
test('orbital export integrity, complete time grid and all proper rotation matrices',()=>{
  const manifest=JSON.parse(readFileSync(new URL('../../../outputs/orbital-index.json',import.meta.url)));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.sha256);
  assert.equal(validateOrbitalData(source).samples.length,13249);
  assert.equal(source.samples[1008].utc,'2026-10-08T00:00:00Z');
  assert.equal(source.samples.at(-1).utc,'2027-01-01T00:00:00Z');
  assert.notDeepEqual(source.samples[0].earth_fixed_to_scene,source.samples[1].earth_fixed_to_scene);
});
test('bad frame, missing epochs and reflected matrices fail closed',()=>{
  assert.throws(()=>validateOrbitalData({...source,frame:'J2000'}));
  assert.throws(()=>validateOrbitalData({...source,samples:source.samples.slice(1)}));
  const changed=structuredClone(source);
  changed.samples[0].earth_fixed_to_scene[0]=NaN;
  assert.throws(()=>validateOrbitalData(changed));
  changed.samples[0].earth_fixed_to_scene=[-1,0,0,0,1,0,0,0,1];
  assert.throws(()=>validateOrbitalData(changed));
});
test('true-scale positions preserve km to meter units and overview preserves directions only',()=>{
  const p=source.samples[0].earth_km;
  assert.deepEqual(displayPosition(p,'true-scale','earth'),p.map(x=>x*1000));
  const q=displayPosition(p,'overview','earth');
  assert.ok(Math.abs(Math.hypot(...q)-12*1737400)<1e-6);
  for(let i=0;i<3;i++)assert.ok(Math.abs(q[i]/Math.hypot(...q)-p[i]/Math.hypot(...p))<1e-12);
  assert.deepEqual(earthTextureMatrix([1,0,0,0,1,0,0,0,1]).map(v=>v||0),[-1,0,0,0,-1,0,0,0,1]);
});
