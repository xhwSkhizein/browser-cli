import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtempSync, rmSync, writeFileSync, readFileSync, readdirSync, mkdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { BrowserCliClient, BrowserCliError, writeJsonArtifact } from '../browser-cli-client.mjs';

const runtimeVersion = '2026-10-22-capture-context-batch-v2';

async function daemon(t, handle, clientOptions = {}) {
  const { daemonRuntimeVersion = () => runtimeVersion, rejectRuntime = false, ...options } = clientOptions;
  const dir = mkdtempSync('/tmp/bcli-node-');
  const path = join(dir, 'daemon.sock');
  const connections = new Set();
  const server = createServer((socket) => {
    connections.add(socket);
    socket.on('close', () => connections.delete(socket));
    let input = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => {
      input += chunk;
      if (input.includes('\n')) {
        const request = JSON.parse(input.split('\n')[0]);
        if (request.action === 'runtime-status' && !request.args.warmup
          && Object.keys(request.args).every(key => key === 'warmup')) {
          const payload = rejectRuntime
            ? {ok:false, data:{}, meta:{runtime_version:daemonRuntimeVersion()}, error_code:'DAEMON_INCOMPATIBLE'}
            : success({ runtime_version: daemonRuntimeVersion() });
          socket.end(JSON.stringify(payload) + '\n');
        } else handle(request, socket);
      }
    });
  });
  await new Promise((resolve) => server.listen(path, resolve));
  t.after(async () => {
    for (const socket of connections) socket.destroy();
    await new Promise((resolve) => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  });
  return { dir, path, client: new BrowserCliClient({ socketPath: path, ...options }) };
}

const success = (data = {}) => ({ ok: true, data, meta: { action: 'eval', runtime_version: runtimeVersion } });

test('status configuration reaches the daemon instead of being replaced by the compatibility probe', async t => {
  const requests = [];
  const {client} = await daemon(t, (request, socket) => {
    requests.push(request);
    socket.end(JSON.stringify(success({runtime_version:runtimeVersion, profile_dir:'/test/profile'})) + '\n');
  });
  const args = {chrome_environment:{executable_path:'/test/chrome-headless-shell', user_data_dir:'/test/profile'}};
  const result = await client.request('runtime-status', args);
  assert.equal(requests.length, 1, 'Browser configuration was swallowed and the next action can launch desktop Chrome');
  assert.deepEqual(requests[0].args, args);
  assert.equal(result.data.profile_dir, '/test/profile');
  await client.status();
  assert.equal(requests.length, 1, 'Plain status reads should still reuse the compatibility probe');
});

test('requests share an agent, preserve envelopes, and accept chunked UTF-8 JSON', async (t) => {
  const requests = [];
  const { client } = await daemon(t, (request, socket) => {
    requests.push(request);
    const bytes = Buffer.from(JSON.stringify(success({ title: '截图' })) + '\n');
    for (const byte of bytes) socket.write(Buffer.from([byte]));
  });
  assert.deepEqual(await client.request('eval', { code: '() => document.title' }), success({ title: '截图' }));
  await client.open('https://example.com');
  assert.equal(requests[0].agent_id, requests[1].agent_id);
  assert.notEqual(requests[0].request_id, requests[1].request_id);
  assert.notEqual(new BrowserCliClient().agentId, client.agentId);
});

test('batch forwards context, compact results, and preserves step failures', async (t) => {
  let request;
  const { client } = await daemon(t, (input, socket) => {
    request = input;
    socket.end(JSON.stringify(success({ success: false, failed_indices: [1], results: [{ ok: false, error_code: 'INVALID_INPUT' }] })) + '\n');
  });
  const commands = [{ action: 'open', args: { url: 'https://example.com' } }];
  await assert.rejects(client.batch(commands, { context: { locale: 'zh-CN' }, resultMode: 'summary', stopOnError: false }), error => {
    assert.equal(error.code, 'BATCH_FAILED');
    assert.equal(error.payload.ok, true);
    assert.equal(error.payload.data.success, false);
    assert.deepEqual(error.payload.data.failed_indices, [1]);
    return true;
  });
  assert.equal(request.action, 'batch');
  assert.deepEqual(request.args, { commands, context: { locale: 'zh-CN' }, result_mode: 'summary', stop_on_error: false });
  const response = await client.request('batch', { commands });
  assert.equal(response.data.success, false, 'Raw requests preserve partial results without throwing');
});

test('JSON artifacts preserve complete Unicode data and describe saved bytes', t => {
  const dir = mkdtempSync('/tmp/bcli-export-');
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const value = [{ title: '中文 "quotes" \\ newline\n'.repeat(20_000), url: 'https://example.com/?signed=private' }];
  const path = join(dir, 'nested', '完整结果.json');
  const info = writeJsonArtifact(path, value);
  const bytes = readFileSync(path);
  assert.ok(bytes.length > 200_000);
  assert.deepEqual(JSON.parse(bytes.toString('utf8')), value);
  assert.deepEqual(info, {path, bytes:bytes.length, sha256:createHash('sha256').update(bytes).digest('hex'), result_type:'array'});
  assert.equal(statSync(path).mode & 0o777, 0o600);
});

test('artifact failures preserve the existing destination and remove temporary files', t => {
  const dir = mkdtempSync('/tmp/bcli-export-');
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'result.json');
  writeFileSync(path, 'previous');
  assert.throws(() => writeJsonArtifact(path, 1n), error => error.code === 'OUTPUT_WRITE_FAILED');
  assert.equal(readFileSync(path, 'utf8'), 'previous');
  const directory = join(dir, 'directory');
  mkdirSync(directory);
  assert.throws(() => writeJsonArtifact(directory, {}), error => error.code === 'OUTPUT_WRITE_FAILED');
  assert.deepEqual(readdirSync(dir).sort(), ['directory', 'result.json']);
});

test('daemon errors keep machine-readable codes and payloads', async (t) => {
  const error = { ok: false, data: {}, meta: {runtime_version: runtimeVersion}, error_code: 'NO_ACTIVE_TAB', error_message: 'No active tab.' };
  const { client } = await daemon(t, (_, socket) => socket.end(JSON.stringify(error) + '\n'));
  await assert.rejects(client.snapshot(), (failure) => failure instanceof BrowserCliError && failure.code === 'NO_ACTIVE_TAB' && failure.payload.error_message === 'No active tab.');
});

test('timeouts and disconnected actions are never replayed', async (t) => {
  let calls = 0;
  const { client } = await daemon(t, (_, socket) => {
    calls++;
    if (calls === 1) socket.end();
  }, { timeoutMs: 25, command: '/nonexistent-browser-cli' });
  await assert.rejects(client.request('click', { ref: 'abcd' }), /may have run/);
  await assert.rejects(client.request('click', { ref: 'abcd' }), (error) => error.code === 'CLIENT_TIMEOUT');
  assert.equal(calls, 2);
});

test('malformed and oversized responses fail predictably', async (t) => {
  let calls = 0;
  const { client } = await daemon(t, (_, socket) => {
    socket.end(calls++ === 0 ? '{broken\n' : 'x'.repeat(2048));
  }, { maxResponseBytes: 1024 });
  await assert.rejects(client.request('info'), (error) => error.code === 'INVALID_RESPONSE');
  await assert.rejects(client.request('info'), /maxResponseBytes/);
});

test('discovers the actual socket once, including hashed paths for long homes', async (t) => {
  const { dir, path } = await daemon(t, (_, socket) => socket.end(JSON.stringify(success()) + '\n'));
  const script = join(dir, 'browser-cli');
  const calls = join(dir, 'calls');
  writeFileSync(script, `#!${process.execPath}\nimport { appendFileSync } from 'node:fs';\nappendFileSync(${JSON.stringify(calls)}, process.argv.slice(2).join(' ') + '\\n');\nconsole.log(${JSON.stringify(JSON.stringify(success({ socket_path: path })))});\n`, { mode: 0o700 });
  // .mjs avoids relying on the parent directory's package type.
  const esmScript = script + '.mjs';
  writeFileSync(esmScript, readFileSync(script), { mode: 0o700 });
  const client = new BrowserCliClient({ command: esmScript, home: join(dir, 'long'.repeat(40)) });
  await client.request('info');
  await client.request('info');
  assert.equal(client.socketPath, path);
  assert.equal(readFileSync(calls, 'utf8'), 'paths --json\n');
});

test('screenshot aliases map to explicit daemon controls', async (t) => {
  let args;
  const { client } = await daemon(t, (request, socket) => {
    args = request.args;
    socket.end(JSON.stringify(success({ screenshot_size: { width: 1600, height: 1200 } })) + '\n');
  });
  await client.screenshot('capture.png', { pageRange: 'full', viewportWidth: 800, viewportHeight: 600, deviceScaleFactor: 2 });
  assert.deepEqual(args, { path: 'capture.png', full_page: true, viewport_width: 800, viewport_height: 600, device_scale_factor: 2 });
});

for (const version of [undefined, 'old-runtime']) {
  test(`rejects incompatible daemon ${version} before any browser action`, async (t) => {
    let actions = 0;
    const { client } = await daemon(t, (_, socket) => {
      actions++;
      socket.end(JSON.stringify(success()) + '\n');
    }, { daemonRuntimeVersion: () => version });
    await assert.rejects(client.open('https://example.com'), (error) =>
      error.code === 'DAEMON_INCOMPATIBLE' && /reload/.test(error.message) &&
      error.payload.expected_runtime_version === runtimeVersion);
    assert.equal(actions, 0);
  });
}

test('checks compatibility again when a daemon at the same socket is replaced', async (t) => {
  let version = runtimeVersion;
  let actions = 0;
  const { client } = await daemon(t, (_, socket) => {
    actions++;
    socket.end(JSON.stringify(success()) + '\n');
  }, { daemonRuntimeVersion: () => version });
  await client.open('https://example.com');
  version = 'old-runtime';
  await assert.rejects(client.screenshot('capture.png'), (error) => error.code === 'DAEMON_INCOMPATIBLE');
  assert.equal(actions, 1);
});

test('version rejection by a newer daemon keeps both versions and reload guidance', async (t) => {
  const {client} = await daemon(t, () => assert.fail('No browser action may be sent'), {
    daemonRuntimeVersion:()=> 'newer-runtime', rejectRuntime:true,
  });
  await assert.rejects(client.open('https://example.com'), error =>
    error.code === 'DAEMON_INCOMPATIBLE' && error.payload.actual_runtime_version === 'newer-runtime' &&
    error.payload.expected_runtime_version === runtimeVersion && /reload/.test(error.message));
});


test('retries failed paths discovery and shares concurrent attempts', async (t) => {
  const { dir, path } = await daemon(t, (_, socket) => socket.end(JSON.stringify(success()) + '\n'));
  const script = join(dir, 'retry-paths.mjs');
  const calls = join(dir, 'path-calls');
  writeFileSync(script, `#!${process.execPath}\nimport { appendFileSync, existsSync } from 'node:fs';\nconst first = !existsSync(${JSON.stringify(calls)});\nappendFileSync(${JSON.stringify(calls)}, 'paths\\n');\nif (first) { console.error('temporary discovery failure'); process.exit(1); }\nconsole.log(${JSON.stringify(JSON.stringify(success({ socket_path: path })))});\n`, { mode: 0o700 });
  const client = new BrowserCliClient({ command: script });
  const failed = await Promise.allSettled([client.request('info'), client.request('info')]);
  for (const result of failed) {
    assert.equal(result.status, 'rejected');
    assert.match(result.reason.message, /temporary discovery failure/);
  }
  assert.equal(readFileSync(calls, 'utf8'), 'paths\n');
  await Promise.all([client.request('info'), client.request('info')]);
  await client.request('info');
  assert.equal(client.socketPath, path);
  assert.equal(readFileSync(calls, 'utf8'), 'paths\npaths\n');
});
