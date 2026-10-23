import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {BrowserCliClient} from './browser-cli-client.mjs';

const root = resolve(process.argv[2] || 'runs/runtime-api-acceptance');
const command = process.argv[3] ? resolve(process.argv[3]) : 'browser-cli';
const client = new BrowserCliClient({command});
// Reuse the existing service/extension; this script never launches Chrome.
const status = await client.status();
assert.ok(status.data.extension.details.capabilities.includes('screenshot-controls'), 'Reload the extension to enable screenshot-controls.');
mkdirSync(root, {recursive:true});
const connections = new Set();
const server = createServer((req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end('<!doctype html><html><head><style>body{margin:0;height:2400px;background:linear-gradient(#eee,#789)}h1{margin:0;padding:40px}#crop{position:absolute;left:10px;top:300px;width:123px;height:77px;background:rgb(255,0,0)}</style></head><body><h1>Browser CLI extension acceptance</h1><div id="crop"></div></body></html>');
});
server.on('connection', socket => { connections.add(socket); socket.on('close', () => connections.delete(socket)); });
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const cases = [];
const colorChecks = [];
let cropReference;

async function imageSamples(png, points) {
  const source = `data:image/${png[0] === 0xff ? 'jpeg' : 'png'};base64,${png.toString('base64')}`;
  return (await client.request('eval', {code:`() => new Promise(resolve => {
    const image = new Image(); image.onload = () => {
      const canvas = document.createElement('canvas'); canvas.width=image.width; canvas.height=image.height;
      const ctx=canvas.getContext('2d'); ctx.drawImage(image,0,0);
      resolve(${JSON.stringify(points)}.map(([x,y])=>Array.from(ctx.getImageData(x,y,1,1).data)));
    }; image.src=${JSON.stringify(source)};
  })`})).data.result;
}
let opened = false;
try {
  await client.open(`http://127.0.0.1:${server.address().port}/`);
  opened = true;
  const native = await client.request('screenshot', {path:resolve(root, 'native-temp.png'), viewport_width:640, viewport_height:480, device_scale_factor:2});
  assert.equal(native.meta.driver, 'extension');
  assert.deepEqual(native.data.screenshot_size, {width:1280, height:960});
  assert.deepEqual(native.data.capture.before, native.data.capture.after);
  cases.push({name:'native-temp', ...native.data});
  await client.request('resize', {width:800, height:600});
  await client.request('eval', {code:'() => {scrollTo(0,300);return true}'});
  for (const [name, args, width, height] of [
    ['viewport', {device_scale_factor:1}, 800, 600],
    ['viewport-dpr2', {device_scale_factor:2}, 1600, 1200],
    ['full', {full_page:true, device_scale_factor:2}, 1600, 4800],
    ['clip', {clip:{x:10,y:300,width:123,height:77}, device_scale_factor:2}, 246, 154],
    ['clip-jpeg', {clip:{x:10,y:300,width:123,height:77}, device_scale_factor:2}, 246, 154],
    ['fixed', {viewport_width:640, viewport_height:480, device_scale_factor:2}, 1280, 960],
    ['fixed-jpeg', {viewport_width:640, viewport_height:480, device_scale_factor:2}, 1280, 960],
  ]) {
    const result = await client.request('screenshot', {path:resolve(root, name + (name.endsWith('jpeg') ? '.jpg' : '.png')), ...args});
    assert.equal(result.meta.driver, 'extension');
    assert.deepEqual(result.data.screenshot_size, {width, height});
    assert.deepEqual(result.data.capture.before, result.data.capture.after);
    assert.equal(result.data.capture.after.viewport_width, 800);
    assert.equal(result.data.capture.after.scroll_y, 300);
    if (!name.endsWith('jpeg')) {
      const png = readFileSync(result.data.path);
      assert.equal(png.readUInt32BE(16), width);
      assert.equal(png.readUInt32BE(20), height);
      if (name === 'full') {
        [cropReference] = await imageSamples(png, [[40,640]]);
        assert.ok(cropReference[0] > 200 && cropReference[1] < 100 && cropReference[2] < 100);
      }
      if (name === 'clip') {
        const samples = await imageSamples(png, [[2,2],[width-3,height-3]]);
        assert.deepEqual(samples, [cropReference, cropReference], 'clip must cover the requested CSS rectangle and preserve its colors');
        colorChecks.push({format:'png',reference:cropReference,samples,tolerance:0});
      }
    }
    if (name === 'clip-jpeg') {
      // JPEG chroma subsampling blends boundary pixels; compare solid interior.
      const samples = await imageSamples(readFileSync(result.data.path), [
        [Math.floor(width/4),Math.floor(height/4)], [Math.floor(3*width/4),Math.floor(3*height/4)],
      ]);
      assert.ok(samples.every(pixel => pixel.every((value,index) => Math.abs(value-cropReference[index]) <= 8)),
        `JPEG crop must preserve the reference colors within compression tolerance: ${JSON.stringify({samples,reference:cropReference})}`);
      colorChecks.push({format:'jpeg',reference:cropReference,samples,tolerance:8});
    }
    cases.push({name, ...result.data});
  }
  const report = resolve(root, 'extension.json');
  writeFileSync(report, JSON.stringify({ok:true, runtime_version:status.data.runtime_version, cases, color_checks:colorChecks}, null, 2));
  console.log(JSON.stringify({ok:true, driver:'extension', cases:cases.map(c => ({name:c.name, size:c.screenshot_size})), report}, null, 2));
} finally {
  try { if (opened) await client.close(); }
  finally {
    for (const socket of connections) socket.destroy();
    await new Promise(resolve => server.close(resolve));
  }
}
