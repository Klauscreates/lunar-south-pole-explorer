import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { attitudeStatus } from '../components/attitudeStatus.ts';

const design = JSON.parse(readFileSync(new URL('../../../data/spacecraft/reference-lander-v1/design.json', import.meta.url)));
const study = { design, scenarios: design.attitudes.flatMap(p => design.boundary_cases.map(b => ({ id:`${p.id}--${b.id}`, pose_id:p.id, boundary_id:b.id }))) };
test('all ten exported R1 choices drive yaw, tilt and environmental badges', () => {
  assert.equal(study.scenarios.length, 10);
  for (const scenario of study.scenarios) {
    const state = attitudeStatus(study, scenario.id);
    const pose = design.attitudes.find(p => p.id === scenario.pose_id);
    const boundary = design.boundary_cases.find(b => b.id === scenario.boundary_id);
    assert.equal(state.heading, pose.yaw);
    assert.equal(state.isTilted, pose.pitch !== 0 || pose.roll !== 0);
    assert.equal(state.pitch, pose.pitch);
    assert.equal(state.roll, pose.roll);
    assert.equal(state.loadLabel, boundary.label);
    assert.equal(state.wall, boundary.wall_reflected_solar_irradiance_w_m2);
    assert.equal(state.ir, boundary.lunar_ir_irradiance_w_m2);
  }
  assert.equal(attitudeStatus(study, 'west--low_load').facing, 'West');
  assert.equal(attitudeStatus(study, 'north_tilted--added_load').isAddedLoad, true);
});
test('unavailable or invalid metadata stays Unknown instead of defaulting north', () => {
  assert.equal(attitudeStatus(undefined, 'north--low_load'), null);
  assert.equal(attitudeStatus(study, 'northeast--low_load'), null);
  const invalid = structuredClone(study);
  invalid.design.attitudes[0].yaw = NaN;
  assert.equal(attitudeStatus(invalid, 'north--low_load'), null);
});
