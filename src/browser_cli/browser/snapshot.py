"""Simplified bridgic-style snapshot generation."""

from __future__ import annotations

SNAPSHOT_SCRIPT = r"""
() => {
  const ROLE_TAGS = new Map([
    ['a', 'link'],
    ['article', 'article'],
    ['button', 'button'],
    ['h1', 'heading'],
    ['h2', 'heading'],
    ['h3', 'heading'],
    ['h4', 'heading'],
    ['h5', 'heading'],
    ['h6', 'heading'],
    ['img', 'img'],
    ['li', 'listitem'],
    ['main', 'main'],
    ['nav', 'navigation'],
    ['ol', 'list'],
    ['p', 'paragraph'],
    ['section', 'region'],
    ['select', 'combobox'],
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
    ['text', 'textbox'],
    ['url', 'textbox'],
  ]);

  const escapeText = (value) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 120);
  const isVisible = (element) => {
    const style = window.getComputedStyle(element);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
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
      element.innerText,
      element.textContent,
      element.getAttribute('value'),
    ];
    for (const candidate of candidates) {
      const value = escapeText(candidate);
      if (value) return value;
    }
    return '';
  };

  const shouldKeep = (role, name, element) => {
    if (role) return true;
    if (name && name.length > 0) return true;
    const tag = element.tagName.toLowerCase();
    return ['body', 'header', 'footer', 'div', 'span'].includes(tag) ? false : true;
  };

  const hashRef = (value) => {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    return (hash >>> 0).toString(16).padStart(8, '0').slice(0, 8);
  };

  const lines = [];

  const walk = (node, depth, path) => {
    if (!(node instanceof Element)) return;
    if (!isVisible(node)) return;

    const role = inferRole(node);
    const name = inferName(node);
    if (shouldKeep(role, name, node)) {
      const roleText = role || node.tagName.toLowerCase();
      const ref = hashRef(`${path}|${roleText}|${name}`);
      const indent = '  '.repeat(depth);
      const label = name ? ` "${name.replace(/"/g, '\\"')}"` : '';
      lines.push(`${indent}- ${roleText}${label} [ref=${ref}]`);
      depth += 1;
    }

    Array.from(node.children).forEach((child, index) => walk(child, depth, `${path}.${index}`));
  };

  walk(document.body, 0, '0');
  return lines.join('\n');
}
"""

