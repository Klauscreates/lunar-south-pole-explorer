import {test} from 'node:test';
import assert from 'node:assert/strict';
import {panDistance,installTouchNavigation} from '../components/touchNavigation.ts';
test('pan follows the finger in four directions at zoom-relative scale',()=>{
  assert.ok(panDistance(10,0,1000,1,800).right<0);
  assert.ok(panDistance(-10,0,1000,1,800).right>0);
  assert.ok(panDistance(0,10,1000,1,800).up>0);
  assert.ok(panDistance(0,-10,1000,1,800).up<0);
  assert.equal(panDistance(10,0,2000,1,800).right,2*panDistance(10,0,1000,1,800).right);
  for(const args of [[NaN,0,1,1,800],[1,1,1,1,0],[1,1,Infinity,1,800],[1,1,1,Math.PI,800],[900,0,1,1,800]]) assert.equal(panDistance(...args),null);
});
test('single touch pans or looks in both views; pinch stays native; cleanup removes handlers',()=>{
  const listeners=new Map(); const canvas={addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name),setPointerCapture:()=>{}};
  let mode='pan',interrupts=0; const pans=[],rotations=[],looks=[];
  const cleanup=installTouchNavigation(canvas,{mode:()=>mode,interrupt:()=>interrupts++,rotate:v=>rotations.push(v),pan:(x,y)=>pans.push([x,y]),look:(x,y)=>looks.push([x,y])});
  const event=(pointerId,x,y)=>({pointerId,clientX:x,clientY:y,pointerType:'touch'});
  listeners.get('pointerdown')(event(1,10,10)); listeners.get('pointermove')(event(1,20,30));
  assert.deepEqual(pans,[[10,20]]); assert.equal(rotations[0],false);
  listeners.get('pointerdown')(event(2,40,40)); listeners.get('pointermove')(event(1,25,30)); assert.equal(pans.length,1);
  listeners.get('pointerup')(event(2,40,40)); listeners.get('pointermove')(event(1,30,30)); assert.deepEqual(pans[1],[5,0]);
  mode='look'; listeners.get('pointermove')(event(1,40,35)); assert.deepEqual(looks,[[10,5]]);
  listeners.get('pointerdown')({...event(3,0,0),pointerType:'mouse'}); assert.equal(rotations.at(-1),true);
  assert.equal(interrupts,3); cleanup(); assert.equal(listeners.size,0);
});
