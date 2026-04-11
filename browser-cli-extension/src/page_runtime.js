function js(value) {
  return JSON.stringify(value);
}

function locatorPrelude() {
  return `
    const __browserCli = window.__browserCli || (window.__browserCli = {});

    function bcNormalizeText(value) {
      return String(value || '').replace(/\\s+/g, ' ').trim();
    }

    function bcTagRole(tag) {
      switch ((tag || '').toLowerCase()) {
        case 'a': return 'link';
        case 'button': return 'button';
        case 'input': {
          const type = (arguments[1] || '').toLowerCase();
          if (type === 'checkbox') return 'checkbox';
          if (type === 'radio') return 'radio';
          if (type === 'search') return 'searchbox';
          if (type === 'button' || type === 'submit' || type === 'reset') return 'button';
          return 'textbox';
        }
        case 'textarea': return 'textbox';
        case 'select': return 'combobox';
        case 'option': return 'option';
        case 'img': return 'img';
        case 'h1':
        case 'h2':
        case 'h3':
        case 'h4':
        case 'h5':
        case 'h6':
          return 'heading';
        case 'main': return 'main';
        case 'nav': return 'navigation';
        case 'article': return 'article';
        case 'section': return 'region';
        case 'p': return 'paragraph';
        case 'iframe': return 'iframe';
        default: return 'generic';
      }
    }

    function bcRoleFor(el) {
      const explicit = bcNormalizeText(el.getAttribute('role'));
      if (explicit) return explicit.toLowerCase();
      return bcTagRole(el.tagName, el.getAttribute('type'));
    }

    function bcNameFor(el) {
      const aria = bcNormalizeText(el.getAttribute('aria-label'));
      if (aria) return aria;
      const labelledBy = bcNormalizeText(el.getAttribute('aria-labelledby'));
      if (labelledBy) {
        const parts = labelledBy.split(/\\s+/).map((id) => bcNormalizeText(document.getElementById(id)?.textContent));
        const joined = bcNormalizeText(parts.join(' '));
        if (joined) return joined;
      }
      if (el.labels && el.labels.length > 0) {
        const joined = bcNormalizeText(Array.from(el.labels).map((node) => node.textContent || '').join(' '));
        if (joined) return joined;
      }
      const title = bcNormalizeText(el.getAttribute('title'));
      if (title) return title;
      const alt = bcNormalizeText(el.getAttribute('alt'));
      if (alt) return alt;
      const placeholder = bcNormalizeText(el.getAttribute('placeholder'));
      if (placeholder) return placeholder;
      const value = bcNormalizeText(el.value);
      const text = bcNormalizeText(el.innerText || el.textContent);
      return value || text || null;
    }

    function bcTextFor(el) {
      if (!el) return '';
      if (el.tagName && el.tagName.toLowerCase() === 'input') {
        return bcNormalizeText(el.value || '');
      }
      if (el.tagName && el.tagName.toLowerCase() === 'textarea') {
        return bcNormalizeText(el.value || '');
      }
      return bcNormalizeText(el.innerText || el.textContent || '');
    }

    function bcIsVisible(el) {
      if (!el || !el.isConnected) return false;
      const style = window.getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    function bcSameOriginDoc(iframe) {
      try {
        return iframe.contentWindow && iframe.contentWindow.document ? iframe.contentWindow.document : null;
      } catch (error) {
        return null;
      }
    }

    function bcDocForFramePath(framePath) {
      let doc = document;
      const path = Array.isArray(framePath) ? framePath : [];
      for (const index of path) {
        const iframes = Array.from(doc.querySelectorAll('iframe'));
        const frame = iframes[index];
        if (!frame) return null;
        doc = bcSameOriginDoc(frame);
        if (!doc) return null;
      }
      return doc;
    }

    function bcAllElements(doc) {
      return Array.from((doc || document).querySelectorAll('*'));
    }

    function bcMatchRole(el, role) {
      return bcRoleFor(el) === role;
    }

    function bcResolveLocator(locator) {
      const doc = bcDocForFramePath(locator.frame_path);
      if (!doc) return null;
      let candidates = bcAllElements(doc).filter((el) => bcMatchRole(el, locator.role));
      if (locator.name) {
        candidates = candidates.filter((el) => bcNameFor(el) === locator.name);
      } else if (locator.match_text && ['row', 'cell', 'columnheader', 'rowheader', 'gridcell', 'listitem', 'text'].includes(locator.role)) {
        candidates = candidates.filter((el) => bcTextFor(el).includes(locator.match_text));
      } else if (locator.text_content) {
        candidates = candidates.filter((el) => bcTextFor(el) === locator.text_content);
      } else if (locator.child_text) {
        candidates = candidates.filter((el) => bcTextFor(el).includes(locator.child_text));
      }
      candidates = candidates.filter((el) => el.isConnected);
      if (locator.nth !== null && locator.nth !== undefined && locator.nth >= 0) {
        return candidates[locator.nth] || null;
      }
      return candidates[0] || null;
    }

    function bcEnsureCaptureState() {
      if (!__browserCli.consoleBuffer) __browserCli.consoleBuffer = [];
      if (!__browserCli.dialogHandlers) __browserCli.dialogHandlers = {};
    }

    function bcResolveRoleName(role, name, exact) {
      let candidates = bcAllElements(document).filter((el) => bcMatchRole(el, role));
      candidates = candidates.filter((el) => {
        const candidateName = bcNameFor(el);
        return exact ? candidateName === name : String(candidateName || '').includes(String(name || ''));
      });
      candidates = candidates.filter((el) => bcIsVisible(el));
      return candidates[0] || null;
    }
  `;
}

export function captureHtmlJs() {
  return `
    (() => {
      return document.documentElement ? document.documentElement.outerHTML : '<html><head></head><body></body></html>';
    })()
  `;
}

export function pageInfoJs() {
  return `
    (() => ({
      url: window.location.href,
      title: document.title,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      page_width: Math.max(document.body ? document.body.scrollWidth : 0, document.documentElement.scrollWidth),
      page_height: Math.max(document.body ? document.body.scrollHeight : 0, document.documentElement.scrollHeight),
      scroll_x: window.scrollX,
      scroll_y: window.scrollY
    }))()
  `;
}

export function waitJs({ seconds = null, text = null, gone = false, exact = false } = {}) {
  if (!text) {
    const timeoutMs = Math.max(0, Number(seconds || 1) * 1000);
    return `
      new Promise((resolve) => {
        setTimeout(() => resolve({ seconds: ${js(seconds || 1)} }), ${Math.floor(timeoutMs)});
      })
    `;
  }
  const timeoutMs = Math.max(0, Number(seconds || 30) * 1000);
  return `
    new Promise((resolve, reject) => {
      const wanted = ${js(text)};
      const exact = ${exact ? 'true' : 'false'};
      const expectGone = ${gone ? 'true' : 'false'};
      const deadline = Date.now() + ${Math.floor(timeoutMs)};
      const read = () => {
        const body = document.body ? document.body.innerText || '' : '';
        return exact ? body.split(/\\n+/).includes(wanted) : body.includes(wanted);
      };
      const loop = () => {
        const present = read();
        if ((!expectGone && present) || (expectGone && !present)) {
          resolve({ text: wanted, state: expectGone ? 'hidden' : 'visible' });
          return;
        }
        if (Date.now() > deadline) {
          reject(new Error('wait timed out'));
          return;
        }
        setTimeout(loop, 150);
      };
      loop();
    })
  `;
}

export function installConsoleCaptureJs() {
  return `
    (() => {
      ${locatorPrelude()}
      bcEnsureCaptureState();
      if (__browserCli.consoleInstalled) return { capturing: true, already_installed: true };
      __browserCli.consoleInstalled = true;
      for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
        const original = console[level].bind(console);
        __browserCli['consoleOriginal_' + level] = original;
        console[level] = (...args) => {
          try {
            __browserCli.consoleBuffer.push({
              type: level,
              text: args.map((item) => {
                if (typeof item === 'string') return item;
                try { return JSON.stringify(item); } catch (error) { return String(item); }
              }).join(' '),
              ts: Date.now()
            });
          } catch (error) {}
          return original(...args);
        };
      }
      return { capturing: true, already_installed: false };
    })()
  `;
}

export function getConsoleMessagesJs({ messageType = null, clear = true } = {}) {
  return `
    (() => {
      ${locatorPrelude()}
      bcEnsureCaptureState();
      let messages = Array.from(__browserCli.consoleBuffer || []);
      if (${js(messageType)} !== null) {
        messages = messages.filter((item) => item.type === ${js(messageType)});
      }
      if (${clear ? 'true' : 'false'}) {
        __browserCli.consoleBuffer = [];
      }
      return { messages };
    })()
  `;
}

export function stopConsoleCaptureJs() {
  return `
    (() => {
      ${locatorPrelude()}
      bcEnsureCaptureState();
      __browserCli.consoleBuffer = [];
      return { capturing: false };
    })()
  `;
}

export function storageGetJs() {
  return `
    (() => ({
      localStorage: Object.fromEntries(Object.entries(localStorage)),
      sessionStorage: Object.fromEntries(Object.entries(sessionStorage))
    }))()
  `;
}

export function storageSetJs(state) {
  return `
    (() => {
      const state = ${js(state)};
      localStorage.clear();
      sessionStorage.clear();
      for (const [key, value] of Object.entries(state.localStorage || {})) localStorage.setItem(key, String(value));
      for (const [key, value] of Object.entries(state.sessionStorage || {})) sessionStorage.setItem(key, String(value));
      return { loaded: true };
    })()
  `;
}

export function verifyTextJs({ text, exact = false, timeoutSeconds = 5 }) {
  return waitJs({ seconds: timeoutSeconds, text, exact, gone: false }).replace('resolve({ text: wanted, state: expectGone ? \'hidden\' : \'visible\' });', 'resolve({ passed: true, text: wanted });');
}

export function verifyUrlJs({ expected, exact = false }) {
  return `
    (() => {
      const actual = window.location.href;
      const expected = ${js(expected)};
      const passed = ${exact ? 'actual === expected' : 'actual.includes(expected)'};
      return { passed, expected, actual };
    })()
  `;
}

export function verifyTitleJs({ expected, exact = false }) {
  return `
    (() => {
      const actual = document.title;
      const expected = ${js(expected)};
      const passed = ${exact ? 'actual === expected' : 'actual.includes(expected)'};
      return { passed, expected, actual };
    })()
  `;
}

export function verifyVisibleJs({ role, name, timeoutSeconds = 5 } = {}) {
  return `
    new Promise((resolve) => {
      ${locatorPrelude()}
      const wantedRole = ${js(role)};
      const wantedName = ${js(name)};
      const deadline = Date.now() + ${Math.floor(Number(timeoutSeconds || 5) * 1000)};
      const loop = () => {
        const node = bcResolveRoleName(wantedRole, wantedName, true);
        if (node) {
          resolve({ passed: true, role: wantedRole, name: wantedName });
          return;
        }
        if (Date.now() > deadline) {
          resolve({ passed: false, role: wantedRole, name: wantedName });
          return;
        }
        setTimeout(loop, 120);
      };
      loop();
    })
  `;
}

export function locatorActionJs(action, locator, payload = {}) {
  return `
    (() => {
      ${locatorPrelude()}
      const locator = ${js(locator)};
      const payload = ${js(payload)};
      const el = bcResolveLocator(locator);
      if (!el) throw new Error('Element not found');
      if (${js(action)} === 'click') {
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        el.click();
        return { ok: true };
      }
      if (${js(action)} === 'double-click') {
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window }));
        return { ok: true };
      }
      if (${js(action)} === 'hover') {
        el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window }));
        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
        return { ok: true };
      }
      if (${js(action)} === 'focus') {
        el.focus();
        return { ok: true };
      }
      if (${js(action)} === 'fill') {
        const text = String(payload.text || '');
        el.focus();
        if (el.isContentEditable) {
          el.textContent = text;
        } else {
          el.value = text;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        if (payload.submit) {
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
        }
        return { ok: true };
      }
      if (${js(action)} === 'select') {
        const wanted = String(payload.text || '');
        const option = Array.from(el.options || []).find((item) => bcNormalizeText(item.textContent) === wanted);
        if (!option) throw new Error('Option not found');
        el.value = option.value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true };
      }
      if (${js(action)} === 'options') {
        const options = Array.from(el.options || []).map((item) => bcNormalizeText(item.textContent)).filter(Boolean);
        return { options };
      }
      if (${js(action)} === 'check') {
        const checked = !!payload.checked;
        if ('checked' in el) {
          el.checked = checked;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return { ok: true };
        }
        throw new Error('Element is not checkable');
      }
      if (${js(action)} === 'scroll-to') {
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        return { ok: true };
      }
      if (${js(action)} === 'eval-on') {
        const evaluated = eval(String(payload.code || ''));
        const result = typeof evaluated === 'function' ? evaluated(el) : evaluated;
        return { result };
      }
      if (${js(action)} === 'verify-state') {
        const state = String(payload.state || '').toLowerCase();
        let passed = false;
        if (state === 'visible') passed = bcIsVisible(el);
        else if (state === 'hidden') passed = !bcIsVisible(el);
        else if (state === 'enabled') passed = !el.disabled;
        else if (state === 'disabled') passed = !!el.disabled;
        else if (state === 'editable') passed = !el.disabled && !el.readOnly;
        else if (state === 'checked') passed = !!el.checked;
        else if (state === 'unchecked') passed = !el.checked;
        else throw new Error('Unsupported verify state');
        return { state, passed };
      }
      if (${js(action)} === 'verify-value') {
        const actual = 'value' in el ? String(el.value || '') : bcTextFor(el);
        const expected = String(payload.expected || '');
        return { expected, actual, passed: actual === expected };
      }
      throw new Error('Unsupported locator action');
    })()
  `;
}

export function generateSnapshotJs({ interactive = false } = {}) {
  return `
    (() => {
      ${locatorPrelude()}
      const interactiveOnly = ${interactive ? 'true' : 'false'};
      const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK', 'HEAD']);
      const keptRoles = new Set(['button', 'link', 'textbox', 'checkbox', 'radio', 'combobox', 'option', 'heading', 'paragraph', 'img', 'main', 'navigation', 'article', 'region', 'iframe']);

      function shouldKeep(el) {
        if (!el || skipTags.has(el.tagName)) return false;
        if (!bcIsVisible(el)) return false;
        const role = bcRoleFor(el);
        if (interactiveOnly) return ['button', 'link', 'textbox', 'checkbox', 'radio', 'combobox', 'option'].includes(role);
        if (keptRoles.has(role)) return true;
        const text = bcTextFor(el);
        return text.length > 0 && text.length < 200;
      }

      function serialize(doc, depth, framePath) {
        const lines = [];
        for (const el of Array.from((doc.body || doc.documentElement).children || [])) {
          walk(el, depth, framePath, lines);
        }
        return lines;
      }

      function walk(el, depth, framePath, lines) {
        if (!shouldKeep(el)) {
          for (const child of Array.from(el.children || [])) walk(child, depth, framePath, lines);
          return;
        }
        const role = bcRoleFor(el);
        const name = bcNameFor(el);
        const text = bcTextFor(el);
        let line = '  '.repeat(depth) + '- ' + role;
        if (name) line += ' ' + JSON.stringify(name);
        if (!name && text) line += ': ' + JSON.stringify(text.slice(0, 120));
        lines.push(line);
        if (role === 'iframe') {
          const childDoc = bcSameOriginDoc(el);
          if (childDoc) {
            for (const child of Array.from((childDoc.body || childDoc.documentElement).children || [])) {
              walk(child, depth + 1, framePath.concat([0]), lines);
            }
          }
          return;
        }
        for (const child of Array.from(el.children || [])) {
          walk(child, depth + 1, framePath, lines);
        }
      }

      return serialize(document, 0, []).join('\\n');
    })()
  `;
}

export function typeTextJs(text, { submit = false } = {}) {
  return `
    (() => {
      const text = ${js(text)};
      const active = document.activeElement || document.body;
      active.focus();
      if ('value' in active) {
        active.value = String(active.value || '') + text;
      } else if (active.isContentEditable) {
        active.textContent = String(active.textContent || '') + text;
      }
      active.dispatchEvent(new Event('input', { bubbles: true }));
      active.dispatchEvent(new Event('change', { bubbles: true }));
      for (const char of text) {
        active.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        active.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
      }
      if (${submit ? 'true' : 'false'}) {
        active.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        active.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
      }
      return { typed: true, submitted: ${submit ? 'true' : 'false'} };
    })()
  `;
}

export function keyActionJs(action, key) {
  return `
    (() => {
      const active = document.activeElement || document.body;
      const eventName = ${js(action)} === 'press'
        ? 'keydown'
        : (${js(action)} === 'key-down' ? 'keydown' : 'keyup');
      active.dispatchEvent(new KeyboardEvent(eventName, { key: ${js(key)}, bubbles: true }));
      if (${js(action)} === 'press') {
        active.dispatchEvent(new KeyboardEvent('keyup', { key: ${js(key)}, bubbles: true }));
      }
      return { key: ${js(key)} };
    })()
  `;
}

export function scrollPageJs(dx = 0, dy = 700) {
  return `
    (() => {
      window.scrollBy(${Number(dx) || 0}, ${Number(dy) || 700});
      document.dispatchEvent(new WheelEvent('wheel', {
        deltaX: ${Number(dx) || 0},
        deltaY: ${Number(dy) || 700},
        bubbles: true,
        cancelable: true
      }));
      return { dx: ${Number(dx) || 0}, dy: ${Number(dy) || 700}, scroll_x: window.scrollX, scroll_y: window.scrollY };
    })()
  `;
}

export function mouseActionJs(action, payload = {}) {
  return `
    (() => {
      const payload = ${js(payload)};
      const dispatch = (type, x, y, extra = {}) => {
        const target = document.elementFromPoint(x, y) || document.body || document.documentElement;
        target.dispatchEvent(new MouseEvent(type, {
          bubbles: true,
          cancelable: true,
          clientX: x,
          clientY: y,
          button: extra.buttonIndex ?? 0,
          buttons: extra.buttons ?? 1,
          detail: extra.detail ?? 1,
          view: window,
        }));
      };
      const buttonName = String(payload.button || 'left');
      const buttonIndex = buttonName === 'right' ? 2 : (buttonName === 'middle' ? 1 : 0);
      if (${js(action)} === 'mouse-move') {
        dispatch('mousemove', Number(payload.x), Number(payload.y), { buttonIndex: 0, buttons: 0, detail: 0 });
        return { x: Number(payload.x), y: Number(payload.y) };
      }
      if (${js(action)} === 'mouse-click') {
        const count = Math.max(1, Number(payload.count || 1));
        for (let i = 0; i < count; i += 1) {
          dispatch('mousedown', Number(payload.x), Number(payload.y), { buttonIndex, buttons: 1, detail: i + 1 });
          dispatch('mouseup', Number(payload.x), Number(payload.y), { buttonIndex, buttons: 0, detail: i + 1 });
          dispatch('click', Number(payload.x), Number(payload.y), { buttonIndex, buttons: 0, detail: i + 1 });
        }
        return { x: Number(payload.x), y: Number(payload.y), button: buttonName, count };
      }
      if (${js(action)} === 'mouse-drag') {
        dispatch('mousemove', Number(payload.x1), Number(payload.y1), { buttonIndex: 0, buttons: 0, detail: 0 });
        dispatch('mousedown', Number(payload.x1), Number(payload.y1), { buttonIndex: 0, buttons: 1, detail: 1 });
        dispatch('mousemove', Number(payload.x2), Number(payload.y2), { buttonIndex: 0, buttons: 1, detail: 0 });
        dispatch('mouseup', Number(payload.x2), Number(payload.y2), { buttonIndex: 0, buttons: 0, detail: 1 });
        return { from: { x: Number(payload.x1), y: Number(payload.y1) }, to: { x: Number(payload.x2), y: Number(payload.y2) } };
      }
      if (${js(action)} === 'mouse-down') {
        dispatch('mousedown', 1, 1, { buttonIndex, buttons: 1, detail: 1 });
        return { button: buttonName };
      }
      if (${js(action)} === 'mouse-up') {
        dispatch('mouseup', 1, 1, { buttonIndex, buttons: 0, detail: 1 });
        return { button: buttonName };
      }
      throw new Error('Unsupported mouse action');
    })()
  `;
}

export function dragBetweenLocatorsJs(startLocator, endLocator) {
  return `
    (() => {
      ${locatorPrelude()}
      const source = bcResolveLocator(${js(startLocator)});
      const target = bcResolveLocator(${js(endLocator)});
      if (!source || !target) throw new Error('Drag endpoint not found');
      const dataTransfer = new DataTransfer();
      source.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer }));
      target.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer }));
      target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }));
      source.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true, dataTransfer }));
      return { dragged: true };
    })()
  `;
}

export function markUploadTargetJs(locator, marker) {
  return `
    (() => {
      ${locatorPrelude()}
      const el = bcResolveLocator(${js(locator)});
      if (!el) throw new Error('Element not found');
      el.setAttribute('data-browser-cli-upload-target', ${js(marker)});
      return { selector: '[data-browser-cli-upload-target=' + JSON.stringify(${js(marker)}) + ']' };
    })()
  `;
}

export function dialogOverrideJs({ action = 'accept', text = null } = {}) {
  return `
    (() => {
      ${locatorPrelude()}
      bcEnsureCaptureState();
      const defaultAction = ${js(action)};
      const promptText = ${js(text)};
      __browserCli.dialogHandlers.default = { action: defaultAction, promptText };
      window.alert = (message) => {
        __browserCli.lastDialog = { type: 'alert', message: String(message || ''), result: 'accepted' };
      };
      window.confirm = (message) => {
        const accepted = defaultAction !== 'dismiss';
        __browserCli.lastDialog = { type: 'confirm', message: String(message || ''), result: accepted };
        return accepted;
      };
      window.prompt = (message, defaultPrompt) => {
        const value = defaultAction === 'dismiss' ? null : (promptText ?? defaultPrompt ?? '');
        __browserCli.lastDialog = { type: 'prompt', message: String(message || ''), defaultPrompt: defaultPrompt ?? '', result: value };
        return value;
      };
      return { configured: true, action: defaultAction, text: promptText };
    })()
  `;
}

export function dialogRemoveJs() {
  return `
    (() => {
      ${locatorPrelude()}
      bcEnsureCaptureState();
      if (__browserCli.dialogHandlers) {
        delete __browserCli.dialogHandlers.default;
      }
      return { removed: true };
    })()
  `;
}
