"""Stealth helpers adapted from bridgic-browser concepts."""

from __future__ import annotations


def build_launch_args() -> list[str]:
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--no-default-browser-check",
        "--disable-features=Translate,OptimizationHints,MediaRouter",
    ]


# Adapted from bridgic-browser/bridgic/browser/session/_stealth.py.
STEALTH_INIT_SCRIPT = r"""
(function () {
  const _nativeFns = new WeakSet();
  const _nativeFnNames = new WeakMap();
  const _mkNative = (fn, name) => {
    _nativeFns.add(fn);
    if (name !== undefined) _nativeFnNames.set(fn, name);
    return fn;
  };

  const _origFnToString = Function.prototype.toString;
  Function.prototype.toString = _mkNative(function toString() {
    if (_nativeFns.has(this)) {
      const _n = _nativeFnNames.has(this) ? _nativeFnNames.get(this) : (this.name || '');
      return `function ${_n}() { [native code] }`;
    }
    return _origFnToString.call(this);
  }, 'toString');

  const _wdDesc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
  if (_wdDesc) {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      get: _mkNative(function () { return undefined; }, ''),
      configurable: true,
    });
  }

  try {
    Object.defineProperty(navigator, 'languages', {
      get: _mkNative(function () { return ['en-US', 'en']; }, ''),
      configurable: true,
    });
  } catch (_) {}

  if (!window.chrome || !window.chrome.runtime) {
    const _chrome = {
      runtime: {
        connect: _mkNative(function connect() {}, 'connect'),
        sendMessage: _mkNative(function sendMessage() {}, 'sendMessage'),
      },
      csi: _mkNative(function csi() { return {}; }, 'csi'),
      loadTimes: _mkNative(function loadTimes() { return {}; }, 'loadTimes'),
    };
    try {
      Object.defineProperty(window, 'chrome', {
        value: _chrome, writable: false, enumerable: true, configurable: false,
      });
    } catch (_) {
      window.chrome = _chrome;
    }
  }

  if (navigator.permissions && navigator.permissions.query) {
    const _origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = _mkNative(function query(params) {
      if (params && params.name === 'notifications') {
        return Promise.resolve({ state: 'default', onchange: null });
      }
      return _origQuery(params);
    }, 'query');
  }

  try {
    document.hasFocus = _mkNative(function hasFocus() { return true; }, 'hasFocus');
  } catch (_) {}
})();
"""

