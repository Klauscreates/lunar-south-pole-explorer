import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {CELESTIAL_TEXTURES} from '../components/celestialAppearance.ts';
const root=new URL('../public/celestial/',import.meta.url);
const manifest=JSON.parse(readFileSync(new URL('texture-manifest.json',root)));
function jpegDimensions(bytes){
  assert.equal(bytes.readUInt16BE(0),0xffd8);
  for(let i=2;i+8<bytes.length;){
    assert.equal(bytes[i],0xff);
    const marker=bytes[i+1],length=bytes.readUInt16BE(i+2);
    if([0xc0,0xc1,0xc2].includes(marker))return [bytes.readUInt16BE(i+7),bytes.readUInt16BE(i+5)];
    assert.ok(length>=2);i+=length+2;
  }
  throw new Error('JPEG dimensions unavailable');
}
test('all rendered celestial maps are genuine 4096x2048 assets with pinned provenance',()=>{
  assert.equal(manifest.assets.length,3);
  for(const asset of manifest.assets){
    const bytes=readFileSync(new URL(asset.file,root));
    assert.deepEqual(jpegDimensions(bytes),[4096,2048]);
    assert.equal(createHash('sha256').update(bytes).digest('hex'),asset.sha256);
    assert.ok(asset.source_width>=asset.width && asset.source_height>=asset.height);
    assert.ok(Object.values(CELESTIAL_TEXTURES).includes('/celestial/'+asset.file));
  }
  assert.equal(manifest.license,'CC BY 4.0');
});
