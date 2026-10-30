import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { closeSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { createConnection } from 'node:net';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const DAEMON_RUNTIME_VERSION = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf8'),
).browserCliRuntimeVersion;

export class BrowserCliError extends Error {
  constructor(message, payload = {}) {
    super(message);
    this.name = 'BrowserCliError';
    this.code = payload.error_code || 'BROWSER_CLI_ERROR';
    this.payload = payload;
  }
}

/** Write the complete JSON value locally and return a compact file descriptor. */
export function writeJsonArtifact(path, value) {
  let temporary;
  let descriptor;
  try {
    const serialized = JSON.stringify(value, (_key, item) => {
      if ((typeof item === 'number' && !Number.isFinite(item))
        || item === undefined || ['bigint', 'function', 'symbol'].includes(typeof item)) {
        throw new TypeError('Value cannot be represented as complete JSON.');
      }
      return item;
    }, 2);
    if (serialized === undefined) throw new TypeError('Value cannot be represented as JSON.');
    const content = Buffer.from(`${serialized}\n`, 'utf8');
    const destination = resolve(path);
    mkdirSync(dirname(destination), { recursive: true });
    temporary = join(dirname(destination), `.browser-cli-${randomUUID()}.tmp`);
    descriptor = openSync(temporary, 'wx', 0o600);
    writeFileSync(descriptor, content);
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    renameSync(temporary, destination);
    temporary = undefined;
    const resultType = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
    return { path: destination, bytes: content.length, sha256: createHash('sha256').update(content).digest('hex'), result_type: resultType };
  } catch (error) {
    throw new BrowserCliError(`Cannot save JSON artifact: ${error.message}`, { error_code: 'OUTPUT_WRITE_FAILED' });
  } finally {
    if (descriptor !== undefined) { try { closeSync(descriptor); } catch {} }
    if (temporary !== undefined) {
      try { unlinkSync(temporary); } catch {}
    }
  }
}

/** One client owns an agent's active tab. Browser actions use the daemon socket. */
export class BrowserCliClient {
  constructor({
    home = process.env.BROWSER_CLI_HOME || join(homedir(), '.browser-cli'),
    socketPath,
    agentId = process.env.X_AGENT_ID || `node-${randomUUID()}`,
    command = 'browser-cli',
    timeoutMs = 120_000,
    startupTimeoutMs = 30_000,
    maxResponseBytes = 32 * 1024 * 1024,
  } = {}) {
    for (const [name, value] of Object.entries({ timeoutMs, startupTimeoutMs, maxResponseBytes })) {
      if (!Number.isSafeInteger(value) || value <= 0) throw new TypeError(`${name} must be a positive integer.`);
    }
    if (typeof agentId !== 'string' || !agentId.trim()) throw new TypeError('agentId must be a non-empty string.');
    this.home = home;
    this.socketPath = socketPath;
    this.agentId = agentId;
    this.command = command;
    this.timeoutMs = timeoutMs;
    this.startupTimeoutMs = startupTimeoutMs;
    this.maxResponseBytes = maxResponseBytes;
    this._pathsPromise = undefined;
    this._startupPromise = undefined;
  }

  async request(action, args = {}, { startIfNeeded = true, timeoutMs = this.timeoutMs } = {}) {
    if (typeof action !== 'string' || !action.trim() || !isObject(args)) {
      throw new TypeError('request requires an action string and an args object.');
    }
    if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be a positive integer.');
    await this.#resolveSocket();
    const request = { action, args, agent_id: this.agentId, request_id: randomUUID().replaceAll('-', ''), runtime_version: DAEMON_RUNTIME_VERSION };
    let payload;
    try {
      payload = await this.#sendChecked(request, timeoutMs);
    } catch (error) {
      // These errors occur before a connection is established. Never replay an action
      // after a timeout, disconnect, or malformed response: it may already have run.
      if (!startIfNeeded || !['ENOENT', 'ECONNREFUSED'].includes(error.code)) throw error;
      await this.ensureStarted();
      payload = await this.#sendChecked(request, timeoutMs);
    }
    if (!payload.ok) throw new BrowserCliError(payload.error_message || 'Daemon command failed.', payload);
    return payload;
  }

  async batch(commands, { context, stopOnError = true, resultMode = 'all', ...requestOptions } = {}) {
    if (!Array.isArray(commands) || commands.length < 1 || commands.length > 500) {
      throw new TypeError('batch requires 1 to 500 { action, args } objects.');
    }
    if (context !== undefined && !isObject(context)) throw new TypeError('context must be an object.');
    const response = await this.request('batch', {
      commands, ...(context === undefined ? {} : { context }),
      stop_on_error: stopOnError, result_mode: resultMode,
    }, requestOptions);
    if (response.data.success !== true) {
      throw new BrowserCliError('One or more batch steps failed.', { ...response, error_code: 'BATCH_FAILED' });
    }
    return response;
  }

  async status(options = {}) {
    return this.request('runtime-status', { warmup: false }, { startIfNeeded: false, ...options });
  }

  async open(url) { return (await this.request('open', { url })).data; }
  async snapshot({ interactive = false, fullPage = true } = {}) {
    return (await this.request('snapshot', { interactive, full_page: fullPage })).data;
  }
  async screenshot(path, {
    fullPage = false, pageRange, clip, viewportWidth, viewportHeight, deviceScaleFactor,
  } = {}) {
    if (pageRange !== undefined && !['viewport', 'full'].includes(pageRange)) throw new TypeError('pageRange must be viewport or full.');
    if (pageRange === 'viewport' && fullPage) throw new TypeError('fullPage conflicts with pageRange viewport.');
    return (await this.request('screenshot', {
      path, full_page: pageRange === undefined ? fullPage : pageRange === 'full',
      clip, viewport_width: viewportWidth, viewport_height: viewportHeight,
      device_scale_factor: deviceScaleFactor,
    })).data;
  }
  async close() { return (await this.request('close')).data; }

  async ensureStarted() {
    await this.#resolveSocket();
    if (!this._startupPromise) {
      this._startupPromise = this.#runCli([
        'batch', '--commands', '[{"action":"runtime-status","args":{"warmup":false}}]',
        '--result-mode', 'summary',
      ]).finally(() => { this._startupPromise = undefined; });
    }
    await this._startupPromise;
  }

  async #resolveSocket() {
    if (this.socketPath) return;
    this._pathsPromise ||= this.#runCli(['paths', '--json']).catch((error) => {
      this._pathsPromise = undefined;
      throw error;
    });
    const payload = await this._pathsPromise;
    if (typeof payload.data?.socket_path !== 'string') {
      throw new BrowserCliError('Installed Browser CLI does not provide socket_path. Upgrade Browser CLI.');
    }
    this.socketPath = payload.data.socket_path;
  }

  async #sendChecked(request, timeoutMs) {
    // Check on every request: the daemon can be replaced at the same socket.
    // This probe is read-only and never reloads an incompatible running daemon.
    const status = await this.#send({ ...request, action: 'runtime-status', args: { warmup: false } }, timeoutMs);
    if (status.error_code === 'DAEMON_INCOMPATIBLE') throw this.#incompatible(status.meta.runtime_version);
    if (!status.ok) throw new BrowserCliError(status.error_message || 'Daemon status failed.', status);
    if (status.data.runtime_version !== DAEMON_RUNTIME_VERSION) {
      throw this.#incompatible(status.data.runtime_version);
    }
    if (request.action === 'runtime-status' && !request.args.warmup
      && Object.keys(request.args).every(key => key === 'warmup')) return status;
    const result = await this.#send(request, timeoutMs);
    if (result.meta.runtime_version !== DAEMON_RUNTIME_VERSION) {
      throw this.#incompatible(result.meta.runtime_version);
    }
    return result;
  }

  #incompatible(actualVersion) {
    return new BrowserCliError(
      'Client and daemon runtime versions differ. Upgrade Browser CLI and run browser-cli reload before retrying.',
      { error_code: 'DAEMON_INCOMPATIBLE', expected_runtime_version: DAEMON_RUNTIME_VERSION, actual_runtime_version: actualVersion ?? null },
    );
  }

  #runCli(args) {
    return new Promise((resolve, reject) => {
      const child = spawn(this.command, args, {
        env: { ...process.env, BROWSER_CLI_HOME: this.home, X_AGENT_ID: this.agentId },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      let stdout = '';
      let stderr = '';
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        callback(value);
      };
      const timer = setTimeout(() => {
        child.kill();
        finish(reject, new BrowserCliError('Browser CLI startup timed out.', { error_code: 'CLIENT_TIMEOUT' }));
      }, this.startupTimeoutMs);
      child.stdout.setEncoding('utf8');
      child.stderr.setEncoding('utf8');
      child.stdout.on('data', (chunk) => {
        if (settled) return;
        stdout += chunk;
        if (Buffer.byteLength(stdout) > this.maxResponseBytes) {
          child.kill();
          finish(reject, new BrowserCliError('Browser CLI output exceeded maxResponseBytes.'));
        }
      });
      child.stderr.on('data', (chunk) => { stderr = (stderr + chunk).slice(-4096); });
      child.once('error', (error) => finish(reject, error));
      child.once('close', (code) => {
        try {
          const payload = JSON.parse(stdout);
          if (code !== 0 || payload.ok !== true) throw new BrowserCliError(payload.error_message || `Browser CLI exited with code ${code}. ${stderr}`, payload);
          finish(resolve, payload);
        } catch (error) {
          finish(reject, error instanceof BrowserCliError ? error : new BrowserCliError(`Invalid Browser CLI output (exit ${code}). ${stderr}`));
        }
      });
    });
  }

  #send(request, timeoutMs) {
    return new Promise((resolve, reject) => {
      const socket = createConnection(this.socketPath);
      let buffer = '';
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        socket.destroy();
        callback(value);
      };
      const timer = setTimeout(() => finish(reject, new BrowserCliError(
        'Browser CLI response timed out. The action may still be running.', { error_code: 'CLIENT_TIMEOUT' },
      )), timeoutMs);
      socket.setEncoding('utf8');
      socket.on('connect', () => {
        try { socket.write(`${JSON.stringify(request)}\n`); }
        catch (error) { finish(reject, error); }
      });
      socket.on('data', (chunk) => {
        buffer += chunk;
        if (Buffer.byteLength(buffer) > this.maxResponseBytes) {
          finish(reject, new BrowserCliError('Daemon response exceeded maxResponseBytes.'));
          return;
        }
        const newline = buffer.indexOf('\n');
        if (newline < 0) return;
        try {
          const payload = JSON.parse(buffer.slice(0, newline));
          if (!isObject(payload) || typeof payload.ok !== 'boolean' || !isObject(payload.meta) || !isObject(payload.data)) {
            throw new Error('Expected a daemon ok/data/meta envelope.');
          }
          finish(resolve, payload);
        } catch (error) {
          finish(reject, new BrowserCliError(`Invalid daemon response: ${error.message}`, { error_code: 'INVALID_RESPONSE' }));
        }
      });
      socket.on('error', (error) => finish(reject, error));
      socket.on('close', () => {
        if (!settled) finish(reject, new BrowserCliError('Daemon disconnected before responding. The action may have run.'));
      });
    });
  }
}

export default BrowserCliClient;
