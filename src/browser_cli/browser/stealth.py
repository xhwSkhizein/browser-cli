"""Stealth helpers adapted from bridgic-browser concepts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

CHROME_DISABLED_COMPONENTS = [
    "AcceptCHFrame",
    "AutoExpandDetailsElement",
    "AvoidUnnecessaryBeforeUnloadCheckSync",
    "CertificateTransparencyComponentUpdater",
    "DestroyProfileOnBrowserClose",
    "DialMediaRouteProvider",
    "ExtensionManifestV2Disabled",
    "GlobalMediaControls",
    "HttpsUpgrades",
    "ImprovedCookieControls",
    "LazyFrameLoading",
    "LensOverlay",
    "MediaRouter",
    "PaintHolding",
    "ThirdPartyStoragePartitioning",
    "Translate",
    "AutomationControlled",
    "BackForwardCache",
    "OptimizationHints",
    "ProcessPerSiteUpToMainFrameThreshold",
    "InterestFeedContentSuggestions",
    "CalculateNativeWinOcclusion",
    "HeavyAdPrivacyMitigations",
    "PrivacySandboxSettings4",
    "AutofillServerCommunication",
    "CrashReporting",
    "OverscrollHistoryNavigation",
    "InfiniteSessionRestore",
    "ExtensionDisableUnsupportedDeveloper",
    "ExtensionManifestV2Unsupported",
]

CHROME_DISABLED_COMPONENTS_HEADED = [
    "AutomationControlled",
    "InfiniteSessionRestore",
]

CHROME_STEALTH_ARGS = [
    "--disable-field-trial-config",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-back-forward-cache",
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-component-extensions-with-background-pages",
    "--disable-component-update",
    "--no-default-browser-check",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--metrics-recording-only",
    "--no-first-run",
    "--no-service-autorun",
    "--export-tagged-pdf",
    "--disable-search-engine-choice-screen",
    "--unsafely-disable-devtools-self-xss-warnings",
    "--disable-sync",
    "--allow-legacy-extension-manifests",
    "--allow-pre-commit-input",
    "--disable-blink-features=AutomationControlled",
    "--log-level=2",
    "--lang=en-US",
    "--disable-focus-on-load",
    "--disable-window-activation",
    "--generate-pdf-document-outline",
    "--no-pings",
    "--disable-infobars",
    "--hide-crash-restore-bubble",
    "--disable-domain-reliability",
    "--disable-datasaver-prompt",
    "--disable-speech-synthesis-api",
    "--disable-speech-api",
    "--disable-print-preview",
    "--safebrowsing-disable-auto-update",
    "--disable-external-intent-requests",
    "--disable-desktop-notifications",
    "--noerrdialogs",
    "--silent-debugger-extension-api",
    "--disable-extensions-http-throttling",
    "--extensions-on-chrome-urls",
    "--disable-default-apps",
]

CHROME_STEALTH_ARGS_HEADED = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--hide-crash-restore-bubble",
    "--no-service-autorun",
    "--log-level=2",
    "--disable-search-engine-choice-screen",
    "--unsafely-disable-devtools-self-xss-warnings",
    "--disable-popup-blocking",
]

CHROME_LINUX_ONLY_ARGS = [
    "--disable-dev-shm-usage",
    "--ash-no-nudges",
    "--suppress-message-center-popups",
]

CHROME_IGNORE_DEFAULT_ARGS = [
    "--enable-automation",
    "--hide-scrollbars",
]

DEFAULT_PERMISSIONS = [
    "clipboard-read",
    "clipboard-write",
    "notifications",
]

_STEALTH_INIT_SCRIPT_TEMPLATE = r"""
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
  } else if (navigator.webdriver !== undefined) {
    Object.defineProperty(navigator, 'webdriver', {
      get: _mkNative(function () { return undefined; }, ''),
      configurable: true,
    });
  }

  const _makeMime = (type, suffixes, description) =>
    ({ type, suffixes, description, enabledPlugin: null });

  const _pdfMimes = [
    _makeMime('application/pdf', 'pdf', 'Portable Document Format'),
    _makeMime('text/pdf', 'pdf', 'Portable Document Format'),
  ];

  const _makePlugin = (name, description) => {
    const p = { name, description, filename: 'internal-pdf-viewer', length: _pdfMimes.length };
    _pdfMimes.forEach((m, i) => {
      const localMime = { type: m.type, suffixes: m.suffixes, description: m.description, enabledPlugin: p };
      Object.defineProperty(p, i, { value: localMime, enumerable: true });
    });
    p.item = _mkNative(function item(i) { return p[i] ?? null; }, 'item');
    p.namedItem = _mkNative(function namedItem(n) {
      const idx = _pdfMimes.findIndex(m => m.type === n);
      return idx >= 0 ? p[idx] : null;
    }, 'namedItem');
    return p;
  };

  const _plugins = [
    _makePlugin('PDF Viewer', 'Portable Document Format'),
    _makePlugin('Chrome PDF Viewer', 'Portable Document Format'),
    _makePlugin('Chromium PDF Viewer', 'Portable Document Format'),
    _makePlugin('Microsoft Edge PDF Viewer', 'Portable Document Format'),
    _makePlugin('WebKit built-in PDF', 'Portable Document Format'),
  ];

  _pdfMimes.forEach((m) => { m.enabledPlugin = _plugins[0]; });

  const _pluginList = Object.assign([..._plugins], {
    item: _mkNative(function item(i) { return _plugins[i] ?? null; }, 'item'),
    namedItem: _mkNative(function namedItem(n) { return _plugins.find(p => p.name === n) ?? null; }, 'namedItem'),
    refresh: _mkNative(function refresh() {}, 'refresh'),
    length: _plugins.length,
  });

  Object.defineProperty(navigator, 'plugins', {
    get: _mkNative(function () { return _pluginList; }, ''),
    configurable: true,
  });

  const _mimeList = Object.assign([..._pdfMimes], {
    item: _mkNative(function item(i) { return _pdfMimes[i] ?? null; }, 'item'),
    namedItem: _mkNative(function namedItem(n) { return _pdfMimes.find(m => m.type === n) ?? null; }, 'namedItem'),
    length: _pdfMimes.length,
  });

  Object.defineProperty(navigator, 'mimeTypes', {
    get: _mkNative(function () { return _mimeList; }, ''),
    configurable: true,
  });

  try {
    Object.defineProperty(navigator, 'languages', {
      get: _mkNative(function () { return __BROWSER_CLI_LANGS__; }, ''),
      configurable: true,
    });
  } catch (_) {}

  if (!window.chrome || !window.chrome.runtime || !window.chrome.csi || !window.chrome.loadTimes) {
    const _chrome = {
      app: {
        isInstalled: false,
        getDetails: _mkNative(function getDetails() { return null; }, 'getDetails'),
        getIsInstalled: _mkNative(function getIsInstalled() { return false; }, 'getIsInstalled'),
        installState: _mkNative(function installState() { return 'not_installed'; }, 'installState'),
      },
      runtime: {
        connect: _mkNative(function connect() {}, 'connect'),
        sendMessage: _mkNative(function sendMessage() {}, 'sendMessage'),
      },
      csi: _mkNative(function csi() {
        return {
          onloadT: Date.now(),
          pageT: Date.now() - (performance.timeOrigin ?? performance.timing?.navigationStart ?? 0),
          startE: Date.now() - 1000,
          tran: 15,
        };
      }, 'csi'),
      loadTimes: _mkNative(function loadTimes() {
        return {
          commitLoadTime: Date.now() / 1000 - 1,
          connectionInfo: 'h2',
          finishDocumentLoadTime: Date.now() / 1000,
          finishLoadTime: Date.now() / 1000,
          firstPaintAfterLoadTime: 0,
          firstPaintTime: Date.now() / 1000 - 0.5,
          navigationType: 'Other',
          npnNegotiatedProtocol: 'h2',
          requestTime: Date.now() / 1000 - 1,
          startLoadTime: Date.now() / 1000 - 1,
          wasAlternateProtocolAvailable: false,
          wasFetchedViaSpdy: true,
          wasNpnNegotiated: true,
        };
      }, 'loadTimes'),
    };
    try {
      Object.defineProperty(window, 'chrome', {
        value: _chrome, writable: false, enumerable: true, configurable: false,
      });
    } catch (_) { window.chrome = _chrome; }
  }

  if (navigator.permissions && navigator.permissions.query) {
    const _origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = _mkNative(function query(params) {
      if (params && params.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission === 'denied' ? 'default' : Notification.permission, onchange: null });
      }
      return _origQuery(params);
    }, 'query');
  }

  if (window.Notification && Notification.permission === 'denied') {
    try {
      Object.defineProperty(Notification, 'permission', {
        get: _mkNative(function () { return 'default'; }, ''),
        configurable: true,
      });
    } catch (_) {}
  }

  try { document.hasFocus = _mkNative(function hasFocus() { return true; }, 'hasFocus'); } catch (_) {}
  try { Object.defineProperty(document, 'hidden', { get: _mkNative(function () { return false; }, ''), configurable: true }); } catch (_) {}
  try { Object.defineProperty(document, 'visibilityState', { get: _mkNative(function () { return 'visible'; }, ''), configurable: true }); } catch (_) {}

  if (window.outerWidth === 0) {
    try { Object.defineProperty(window, 'outerWidth', { get: _mkNative(function () { return window.innerWidth; }, ''), configurable: true }); } catch (_) {}
  }
  if (window.outerHeight === 0) {
    try { Object.defineProperty(window, 'outerHeight', { get: _mkNative(function () { return window.innerHeight; }, ''), configurable: true }); } catch (_) {}
  }

  if (navigator.deviceMemory === undefined) {
    try { Object.defineProperty(navigator, 'deviceMemory', { get: _mkNative(function () { return 8; }, ''), configurable: true }); } catch (_) {}
  }

  if (!navigator.hardwareConcurrency || navigator.hardwareConcurrency < 2) {
    try { Object.defineProperty(navigator, 'hardwareConcurrency', { get: _mkNative(function () { return 8; }, ''), configurable: true }); } catch (_) {}
  }

  if (!navigator.connection) {
    try {
      Object.defineProperty(navigator, 'connection', {
        get: _mkNative(function () { return { effectiveType: '4g', downlink: 10, rtt: 100, saveData: false }; }, ''),
        configurable: true,
      });
    } catch (_) {}
  }

  (function () {
    const _patchWebGL = (Ctx) => {
      if (!Ctx) return;
      const _orig = Ctx.prototype.getParameter;
      Ctx.prototype.getParameter = _mkNative(function getParameter(parameter) {
        const _val = _orig.call(this, parameter);
        if (parameter === 37445) {
          if (_val && (_val.includes('Google') || _val === '')) return 'Intel Inc.';
          return _val;
        }
        if (parameter === 37446) {
          if (_val && (_val.includes('SwiftShader') || _val === '')) return 'Intel Iris OpenGL Engine';
          return _val;
        }
        return _val;
      }, 'getParameter');
    };
    _patchWebGL(window.WebGLRenderingContext);
    _patchWebGL(window.WebGL2RenderingContext);
  })();
})();
"""


def _normalize_locale(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().split(".", 1)[0]
    if not value:
        return None
    return value.replace("_", "-")


def _languages_for_locale(locale: str | None) -> list[str]:
    normalized = _normalize_locale(locale)
    if not normalized:
        return ["en-US", "en"]
    parts = normalized.split("-")
    base = parts[0]
    langs = [normalized]
    if base != normalized:
        langs.append(base)
    if base.lower() != "en" and "en" not in langs:
        langs.append("en")
    return langs


def _get_playwright_disabled_features() -> list[str]:
    try:
        import playwright as playwright_pkg
    except Exception:
        return []
    try:
        switches_js = (
            Path(playwright_pkg.__file__).parent
            / "driver/package/lib/server/chromium/chromiumSwitches.js"
        )
        text = switches_js.read_text(encoding="utf-8")
        match = re.search(r"const disabledFeatures\s*=.*?\[(.+?)\]\.filter", text, re.DOTALL)
        if not match:
            return []
        return [feature for feature in re.findall(r'"([^"]+)"', match.group(1)) if feature]
    except Exception:
        return []


def _build_disable_features(headless: bool) -> str:
    playright_features = _get_playwright_disabled_features()
    browser_cli_features = (
        CHROME_DISABLED_COMPONENTS if headless else CHROME_DISABLED_COMPONENTS_HEADED
    )
    combined = list(dict.fromkeys(playright_features + list(browser_cli_features)))
    return f"--disable-features={','.join(combined)}"


def build_launch_args(
    *,
    headless: bool,
    viewport_width: int,
    viewport_height: int,
    locale: str | None = None,
) -> list[str]:
    normalized_locale = _normalize_locale(locale) or "en-US"
    if headless:
        args = [arg for arg in CHROME_STEALTH_ARGS if not arg.startswith("--lang=")]
        args.append(f"--lang={normalized_locale}")
        if sys.platform == "linux":
            args.extend(CHROME_LINUX_ONLY_ARGS)
        args.append(_build_disable_features(headless=True))
        args.append(f"--window-size={viewport_width},{viewport_height}")
        args.extend(
            [
                "--headless=new",
                "--hide-scrollbars",
                "--mute-audio",
                "--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4",
            ]
        )
        return args

    args = list(CHROME_STEALTH_ARGS_HEADED)
    if sys.platform == "linux":
        args.append("--disable-dev-shm-usage")
    args.append(_build_disable_features(headless=False))
    args.append(f"--lang={normalized_locale}")
    args.append(f"--window-size={viewport_width},{viewport_height}")
    return args


def build_ignore_default_args() -> list[str]:
    return list(CHROME_IGNORE_DEFAULT_ARGS)


def build_context_options(
    *,
    viewport_width: int,
    viewport_height: int,
    locale: str | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "accept_downloads": True,
        "permissions": list(DEFAULT_PERMISSIONS),
        "screen": {"width": viewport_width, "height": viewport_height},
    }
    normalized_locale = _normalize_locale(locale)
    if normalized_locale:
        options["locale"] = normalized_locale
    return options


def build_init_script(*, headless: bool, locale: str | None = None) -> str | None:
    if not headless:
        return None
    return _STEALTH_INIT_SCRIPT_TEMPLATE.replace(
        "__BROWSER_CLI_LANGS__",
        json.dumps(_languages_for_locale(locale)),
    )
