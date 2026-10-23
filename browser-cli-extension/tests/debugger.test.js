import test from 'node:test'
import assert from 'node:assert/strict'

function installChromeStub({
  urls,
  attachImpl = async () => {},
}) {
  const sequence = Array.isArray(urls) && urls.length ? [...urls] : ['about:blank']
  let getCallCount = 0
  const attachCalls = []

  globalThis.chrome = {
    tabs: {
      async get(tabId) {
        const index = Math.min(getCallCount, sequence.length - 1)
        const url = sequence[index]
        getCallCount += 1
        return { id: tabId, url }
      },
    },
    debugger: {
      async attach(target, version) {
        attachCalls.push({ target, version })
        return await attachImpl(target, version)
      },
    },
  }

  return {
    attachCalls,
    getCallCount: () => getCallCount,
  }
}

async function loadDebuggerModule() {
  const cacheBust = `${Date.now()}-${Math.random()}`
  return await import(new URL(`../src/debugger.js?test=${cacheBust}`, import.meta.url))
}

test('ensureAttached waits for an initially blank tab URL before attaching', async (t) => {
  const chromeStub = installChromeStub({ urls: ['', '', 'about:blank'] })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await ensureAttached(17, {
    waitTimeoutMs: 25,
    pollIntervalMs: 0,
    retryCount: 1,
  })

  assert.equal(chromeStub.attachCalls.length, 1)
  assert.equal(chromeStub.attachCalls[0].target.tabId, 17)
  assert.equal(chromeStub.getCallCount(), 3)
})

test('ensureAttached retries a transient debugger attach failure', async (t) => {
  let attachAttempts = 0
  installChromeStub({
    urls: ['about:blank'],
    attachImpl: async () => {
      attachAttempts += 1
      if (attachAttempts === 1) {
        throw new Error('transient attach failure')
      }
    },
  })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await ensureAttached(23, {
    waitTimeoutMs: 0,
    pollIntervalMs: 0,
    retryCount: 2,
    retryDelayMs: 0,
  })

  assert.equal(attachAttempts, 2)
})

test('ensureAttached still rejects truly non-debuggable tabs', async (t) => {
  installChromeStub({ urls: ['chrome://newtab/'] })
  t.after(() => {
    delete globalThis.chrome
  })

  const { ensureAttached } = await loadDebuggerModule()
  await assert.rejects(
    ensureAttached(29, {
      waitTimeoutMs: 0,
      pollIntervalMs: 0,
      retryCount: 1,
    }),
    /Tab 29 is not debuggable: chrome:\/\/newtab\//,
  )
})

function captureChromeStub({ fail = false, dpr = 2, zoom = 1, images = ['aW1hZ2U='] } = {}) {
  const native = { viewport_width: 1000, viewport_height: 700, page_width: 1000, page_height: 2400, scroll_x: 0, scroll_y: 300, device_scale_factor: dpr };
  let geometry = { ...native };
  const commands = [];
  let imageIndex = 0;
  globalThis.chrome = {
    tabs: { async get(id) { return { id, url: 'https://example.com' }; }, async getZoom() { return zoom; } },
    debugger: {
      async attach() {},
      async sendCommand(_, method, params = {}) {
        commands.push({ method, params });
        if (method === 'Runtime.evaluate' && params.expression.includes('viewport_width')) return { result: { value: { ...geometry } } };
        if (method === 'Emulation.setDeviceMetricsOverride') {
          geometry = { ...geometry, viewport_width: Math.round(params.width / zoom), viewport_height: Math.round(params.height / zoom), page_width: Math.round(params.width / zoom), device_scale_factor: params.deviceScaleFactor * zoom };
        }
        if (method === 'Emulation.clearDeviceMetricsOverride') geometry = { ...native };
        if (method === 'Page.captureScreenshot') {
          if (fail) throw new Error('capture failed');
          return { data: images[Math.min(imageIndex++, images.length - 1)] };
        }
        return { result: { value: true } };
      },
    },
  };
  return { commands };
}

test('full-page screenshot keeps viewport and scales image pixels only', async (t) => {
  const stub = captureChromeStub();
  t.after(() => { delete globalThis.chrome; });
  const { captureScreenshot } = await loadDebuggerModule();
  const { capture } = await captureScreenshot(47, { fullPage: true, deviceScaleFactor: 3 });
  assert.deepEqual(capture.before, capture.after);
  assert.equal(capture.page_dimensions_unchanged, true);
  assert.equal(stub.commands.some((c) => c.method.startsWith('Emulation.')), false);
  const command = stub.commands.find((c) => c.method === 'Page.captureScreenshot');
  assert.deepEqual(command.params.clip, { x: 0, y: 0, width: 1000, height: 2400, scale: 1.5 });
});

test('temporary screenshot viewport restores an existing explicit viewport', async (t) => {
  const stub = captureChromeStub();
  t.after(() => { delete globalThis.chrome; });
  const { captureScreenshot, setViewport } = await loadDebuggerModule();
  await setViewport(48, 1200, 800);
  const { capture } = await captureScreenshot(48, { viewportWidth: 640, viewportHeight: 480 });
  assert.equal(capture.before.viewport_width, 1200);
  assert.deepEqual(capture.before, capture.after);
  assert.deepEqual(capture.viewport, { width: 640, height: 480 });
  const metrics = stub.commands.filter((c) => c.method === 'Emulation.setDeviceMetricsOverride');
  assert.equal(metrics.at(-1).params.width, 1200);
  assert.equal(stub.commands.some((c) => c.method === 'Emulation.clearDeviceMetricsOverride'), false);
});

test('capture failure still clears a temporary viewport override', async (t) => {
  const stub = captureChromeStub({ fail: true });
  t.after(() => { delete globalThis.chrome; });
  const { captureScreenshot } = await loadDebuggerModule();
  await assert.rejects(captureScreenshot(49, { viewportWidth: 640, viewportHeight: 480 }), /capture failed/);
  assert.equal(stub.commands.some((c) => c.method === 'Emulation.clearDeviceMetricsOverride'), true);
});

test('non-default browser zoom preserves CSS viewport and page DPR', async (t) => {
  const stub = captureChromeStub({dpr: 1.8, zoom: 0.9});
  t.after(() => { delete globalThis.chrome; });
  const {captureScreenshot, setViewport} = await loadDebuggerModule();
  await setViewport(50, 800, 600);
  const {capture} = await captureScreenshot(50, {viewportWidth:640, viewportHeight:480, deviceScaleFactor:2});
  assert.deepEqual(capture.before, capture.after);
  assert.equal(capture.before.device_scale_factor, 1.8);
  assert.deepEqual(capture.viewport, {width:640, height:480});
  const metrics = stub.commands.filter(c => c.method === 'Emulation.setDeviceMetricsOverride');
  assert.equal(metrics[0].params.width, 720);
  assert.equal(metrics[0].params.deviceScaleFactor, 2);
  const screenshot = stub.commands.find(c => c.method === 'Page.captureScreenshot');
  assert.deepEqual(screenshot.params.clip, {x:0, y:270, width:576, height:432, scale:2/1.8});
});

test('fractional capture bounds at browser zoom produce exact output pixels', async (t) => {
  const stub = captureChromeStub({dpr:1.8, zoom:0.9});
  let sent;
  chrome.offscreen = {async hasDocument(){return true;}};
  chrome.runtime = {async sendMessage(message){sent=message; return {ok:true,data:{data_base64:'cropped'}};}};
  t.after(() => { delete globalThis.chrome; });
  const {captureScreenshot} = await loadDebuggerModule();
  const result=await captureScreenshot(51, {clip:{x:10,y:300,width:123,height:77}, deviceScaleFactor:2});
  assert.equal(result.dataBase64, 'cropped');
  assert.equal(sent.command, 'image-crop');
  assert.equal(sent.payload.density, 2);
  assert.deepEqual(sent.payload.rectangle, {x:10,y:300,width:123,height:77});
  const screenshot=stub.commands.find(c=>c.method === 'Page.captureScreenshot');
  assert.equal(screenshot.params.format, 'png');
  assert.deepEqual(screenshot.params.clip, {x:9,y:270,width:112,height:71,scale:2/1.8});
});

test('rectangle screenshot restores ICC metadata from an un-clipped capture', async t => {
  const signature=Buffer.from([137,80,78,71,13,10,26,10]);
  const chunk=(type, bytes)=>{const length=Buffer.alloc(4);length.writeUInt32BE(bytes.length);return Buffer.concat([length,Buffer.from(type),bytes,Buffer.alloc(4)]);};
  const header=chunk('IHDR',Buffer.alloc(13));
  const profile=chunk('iCCP',Buffer.from('display-profile'));
  const end=chunk('IEND',Buffer.alloc(0));
  const raw=Buffer.concat([signature,header,end]);
  const native=Buffer.concat([signature,header,profile,end]);
  const stub=captureChromeStub({images:[raw.toString('base64'),native.toString('base64')]});
  t.after(()=>{delete globalThis.chrome;});
  const {captureScreenshot}=await loadDebuggerModule();
  const result=await captureScreenshot(52,{clip:{x:10,y:10,width:100,height:100}});
  assert.deepEqual(Buffer.from(result.dataBase64,'base64'),native);
  const calls=stub.commands.filter(c=>c.method==='Page.captureScreenshot');
  assert.equal(calls.length,2);
  assert.deepEqual(calls[1].params,{format:'png',fromSurface:true});
});

test('late screencast completion cannot reattach after the tab is released', async t => {
  let onEvent;
  let onDetach;
  let finishFrame;
  let attachments = 0;
  const commands = [];
  globalThis.chrome = {
    tabs: {async get(id) {return {id, url:'https://example.com'};}, onRemoved:{addListener() {}}},
    debugger: {
      async attach() {attachments++;},
      async detach(target) {onDetach(target);},
      async sendCommand(_, method) {commands.push(method); return {};},
      onDetach:{addListener(fn) {onDetach = fn;}},
      onEvent:{addListener(fn) {onEvent = fn;}},
    },
  };
  t.after(() => {delete globalThis.chrome;});
  const {registerDebuggerListeners, startScreencast, stopScreencast, releaseTabDebugger} = await loadDebuggerModule();
  registerDebuggerListeners();
  await startScreencast(101, {onFrame:() => new Promise(resolve => {finishFrame = resolve;})});
  onEvent({tabId:101}, 'Page.screencastFrame', {sessionId:1, data:'frame'});
  await stopScreencast(101);
  await releaseTabDebugger(101);
  finishFrame();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(attachments, 1);
  assert.equal(commands.includes('Page.screencastFrameAck'), false);
});

test('background screencast requests rendering without activating the tab and stops pumping on cleanup', async t => {
  let onEvent;
  let frames = 0;
  let captures = 0;
  let detached;
  let active = false;
  let attachments = 0;
  globalThis.chrome = {
    tabs: {async get(id) {return {id,url:'https://example.com',active};},onRemoved:{addListener() {}}},
    debugger: {
      async attach() {attachments++;},
      async detach(target) {detached(target);},
      async sendCommand(target,method,params) {
        if (method === 'Page.captureScreenshot') {
          captures++;
          assert.deepEqual(params.clip,{x:0,y:0,width:1,height:1,scale:1});
          // Chrome's hidden-page compositor only produces a frame when asked
          // to render. Exercise the same chain as the real background failure.
          onEvent(target,'Page.screencastFrame',{sessionId:captures,data:'frame'});
        }
        return {};
      },
      onDetach:{addListener(fn) {detached=fn;}},
      onEvent:{addListener(fn) {onEvent=fn;}},
    },
  };
  const {registerDebuggerListeners,startScreencast,stopScreencast,releaseTabDebugger}=await loadDebuggerModule();
  registerDebuggerListeners();
  t.after(async()=>{await stopScreencast(102);await releaseTabDebugger(102);delete globalThis.chrome;});
  await startScreencast(102,{fps:25,onFrame:()=>{frames++;}});
  for(let attempt=0;attempt<20 && !frames;attempt++) await new Promise(resolve=>setTimeout(resolve,10));
  assert.ok(frames>0,'A hidden tab must produce actual screencast frames.');
  active = true;
  const foregroundCaptures = captures;
  await new Promise(resolve=>setTimeout(resolve,80));
  assert.equal(captures,foregroundCaptures,'Visible tabs should use their native frame delivery.');
  await stopScreencast(102);
  const stoppedCaptures=captures;
  await new Promise(resolve=>setTimeout(resolve,60));
  assert.equal(captures,stoppedCaptures,'Stopping a recording must stop background rendering.');
  await releaseTabDebugger(102);
  await stopScreencast(102);
  assert.equal(attachments,1,'A late stop must not reattach the released debugger.');
});
