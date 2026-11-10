// Live extension acceptance: open the printed sentinel URL in Chrome, then POST
// /start from a terminal. This script never launches a browser or selects a tab.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdirSync, statSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {BrowserCliClient} from './browser-cli-client.mjs';

const root = resolve(process.argv[2] || 'runs/background-tab-acceptance');
const command = process.argv[3] ? resolve(process.argv[3]) : 'browser-cli';
const client = new BrowserCliClient({command, agentId:'background-tab-acceptance'});
const exec = promisify(execFile);
const ffmpeg = process.env.BROWSER_CLI_FFMPEG || 'ffmpeg';
// Browser media loading may pause in hidden tabs. Use an independent decoder
// so the live test distinguishes playback restrictions from recording failures.
await exec(ffmpeg, ['-version']);
const status = await client.status();
assert.equal(status.data.extension.connected, true, 'Connect and reload the current extension first.');
mkdirSync(root, {recursive:true});
let start;
const started = new Promise(resolve => {start = resolve;});
const observations = [];
let monitoring = false;
const phases = [];
const connections = new Set();
const server = createServer(async (req, res) => {
  if (req.url === '/observe') {
    let body = '';
    for await (const chunk of req) body += chunk;
    observations.push({...JSON.parse(body), monitoring, at:Date.now()});
    res.end('ok'); return;
  }
  if (req.url === '/start') {
    res.end('started'); start(); return;
  }
  if (req.url === '/sentinel') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(`<!doctype html><title>Browser CLI foreground sentinel</title>
      <style>body{font:20px system-ui;padding:50px;background:#f3f6f2;color:#173d2d}input{font:inherit;padding:12px}</style>
      <h1>User tab A</h1><p>This tab should stay selected while Browser CLI works in B and C.</p>
      <input aria-label="User typing" placeholder="You can keep typing here" autofocus>
      <script>
        function report(){fetch('/observe',{method:'POST',body:JSON.stringify({visible:!document.hidden,value:document.querySelector('input').value}),keepalive:true})}
        addEventListener('visibilitychange',report);setInterval(report,250);report();
      </script>`);
    return;
  }
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(`<!doctype html><title>Agent ${req.url}</title>
    <style>body{margin:0;background:#cc3333;height:2400px}input,button{font:20px system-ui;margin:20px}</style>
    <h1>Agent ${req.url}</h1><input aria-label="Agent value"><button onclick="document.querySelector('output').textContent='clicked'">Apply</button><output></output>
    <script>let n=0;setInterval(()=>{document.body.style.background=n++%2?'#33aa66':'#cc3333'},150)</script>`);
});
server.on('connection', socket => {connections.add(socket); socket.on('close', () => connections.delete(socket));});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
console.log(JSON.stringify({sentinel:base+'/sentinel', start:base+'/start'}));
const pages = new Set();
async function check(name, action) {
  const result = await action();
  // Wait for a fresh observation, so a delayed visibility event cannot be
  // mistaken for the previous phase's still-visible state.
  const completedAt = Date.now();
  for (let attempt=0;observations.at(-1)?.at<=completedAt && attempt<80;attempt++) {
    await new Promise(resolve=>setTimeout(resolve,25));
  }
  assert.ok(observations.at(-1)?.at>completedAt, `Sentinel A stopped reporting during ${name}.`);
  assert.equal(observations.at(-1)?.visible, true, `Sentinel A lost visibility during ${name}.`);
  assert.equal(observations.filter(item => item.monitoring && !item.visible).length, 0, `Sentinel A was hidden during ${name}.`);
  phases.push(name);
  console.log(JSON.stringify({passed:name}));
  return result;
}
try {
  await started;
  assert.equal(observations.at(-1)?.visible, true, 'Select sentinel A before starting.');
  monitoring = true;
  const b = await check('open-background-B', () => client.open(base+'/agent-b'));
  pages.add(b.page.page_id);
  assert.equal((await client.request('eval', {code:'() => document.visibilityState'})).data.result, 'hidden');
  const c = await check('open-background-C', () => client.open(base+'/agent-c'));
  pages.add(c.page.page_id);
  await check('select-B', () => client.request('switch-tab', {page_id:b.page.page_id}));
  assert.equal((await client.request('info')).data.page.url, base+'/agent-b');
  const snapshot = await check('snapshot-B', () => client.snapshot({interactive:true}));
  const input = snapshot.refs_summary.find(item => item.role === 'textbox');
  const button = snapshot.refs_summary.find(item => item.role === 'button');
  assert.ok(input && button);
  await check('fill-B', () => client.request('fill', {ref:input.ref, text:'background typing'}));
  await check('click-B', () => client.request('click', {ref:button.ref}));
  const values = (await client.request('eval', {code:'() => [document.querySelector("input").value,document.querySelector("output").textContent,document.visibilityState]'})).data.result;
  assert.deepEqual(values, ['background typing','clicked','hidden']);
  await check('initial-network-history', () => client.request('network-wait', {url_contains:'/agent-b', include_static:true, timeout_seconds:5}));
  const read = await check('one-shot-read', () => client.request('read-page', {url:base+'/read', output_mode:'snapshot'}));
  assert.ok(read.data.body.includes('Agent /read'));
  await check('controlled-screenshot', async () => {
    const shot = await client.screenshot(resolve(root, 'background.png'), {viewportWidth:640,viewportHeight:480,deviceScaleFactor:2});
    assert.deepEqual(shot.screenshot_size, {width:1280,height:960});
    assert.deepEqual(shot.capture.before, shot.capture.after);
  });
  await check('pdf', () => client.request('pdf', {path:resolve(root,'background.pdf')}));
  await check('trace-start', () => client.request('trace-start', {}));
  await client.request('eval', {code:'() => {document.querySelector("h1").textContent="Updated agent B"; return true}'});
  await check('trace-stop', () => client.request('trace-stop', {path:resolve(root,'background-trace.zip')}));
  const geometry = async () => (await client.request('eval', {code:'() => [innerWidth,innerHeight,scrollX,scrollY,devicePixelRatio]'})).data.result;
  const beforeVideo = await geometry();
  await check('video-start', () => client.request('video-start', {width:640,height:480}));
  // Leave enough time to verify typing in A while B is still recording.
  await client.request('wait', {seconds:5});
  await check('video-stop', () => client.request('video-stop', {path:resolve(root,'background.webm')}));
  assert.deepEqual(await geometry(), beforeVideo, 'Background video must not change page geometry.');
  const closed = await check('close-B-and-save-video', () => client.request('close-tab', {page_id:b.page.page_id}));
  pages.delete(b.page.page_id);
  assert.ok(statSync(closed.data.video_path).size > 100, 'Video must contain encoded frames.');
  await check('decode-background-video', async () => {
    const {stdout:frame} = await exec(ffmpeg, [
      '-hide_banner','-loglevel','error','-i',closed.data.video_path,
      '-ss','0.5','-frames:v','1','-vf','format=rgb24','-f','rawvideo','-pix_fmt','rgb24','pipe:1',
    ], {encoding:'buffer',maxBuffer:2*1024*1024});
    assert.equal(frame.length,640*480*3, 'Video must contain a complete RGB frame.');
    const pixel = [...frame.subarray((240*640+320)*3,(240*640+320)*3+3)];
    assert.ok(Math.max(...pixel)-Math.min(...pixel)>60,
      `Video must show the colored agent page rather than a blank frame: ${JSON.stringify(pixel)}`);
  });
  await check('close-C', () => client.request('close-tab', {page_id:c.page.page_id}));
  pages.delete(c.page.page_id);
  const report = {ok:true, phases, observations:observations.filter(item => item.monitoring), video:closed.data.video_path};
  writeFileSync(resolve(root,'background.json'), JSON.stringify(report,null,2));
  console.log(JSON.stringify({ok:true, report:resolve(root,'background.json'), video:report.video}));
} finally {
  for (const page_id of pages) await client.request('close-tab', {page_id}).catch(() => {});
  for (const socket of connections) socket.destroy();
  await new Promise(resolve => server.close(resolve));
}
