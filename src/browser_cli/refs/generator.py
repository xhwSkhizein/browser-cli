"""Semantic snapshot generation adapted from bridgic-browser."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any

from browser_cli.refs.models import RefData, SemanticSnapshot, SnapshotMetadata
from browser_cli.refs.resolver import SemanticRefResolver


@dataclass(slots=True, frozen=True)
class SnapshotOptions:
    interactive: bool = False
    full_page: bool = True


class SemanticSnapshotGenerator:
    CONTENT_ROLES = {"article", "cell", "columnheader", "heading", "main", "navigation", "region", "rowheader"}
    ALWAYS_REF_ROLES = {"cell", "columnheader", "gridcell", "listitem", "option", "row", "rowheader"}
    LANDMARK_ROLES = {"banner", "contentinfo", "complementary", "form", "main", "navigation", "region", "search"}
    SEMANTIC_ROLES = {
        "alert",
        "blockquote",
        "caption",
        "code",
        "definition",
        "document",
        "emphasis",
        "feed",
        "figure",
        "img",
        "insertion",
        "log",
        "marquee",
        "math",
        "meter",
        "note",
        "paragraph",
        "status",
        "strong",
        "subscript",
        "superscript",
        "term",
        "text",
        "time",
        "timer",
        "tooltip",
    }
    STRUCTURAL_ROLES = {"directory", "list", "row", "rowgroup", "table", "toolbar"}
    STRUCTURAL_NOISE_ROLES = SemanticRefResolver.STRUCTURAL_NOISE_ROLES
    TEXT_LEAF_ROLES = SemanticRefResolver.TEXT_LEAF_ROLES
    INTERACTIVE_ROLES = SemanticRefResolver.INTERACTIVE_ROLES
    _REF_NAMESPACE = "browser-cli-semantic-v1"
    _YAML_QUOTE_PATTERN = re.compile(r"^(\s*-\s*)'(.+)'(:{0,1})\s*$")
    _LINE_PATTERN = re.compile(
        r'^(\s*-\s*)'
        r'([A-Za-z0-9_/-]+)'
        r'(?:\s+"((?:[^"\\]|\\.)*)")?'
        r'(.*)$'
    )
    _REF_CLEAN_PATTERN = re.compile(r"\s*\[ref=[a-zA-Z0-9]+\]")
    _REF_EXTRACT_PATTERN = re.compile(r"\[ref=([a-zA-Z0-9]+)\]")

    async def page_snapshot_for_ai(self, page: Any) -> str:
        page_impl = page._impl_obj
        channel = page_impl._channel
        result = await channel.send_return_as_dict(
            "snapshotForAI",
            page_impl._timeout_settings.timeout,
            {"track": None, "timeout": 30000},
            is_internal=True,
        )
        return str(result.get("full") or "")

    @classmethod
    def _strip_yaml_quotes(cls, line: str) -> str:
        match = cls._YAML_QUOTE_PATTERN.match(line)
        if not match:
            return line
        prefix, content, colon = match.groups()
        content = content.replace("''", "'")
        return f"{prefix}{content}{colon}"

    @classmethod
    def _normalize_raw_snapshot(cls, raw: str) -> str:
        return "\n".join(cls._strip_yaml_quotes(line) for line in raw.splitlines())

    @staticmethod
    def _indent_level(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    @classmethod
    def _build_selector(cls, role: str, name: str | None = None, text_content: str | None = None) -> str:
        if name:
            escaped_name = name.replace('"', '\\"')
            if role in cls.TEXT_LEAF_ROLES:
                return f'get_by_text("{escaped_name}", exact=True)'
            return f'get_by_role("{role}", name="{escaped_name}", exact=True)'
        if text_content:
            escaped_text = text_content.replace('"', '\\"')
            return f'get_by_text("{escaped_text}", exact=True)'
        return f'get_by_role("{role}")'

    @classmethod
    def _compute_stable_ref(
        cls,
        role: str,
        name: str | None,
        frame_path: tuple[int, ...],
        nth: int,
    ) -> str:
        frame_str = ",".join(str(item) for item in frame_path)
        raw = f"{cls._REF_NAMESPACE}\x1f{role}\x1f{name or ''}\x1f{frame_str}\x1f{nth}"
        return hashlib.sha256(raw.encode("utf-8")).digest()[:4].hex()

    def _should_keep(self, role_lower: str, name: str | None, suffix: str, *, interactive_only: bool) -> tuple[bool, bool]:
        is_interactive = role_lower in self.INTERACTIVE_ROLES
        has_cursor_pointer = "[cursor=pointer]" in suffix
        has_aria_state = any(
            token in suffix
            for token in ("[pressed", "[expanded", "[checked", "[selected")
        )
        is_disabled = "[disabled]" in suffix

        should_keep = False
        should_have_ref = False
        if interactive_only:
            if is_interactive or has_cursor_pointer or has_aria_state or is_disabled:
                should_keep = True
                should_have_ref = True
            return should_keep, should_have_ref

        if is_interactive or has_cursor_pointer or has_aria_state or is_disabled:
            return True, True
        if role_lower in self.ALWAYS_REF_ROLES:
            return True, True
        if role_lower in self.CONTENT_ROLES | self.LANDMARK_ROLES | self.SEMANTIC_ROLES | self.STRUCTURAL_ROLES:
            return True, bool(name)
        if role_lower in self.STRUCTURAL_NOISE_ROLES:
            return bool(name), bool(name)
        return True, bool(name)

    async def get_snapshot(
        self,
        page: Any,
        *,
        page_id: str,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SemanticSnapshot:
        raw_snapshot = await self.page_snapshot_for_ai(page)
        if not raw_snapshot:
            captured_at = time.time()
            metadata = SnapshotMetadata(
                snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
                page_id=page_id,
                captured_url=str(page.url),
                captured_at=captured_at,
                interactive=interactive,
                full_page=full_page,
            )
            return SemanticSnapshot(tree="(empty)", refs={}, metadata=metadata)

        normalized = self._normalize_raw_snapshot(raw_snapshot)
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        captured_at = time.time()
        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            page_id=page_id,
            captured_url=str(page.url),
            captured_at=captured_at,
            interactive=interactive,
            full_page=full_page,
        )

        refs: dict[str, RefData] = {}
        result: list[str] = []
        depth_stack: list[tuple[int, bool, int, str | None]] = []
        iframe_stack: list[tuple[int, tuple[int, ...]]] = []
        iframe_local_counters: dict[tuple[int, ...], int] = {}
        occurrence_counts: dict[tuple[str, str | None, tuple[int, ...]], int] = {}

        def effective_depth(original_depth: int) -> int:
            depth = 0
            for stack_depth, kept, out_depth, _ in depth_stack:
                if stack_depth < original_depth and kept:
                    depth = out_depth + 1
            return depth

        def nearest_parent_ref(original_depth: int) -> str | None:
            for stack_depth, kept, _, ref in reversed(depth_stack):
                if stack_depth < original_depth and kept and ref is not None:
                    return ref
            return None

        for line in normalized.splitlines():
            if not line.strip():
                continue

            original_depth = self._indent_level(line)
            while depth_stack and depth_stack[-1][0] >= original_depth:
                depth_stack.pop()
            while iframe_stack and iframe_stack[-1][0] >= original_depth:
                iframe_stack.pop()

            match = self._LINE_PATTERN.match(line)
            if not match:
                stripped = line.lstrip()
                if interactive:
                    if stripped.startswith("- /") and any(kept for _, kept, _, _ in depth_stack):
                        result.append(f"{'  ' * effective_depth(original_depth)}- {stripped[2:]}")
                    continue
                if any(kept for _, kept, _, _ in depth_stack) or not depth_stack:
                    content = stripped[2:] if stripped.startswith("- ") else stripped
                    result.append(f"{'  ' * effective_depth(original_depth)}- {content}")
                continue

            _, role, name, suffix = match.groups()
            role_lower = role.lower()
            if not name and suffix and ":" in suffix:
                inline_label_match = re.search(r':\s*(?:"((?:[^"\\]|\\.)*)"|([^\n]+))\s*$', suffix)
                if inline_label_match:
                    name = (inline_label_match.group(1) or inline_label_match.group(2) or "").strip() or None

            if role.startswith("/"):
                if any(kept for _, kept, _, _ in depth_stack) or not depth_stack:
                    result.append(f"{'  ' * effective_depth(original_depth)}- {role}{suffix}")
                continue

            keep, have_ref = self._should_keep(role_lower, name, suffix, interactive_only=interactive)
            current_out_depth = effective_depth(original_depth)
            current_ref: str | None = None

            if not keep:
                depth_stack.append((original_depth, False, current_out_depth, None))
                if role_lower == "iframe":
                    parent_path = iframe_stack[-1][1] if iframe_stack else ()
                    local_index = iframe_local_counters.get(parent_path, 0)
                    iframe_local_counters[parent_path] = local_index + 1
                    iframe_stack.append((original_depth, tuple([*parent_path, local_index])))
                continue

            clean_suffix = self._REF_CLEAN_PATTERN.sub("", suffix).strip()
            pw_ref_match = self._REF_EXTRACT_PATTERN.search(suffix)
            playwright_ref = pw_ref_match.group(1) if pw_ref_match else None

            if interactive:
                enhanced = f"- {role}"
            else:
                enhanced = f"{'  ' * current_out_depth}- {role}"
            if name:
                enhanced += f' "{name}"'

            if have_ref:
                frame_path = iframe_stack[-1][1] if iframe_stack else ()
                occurrence_key = (role_lower, name, frame_path)
                nth = occurrence_counts.get(occurrence_key, 0)
                occurrence_counts[occurrence_key] = nth + 1
                ref = self._compute_stable_ref(role_lower, name, frame_path, nth)
                current_ref = ref
                text_content = None
                if clean_suffix and ":" in clean_suffix:
                    text_match = re.search(r':\s*"?([^"]+)"?\s*$', clean_suffix)
                    if text_match:
                        candidate = text_match.group(1).strip()
                        if candidate and candidate != name:
                            text_content = candidate
                ref_data = RefData(
                    ref=ref,
                    role=role_lower,
                    name=name,
                    nth=nth,
                    text_content=text_content,
                    tag=None,
                    interactive=role_lower in self.INTERACTIVE_ROLES,
                    parent_ref=nearest_parent_ref(original_depth),
                    frame_path=frame_path,
                    playwright_ref=playwright_ref,
                    selector_recipe=self._build_selector(role_lower, name, text_content),
                    snapshot_id=snapshot_id,
                    page_id=page_id,
                    captured_url=str(page.url),
                    captured_at=captured_at,
                )
                refs[ref] = ref_data
                enhanced += f" [ref={ref}]"
                if nth > 0 and name:
                    enhanced += f" [nth={nth}]"

            depth_stack.append((original_depth, keep, current_out_depth, current_ref))
            if role_lower == "iframe":
                parent_path = iframe_stack[-1][1] if iframe_stack else ()
                local_index = iframe_local_counters.get(parent_path, 0)
                iframe_local_counters[parent_path] = local_index + 1
                iframe_stack.append((original_depth, tuple([*parent_path, local_index])))

            if clean_suffix:
                if name and ":" in clean_suffix:
                    colon_match = re.search(r":\s*(.+?)\s*$", clean_suffix)
                    if colon_match:
                        raw_text = colon_match.group(1).strip()
                        if raw_text.startswith('"') and raw_text.endswith('"'):
                            raw_text = raw_text[1:-1]
                        if raw_text == name:
                            clean_suffix = clean_suffix[:colon_match.start()].rstrip()
                if clean_suffix == ":":
                    enhanced += ":"
                elif clean_suffix.startswith(":"):
                    enhanced += clean_suffix
                elif clean_suffix.endswith(":"):
                    enhanced += f" {clean_suffix[:-1]}:"
                else:
                    enhanced += f" {clean_suffix}"

            result.append(enhanced)

        dedup_counts: dict[tuple[str, str | None, tuple[int, ...]], int] = {}
        for item in refs.values():
            dedup_counts[(item.role, item.name, item.frame_path)] = dedup_counts.get((item.role, item.name, item.frame_path), 0) + 1
        for ref, data in list(refs.items()):
            if dedup_counts[(data.role, data.name, data.frame_path)] == 1:
                refs[ref] = replace(data, nth=None)

        tree = "\n".join(result) if result else "(empty)"
        return SemanticSnapshot(tree=tree, refs=refs, metadata=metadata)
