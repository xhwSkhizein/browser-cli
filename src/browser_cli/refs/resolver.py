"""Semantic ref resolver adapted from bridgic-browser."""

from __future__ import annotations

import re
from typing import Any

from browser_cli.refs.models import LocatorSpec, RefData


class SemanticRefResolver:
    INTERACTIVE_ROLES = {
        "application",
        "alertdialog",
        "button",
        "checkbox",
        "combobox",
        "dialog",
        "grid",
        "gridcell",
        "link",
        "listbox",
        "menu",
        "menubar",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "progressbar",
        "radio",
        "radiogroup",
        "scrollbar",
        "search",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "tablist",
        "tabpanel",
        "textbox",
        "tree",
        "treegrid",
        "treeitem",
    }
    ROLE_TEXT_MATCH_ROLES = {
        "cell",
        "columnheader",
        "gridcell",
        "listitem",
        "row",
        "rowheader",
    }
    STRUCTURAL_NOISE_ROLES = {"generic", "group", "none", "presentation"}
    TEXT_LEAF_ROLES = {"text"}
    STRUCTURAL_NOISE_CSS = {
        "generic": 'div:not([role]), legend, [role="generic"]',
        "group": 'fieldset, details, optgroup, [role="group"]',
        "none": '[role="none"]',
        "presentation": '[role="presentation"]',
    }
    STRUCTURAL_NOISE_CSS_NAMED = {
        **STRUCTURAL_NOISE_CSS,
        "generic": 'div:not([role]), span:not([role]), legend, [role="generic"]',
    }

    @staticmethod
    def parse_ref(arg: str) -> str | None:
        raw = arg.strip()
        if raw.startswith("@"):
            raw = raw[1:]
        elif raw.startswith("ref="):
            raw = raw[4:]
        if re.fullmatch(r"[0-9a-fA-F]{8}", raw):
            return raw.lower()
        return None

    @staticmethod
    def _text_pattern(value: str, *, exact: bool) -> re.Pattern[str]:
        parts = [re.escape(part) for part in re.split(r"\s+", value.strip()) if part]
        joined = r"\s+".join(parts) if parts else ""
        if exact:
            return re.compile(rf"^\s*{joined}\s*$")
        return re.compile(joined)

    def get_locator(
        self,
        page: Any,
        ref_arg: str,
        refs: dict[str, RefData],
    ) -> Any | None:
        locator_spec = self.build_locator_spec(ref_arg, refs)
        if locator_spec is None:
            return None
        return self.get_locator_from_spec(page, locator_spec)

    def get_locator_from_spec(
        self,
        page: Any,
        locator_spec: LocatorSpec,
    ) -> Any | None:
        if not locator_spec.role:
            return None

        normalized_name = locator_spec.name.strip() if locator_spec.name and locator_spec.name.strip() else None
        normalized_text = (
            locator_spec.text_content.strip()
            if locator_spec.text_content and locator_spec.text_content.strip()
            else None
        )
        match_text = locator_spec.match_text
        child_text = locator_spec.child_text

        scope: Any = page
        if locator_spec.frame_path:
            for local_nth in locator_spec.frame_path:
                scope = scope.frame_locator("iframe").nth(local_nth)

        skip_nth = False

        if (
            normalized_name
            and locator_spec.role not in self.ROLE_TEXT_MATCH_ROLES
            and locator_spec.role not in self.STRUCTURAL_NOISE_ROLES
            and locator_spec.role not in self.TEXT_LEAF_ROLES
        ):
            locator = scope.get_by_role(locator_spec.role, name=normalized_name, exact=True)
        elif locator_spec.role in self.ROLE_TEXT_MATCH_ROLES and match_text:
            if locator_spec.role == "row":
                locator = scope.get_by_role("row").filter(has_text=self._text_pattern(match_text, exact=False))
            else:
                locator = scope.get_by_role(locator_spec.role).filter(
                    has_text=self._text_pattern(match_text, exact=True)
                )
        elif locator_spec.role in self.TEXT_LEAF_ROLES and match_text:
            locator = scope.get_by_text(match_text, exact=True)
            skip_nth = True
        elif locator_spec.role in self.STRUCTURAL_NOISE_ROLES and match_text:
            css = self.STRUCTURAL_NOISE_CSS.get(locator_spec.role)
            if css:
                locator = scope.locator(css).filter(has_text=self._text_pattern(match_text, exact=True))
            else:
                locator = scope.get_by_text(match_text, exact=True)
                skip_nth = True
        elif locator_spec.role in self.STRUCTURAL_NOISE_ROLES:
            if child_text:
                css = self.STRUCTURAL_NOISE_CSS.get(locator_spec.role)
                if css:
                    locator = scope.locator(css).filter(has_text=self._text_pattern(child_text, exact=True))
                else:
                    locator = scope.get_by_text(child_text, exact=True)
                skip_nth = True
            else:
                locator = scope.get_by_role(locator_spec.role)
        elif normalized_text:
            locator = scope.get_by_text(normalized_text, exact=True)
            skip_nth = True
        else:
            locator = scope.get_by_role(locator_spec.role, name=re.compile(r"^$"))

        if not skip_nth and locator_spec.nth is not None:
            locator = locator.nth(locator_spec.nth)
        return locator

    def build_locator_spec(self, ref_arg: str, refs: dict[str, RefData]) -> LocatorSpec | None:
        ref = self.parse_ref(ref_arg)
        if not ref:
            return None
        ref_data = refs.get(ref)
        if ref_data is None:
            return None
        normalized_name = ref_data.name.strip() if ref_data.name and ref_data.name.strip() else None
        normalized_text = (
            ref_data.text_content.strip()
            if ref_data.text_content and ref_data.text_content.strip()
            else None
        )
        match_text = normalized_name or normalized_text
        child_text = None
        if ref_data.role in self.STRUCTURAL_NOISE_ROLES:
            child_text = next(
                (
                    (child.name or child.text_content or "").strip()
                    for child in refs.values()
                    if child.parent_ref == ref
                    and (child.role in self.TEXT_LEAF_ROLES or child.role in self.STRUCTURAL_NOISE_ROLES)
                    and (child.name or child.text_content)
                ),
                None,
            )
        return LocatorSpec(
            ref=ref,
            role=ref_data.role,
            name=normalized_name,
            text_content=normalized_text,
            match_text=match_text,
            child_text=child_text,
            nth=ref_data.nth,
            tag=ref_data.tag,
            interactive=ref_data.interactive,
            frame_path=ref_data.frame_path,
            selector_recipe=ref_data.selector_recipe,
        )
