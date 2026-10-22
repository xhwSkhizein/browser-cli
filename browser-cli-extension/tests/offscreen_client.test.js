import test from 'node:test';
import assert from 'node:assert/strict';
import {ensureOffscreenDocument} from '../src/offscreen_client.js';

test('concurrent screenshot and video requests create one offscreen document', async t => {
  let creations = 0;
  let finish;
  globalThis.chrome = {offscreen:{
    Reason:{DISPLAY_MEDIA:'DISPLAY_MEDIA', BLOBS:'BLOBS'},
    async hasDocument(){return false;},
    createDocument(){creations++; return new Promise(resolve => {finish=resolve;});},
  }};
  t.after(() => {delete globalThis.chrome;});
  const screenshot = ensureOffscreenDocument();
  const video = ensureOffscreenDocument();
  await new Promise(setImmediate);
  assert.equal(creations,1);
  finish();
  await Promise.all([screenshot,video]);
});
