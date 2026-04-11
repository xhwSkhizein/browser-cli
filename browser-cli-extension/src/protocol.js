export const PROTOCOL_VERSION = '1';
export const DEFAULT_DAEMON_HOST = '127.0.0.1';
export const DEFAULT_DAEMON_PORT = 19825;
export const ARTIFACT_CHUNK_SIZE = 256 * 1024;

export const REQUIRED_CAPABILITIES = [
  'open',
  'tabs',
  'info',
  'html',
  'snapshot',
  'reload',
  'back',
  'forward',
  'resize',
  'click',
  'double-click',
  'hover',
  'focus',
  'fill',
  'fill-form',
  'select',
  'check',
  'options',
  'uncheck',
  'scroll-to',
  'drag',
  'upload',
  'scroll',
  'type',
  'press',
  'key-down',
  'key-up',
  'mouse-click',
  'mouse-move',
  'mouse-drag',
  'mouse-down',
  'mouse-up',
  'eval',
  'eval-on',
  'wait',
  'wait-network',
  'screenshot',
  'pdf',
  'trace-start',
  'trace-chunk',
  'trace-stop',
  'video-start',
  'video-stop',
  'network-wait',
  'network',
  'network-start',
  'network-stop',
  'console',
  'console-start',
  'console-stop',
  'dialog-setup',
  'dialog',
  'dialog-remove',
  'cookies',
  'cookie-set',
  'cookies-clear',
  'storage-save',
  'storage-load',
  'verify-visible',
  'verify-text',
  'verify-url',
  'verify-title',
  'verify-state',
  'verify-value',
];

export const OPTIONAL_CAPABILITIES = [];

export const SUPPORTED_CAPABILITIES = [
  ...REQUIRED_CAPABILITIES,
];

export const CORE_CAPABILITIES = REQUIRED_CAPABILITIES;

export function buildWsUrl(host = DEFAULT_DAEMON_HOST, port = DEFAULT_DAEMON_PORT) {
  return `ws://${host}:${port}/ext`;
}
