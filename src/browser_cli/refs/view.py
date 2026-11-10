"""Optional response views over a complete daemon-owned semantic snapshot.

Views never change the stored snapshot or regenerate refs. They reduce only
the observation sent to the caller, after the shared generator has run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from browser_cli.refs.generator import SemanticSnapshotGenerator
from browser_cli.refs.models import RefData, SemanticSnapshot
from browser_cli.refs.resolver import SemanticRefResolver

_ROLE = re.compile(r"^\s*-\s+([a-zA-Z][a-zA-Z0-9_-]*)\b")


@dataclass(frozen=True)
class _Line:
    text: str
    ref: str | None


@dataclass(frozen=True)
class SnapshotViewOptions:
    compact: bool = False
    scope: str | None = None
    roles: tuple[str, ...] = ()
    max_lines: int | None = None

    @classmethod
    def from_dict(cls, args: dict[str, Any]) -> SnapshotViewOptions | None:
        compact = args.get("compact", False)
        if not isinstance(compact, bool):
            raise ValueError("snapshot compact must be a boolean.")
        scope = args.get("scope")
        if scope is not None:
            if not isinstance(scope, str) or SemanticRefResolver.parse_ref(scope) is None:
                raise ValueError("snapshot scope must be a semantic ref from this page.")
            scope = SemanticRefResolver.parse_ref(scope)
        roles = args.get("roles", [])
        if not isinstance(roles, list) or any(
            not isinstance(role, str) or re.fullmatch(r"[a-z][a-z0-9_-]*", role) is None
            for role in roles
        ):
            raise ValueError("snapshot roles must be an array of lowercase role names.")
        max_lines = args.get("max_lines")
        if max_lines is not None and (type(max_lines) is not int or not 1 <= max_lines <= 100_000):
            raise ValueError("snapshot max_lines must be an integer from 1 to 100000.")
        if not compact and scope is None and not roles and max_lines is None:
            return None
        return cls(compact, scope, tuple(dict.fromkeys(roles)), max_lines)


def _summary(data: RefData, compact: bool) -> dict[str, Any]:
    if not compact:
        return data.to_summary()
    # Preserve every field consumed by the public SnapshotResult, including
    # duplicate disambiguation, ancestry and iframe paths. Locator recipes and
    # repeated capture provenance remain in the daemon's complete registry.
    values = {
        "ref": data.ref,
        "role": data.role,
        "name": data.name,
        "nth": data.nth,
        "text_content": data.text_content,
        "interactive": data.interactive,
        "parent_ref": data.parent_ref,
        "frame_path": list(data.frame_path),
    }
    return {key: value for key, value in values.items() if value is not None}


def _line_ref(line: _Line, refs: dict[str, RefData]) -> tuple[RefData, str] | None:
    """Read the generator's line owner; page text cannot supply this identity.

    Accessible names may themselves contain quotes and ref-shaped text.
    Verify the owned line's prefix before reading the genuine state suffix, which
    excludes the complete page-supplied name, including any embedded markers.
    """
    if line.ref is None:
        return None
    data = refs.get(line.ref)
    content = line.text.lstrip()
    role = _ROLE.match(content)
    if data is None or role is None or data.role != role[1].lower():
        raise ValueError("Snapshot line provenance does not match its ref registry.")
    name = f' "{data.name}"' if data.name else ""
    prefix = f"- {role[1]}{name} [ref={data.ref}]"
    if not content.startswith(prefix):
        raise ValueError("Snapshot line provenance does not match its rendered name.")
    return data, content[len(prefix) :]


def _select_subtrees(lines: list[_Line], matches: set[int], *, descendants: bool) -> list[_Line]:
    keep: set[int] = set()
    ancestors: list[tuple[int, int]] = []
    selected_depth: int | None = None
    for index, line in enumerate(lines):
        depth = len(line.text) - len(line.text.lstrip())
        while ancestors and ancestors[-1][0] >= depth:
            ancestors.pop()
        if selected_depth is not None and depth <= selected_depth:
            selected_depth = None
        if index in matches:
            selected_depth = depth if selected_depth is None else selected_depth
            keep.update(item[1] for item in ancestors)
            keep.add(index)
        elif selected_depth is not None and (descendants or line.text.lstrip().startswith("- /")):
            keep.add(index)
        ancestors.append((depth, index))
    return [line for index, line in enumerate(lines) if index in keep]


def project_snapshot(
    snapshot: SemanticSnapshot, options: SnapshotViewOptions, *, interactive: bool = False
) -> dict[str, Any]:
    """Keep selected subtrees and their ancestors; make every omission explicit.

    A missing scope raises KeyError so the service can distinguish an unknown
    ref from a previously known ref that disappeared. Never widen on failure.
    """
    text_lines = snapshot.tree.splitlines() if snapshot.tree != "(empty)" else []
    line_refs = snapshot.line_refs
    if line_refs is None:
        if snapshot.refs:
            raise ValueError("Snapshot views require generator-owned line provenance.")
        line_refs = (None,) * len(text_lines)
    if len(line_refs) != len(text_lines):
        raise ValueError("Snapshot line provenance does not match its tree length.")
    lines = [_Line(text, ref) for text, ref in zip(text_lines, line_refs, strict=True)]
    for line in lines:
        _line_ref(line, snapshot.refs)
    total_lines = len(lines)
    if options.scope is not None:
        if options.scope not in snapshot.refs:
            raise KeyError(options.scope)
        start = next(
            (i for i, line in enumerate(lines) if line.ref == options.scope),
            None,
        )
        if start is None:
            raise KeyError(options.scope)
        depth = len(lines[start].text) - len(lines[start].text.lstrip())
        end = start + 1
        while end < len(lines) and len(lines[end].text) - len(lines[end].text.lstrip()) > depth:
            end += 1
        lines = [_Line(line.text[depth:], line.ref) for line in lines[start:end]]
    if options.roles:
        matches = {
            index
            for index, line in enumerate(lines)
            if (role := _ROLE.match(line.text)) and role[1].lower() in options.roles
        }
        lines = _select_subtrees(lines, matches, descendants=True)
    if interactive and not snapshot.metadata.interactive:
        generator = SemanticSnapshotGenerator()
        matches = {
            index
            for index, line in enumerate(lines)
            if (match := _line_ref(line, snapshot.refs))
            and generator._should_keep(
                match[0].role, match[0].name, match[1], interactive_only=True
            )[0]
        }
        lines = _select_subtrees(lines, matches, descendants=False)
    matched_lines = len(lines)
    if options.max_lines is not None:
        lines = lines[: options.max_lines]
    visible_refs = {line.ref for line in lines if line.ref is not None}
    truncated = len(lines) < matched_lines
    tree = "\n".join(line.text for line in lines) or "(empty)"
    if truncated:
        tree += f"\n[snapshot truncated: {len(lines)} of {matched_lines} matching lines returned]"
    return {
        "tree": tree,
        "refs_summary": [
            _summary(data, options.compact)
            for ref, data in snapshot.refs.items()
            if ref in visible_refs
        ],
        "view": {
            "compact": options.compact,
            "scope": options.scope,
            "roles": list(options.roles),
            "max_lines": options.max_lines,
            "total_lines": total_lines,
            "matched_lines": matched_lines,
            "returned_lines": len(lines),
            "total_refs": len(snapshot.refs),
            "returned_refs": len(visible_refs),
            "truncated": truncated,
            "filtered": bool(options.scope or options.roles or interactive),
            "interactive": interactive,
        },
    }
