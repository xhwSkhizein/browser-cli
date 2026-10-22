import test from 'node:test';
import assert from 'node:assert/strict';
import {cropImage} from '../src/offscreen_image.js';

test('image crop uses DOM image decoding, exact dimensions, and sRGB output', async t => {
  let draw;
  const canvas = {
    getContext(type, options) {
      assert.deepEqual(options, {colorSpace:'srgb'});
      return {drawImage(...args){draw=args.slice(1);}};
    },
    toDataURL(type) { assert.equal(type,'image/png'); return 'data:image/png;base64,cropped'; },
  };
  globalThis.Image = class { set src(value){assert.equal(value,'data:image/png;base64,source'); this.onload();} };
  globalThis.document = {createElement(type){assert.equal(type,'canvas'); return canvas;}};
  t.after(() => {delete globalThis.Image; delete globalThis.document;});
  const result=await cropImage('source', {
    rectangle:{x:10,y:300,width:123,height:77}, enclosing:{x:9,y:270,width:112,height:71},
    zoom:0.9, density:2, format:'png',
  });
  assert.equal(canvas.width,246);
  assert.equal(canvas.height,154);
  assert.deepEqual(draw,[0,0,246,154,0,0,246,154]);
  assert.equal(result.data_base64,'cropped');
});

test('image decode errors fail without encoding a screenshot', async t => {
  globalThis.Image = class {set src(value){this.onerror();}};
  t.after(() => {delete globalThis.Image;});
  await assert.rejects(cropImage('invalid', {}), /Could not decode/);
});
