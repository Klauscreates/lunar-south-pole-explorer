import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sharedResource} from '../components/sharedResource.ts';

test('concurrent and repeated panels reuse one verified resource', async()=>{
  const cache=sharedResource(); let calls=0;
  const load=async()=>{calls++; return {verified:true};};
  const signal=new AbortController().signal;
  const [a,b]=await Promise.all([cache('site:hash',load,signal),cache('site:hash',load,signal)]);
  assert.equal(a,b); assert.equal(await cache('site:hash',load,signal),a); assert.equal(calls,1);
  await cache('site:new-hash',load,signal); assert.equal(calls,2);
});
test('cancelled subscriber cannot cancel another panel',async()=>{
  const cache=sharedResource(); const a=new AbortController(),b=new AbortController();
  let finish; const load=()=>new Promise(resolve=>{finish=resolve;});
  const first=cache('site',load,a.signal), second=cache('site',load,b.signal);
  await Promise.resolve(); a.abort(); finish(42);
  await assert.rejects(first,{name:'AbortError'}); assert.equal(await second,42);
});
test('failure evicts and retries; cache has bounded retention',async()=>{
  const cache=sharedResource(2), signal=new AbortController().signal; let calls=0;
  await assert.rejects(cache('bad',async()=>{throw Error('checksum');},signal),/checksum/);
  assert.equal(await cache('bad',async()=>42,signal),42);
  const load=async()=>++calls;
  await cache('a',load,signal); await cache('b',load,signal);
  await cache('c',load,signal); await cache('a',load,signal); assert.equal(calls,4);
});
