"""Snapshot generation and ref-aware page inspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SNAPSHOT_SCRIPT = r"""
(options) => {
  const interactiveOnly = Boolean(options && options.interactive);
  const includeFullPage = options && options.full_page !== false;
  const namespace = 'browser-cli-v2';

  for (const element of document.querySelectorAll('[data-browser-cli-ref]')) {
    element.removeAttribute('data-browser-cli-ref');
  }

  const ROLE_TAGS = new Map([
    ['a', 'link'],
    ['article', 'article'],
    ['button', 'button'],
    ['details', 'group'],
    ['dialog', 'dialog'],
    ['footer', 'contentinfo'],
    ['form', 'form'],
    ['h1', 'heading'],
    ['h2', 'heading'],
    ['h3', 'heading'],
    ['h4', 'heading'],
    ['h5', 'heading'],
    ['h6', 'heading'],
    ['header', 'banner'],
    ['img', 'img'],
    ['input', 'textbox'],
    ['li', 'listitem'],
    ['main', 'main'],
    ['nav', 'navigation'],
    ['ol', 'list'],
    ['option', 'option'],
    ['p', 'paragraph'],
    ['section', 'region'],
    ['select', 'combobox'],
    ['summary', 'button'],
    ['textarea', 'textbox'],
    ['ul', 'list'],
  ]);

  const INPUT_TYPES = new Map([
    ['button', 'button'],
    ['checkbox', 'checkbox'],
    ['email', 'textbox'],
    ['password', 'textbox'],
    ['radio', 'radio'],
    ['search', 'searchbox'],
    ['submit', 'button'],
    ['tel', 'textbox'],
    ['text', 'textbox'],
    ['url', 'textbox'],
  ]);

  const INTERACTIVE_ROLES = new Set([
    'button', 'checkbox', 'combobox', 'dialog', 'gridcell', 'link',
    'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option', 'radio',
    'searchbox', 'slider', 'spinbutton', 'switch', 'tab', 'tabpanel',
    'textbox', 'treeitem'
  ]);

  const escapeText = (value) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 120);

  const isVisible = (element) => {
    const style = window.getComputedStyle(element);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const inViewport = (element) => {
    const rect = element.getBoundingClientRect();
    return rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
  };

  const inferRole = (element) => {
    const ariaRole = element.getAttribute('role');
    if (ariaRole) return ariaRole;
    const tag = element.tagName.toLowerCase();
    if (tag === 'input') {
      return INPUT_TYPES.get((element.getAttribute('type') || 'text').toLowerCase()) || 'textbox';
    }
    return ROLE_TAGS.get(tag) || '';
  };

  const inferName = (element) => {
    const candidates = [
      element.getAttribute('aria-label'),
      element.getAttribute('alt'),
      element.getAttribute('title'),
      element.getAttribute('placeholder'),
      element.getAttribute('value'),
      element.innerText,
      element.textContent,
    ];
    for (const candidate of candidates) {
      const normalized = escapeText(candidate);
      if (normalized) return normalized;
    }
    return '';
  };

  const isInteractive = (element, role) => {
    if (INTERACTIVE_ROLES.has(role)) return true;
    const tag = element.tagName.toLowerCase();
    if (['button', 'input', 'select', 'textarea', 'a', 'option', 'summary'].includes(tag)) return true;
    if (element.hasAttribute('contenteditable')) return true;
    if (typeof element.onclick === 'function') return true;
    const tabindex = element.getAttribute('tabindex');
    if (tabindex !== null && Number(tabindex) >= 0) return true;
    const style = window.getComputedStyle(element);
    return style.cursor === 'pointer';
  };

  const shouldKeep = (element, role, name) => {
    if (interactiveOnly) return isInteractive(element, role);
    if (role) return true;
    if (name) return true;
    const tag = element.tagName.toLowerCase();
    return !['body', 'div', 'span'].includes(tag);
  };

  const hashRef = (value) => {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    return (hash >>> 0).toString(16).padStart(8, '0').slice(0, 8);
  };

  const refs = {};
  const lines = [];
  const occurrenceCounts = new Map();

  const nextOccurrence = (role, name) => {
    const key = `${role}|${name}`;
    const index = occurrenceCounts.get(key) || 0;
    occurrenceCounts.set(key, index + 1);
    return index;
  };

  const walk = (node, depth) => {
    if (!(node instanceof Element)) return;
    if (!isVisible(node)) return;
    if (!includeFullPage && !inViewport(node)) return;

    const role = inferRole(node);
    const name = inferName(node);
    const keep = shouldKeep(node, role, name);
    let nextDepth = depth;

    if (keep) {
      const roleText = role || node.tagName.toLowerCase();
      const occurrence = nextOccurrence(roleText, name);
      const ref = hashRef(`${namespace}|${roleText}|${name}|${occurrence}`);
      node.setAttribute('data-browser-cli-ref', ref);
      refs[ref] = {
        role: roleText,
        name: name || null,
        nth: occurrence,
        tag: node.tagName.toLowerCase(),
        interactive: isInteractive(node, roleText),
      };

      const indent = interactiveOnly ? '' : '  '.repeat(depth);
      const label = name ? ` "${name.replace(/"/g, '\\"')}"` : '';
      lines.push(`${indent}- ${roleText}${label} [ref=${ref}]`);
      nextDepth = interactiveOnly ? 0 : depth + 1;
    }

    for (const child of Array.from(node.children)) {
      walk(child, nextDepth);
    }
  };

  if (document.body) {
    walk(document.body, 0);
  }

  return {
    tree: lines.length > 0 ? lines.join('\n') : '(empty)',
    refs,
  };
}
"""


@dataclass(slots=True)
class SnapshotCapture:
    tree: str
    refs: dict[str, dict[str, Any]]


async def capture_snapshot(
    page: Any,
    *,
    interactive: bool = False,
    full_page: bool = True,
) -> SnapshotCapture:
    result = await page.evaluate(
        SNAPSHOT_SCRIPT,
        {
            "interactive": interactive,
            "full_page": full_page,
        },
    )
    if not isinstance(result, dict):
        return SnapshotCapture(tree="(empty)", refs={})
    return SnapshotCapture(
        tree=str(result.get("tree") or "(empty)"),
        refs=dict(result.get("refs") or {}),
    )
