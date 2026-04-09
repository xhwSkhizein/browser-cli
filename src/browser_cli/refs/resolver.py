"""Semantic ref resolver adapted from bridgic-browser."""

from __future__ import annotations

import re
from typing import Any

from browser_cli.refs.models import RefData


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

        scope: Any = page
        if ref_data.frame_path:
            for local_nth in ref_data.frame_path:
                scope = scope.frame_locator("iframe").nth(local_nth)

        skip_nth = False

        if (
            normalized_name
            and ref_data.role not in self.ROLE_TEXT_MATCH_ROLES
            and ref_data.role not in self.STRUCTURAL_NOISE_ROLES
            and ref_data.role not in self.TEXT_LEAF_ROLES
        ):
            locator = scope.get_by_role(ref_data.role, name=normalized_name, exact=True)
        elif ref_data.role in self.ROLE_TEXT_MATCH_ROLES and match_text:
            if ref_data.role == "row":
                locator = scope.get_by_role("row").filter(has_text=self._text_pattern(match_text, exact=False))
            else:
                locator = scope.get_by_role(ref_data.role).filter(
                    has_text=self._text_pattern(match_text, exact=True)
                )
        elif ref_data.role in self.TEXT_LEAF_ROLES and match_text:
            locator = scope.get_by_text(match_text, exact=True)
            skip_nth = True
        elif ref_data.role in self.STRUCTURAL_NOISE_ROLES and match_text:
            css = self.STRUCTURAL_NOISE_CSS.get(ref_data.role)
            if css:
                locator = scope.locator(css).filter(has_text=self._text_pattern(match_text, exact=True))
            else:
                locator = scope.get_by_text(match_text, exact=True)
                skip_nth = True
        elif ref_data.role in self.STRUCTURAL_NOISE_ROLES:
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
            if child_text:
                css = self.STRUCTURAL_NOISE_CSS.get(ref_data.role)
                if css:
                    locator = scope.locator(css).filter(has_text=self._text_pattern(child_text, exact=True))
                else:
                    locator = scope.get_by_text(child_text, exact=True)
                skip_nth = True
            else:
                locator = scope.get_by_role(ref_data.role)
        elif normalized_text:
            locator = scope.get_by_text(normalized_text, exact=True)
            skip_nth = True
        else:
            locator = scope.get_by_role(ref_data.role, name=re.compile(r"^$"))

        if not skip_nth and ref_data.nth is not None:
            locator = locator.nth(ref_data.nth)
        return locator
