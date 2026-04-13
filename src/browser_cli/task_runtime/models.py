"""Task runtime models and metadata validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from browser_cli.task_runtime.errors import TaskMetadataError

REQUIRED_TASK_META_SECTIONS = (
    "task",
    "environment",
    "success_path",
    "recovery_hints",
    "failures",
    "knowledge",
)


@dataclass(slots=True, frozen=True)
class SnapshotRef:
    ref: str
    role: str
    name: str | None = None
    nth: int | None = None
    text_content: str | None = None
    interactive: bool = False
    parent_ref: str | None = None
    frame_path: tuple[int, ...] = ()


@dataclass(slots=True, frozen=True)
class SnapshotResult:
    page_id: str
    snapshot_id: str
    tree: str
    refs: tuple[SnapshotRef, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SnapshotResult:
        refs = tuple(
            SnapshotRef(
                ref=str(item["ref"]),
                role=str(item.get("role") or ""),
                name=str(item["name"]) if item.get("name") is not None else None,
                nth=int(item["nth"]) if item.get("nth") is not None else None,
                text_content=str(item["text_content"])
                if item.get("text_content") is not None
                else None,
                interactive=bool(item.get("interactive")),
                parent_ref=str(item["parent_ref"]) if item.get("parent_ref") is not None else None,
                frame_path=tuple(int(value) for value in (item.get("frame_path") or [])),
            )
            for item in payload.get("refs_summary", [])
        )
        return cls(
            page_id=str(payload.get("page_id") or ""),
            snapshot_id=str(payload.get("snapshot_id") or ""),
            tree=str(payload.get("tree") or "(empty)"),
            refs=refs,
        )

    def find_ref(self, *, role: str, name: str, nth: int = 0) -> str:
        matches = [item.ref for item in self.refs if item.role == role and item.name == name]
        if nth < 0 or nth >= len(matches):
            raise TaskMetadataError(f"Could not find ref role={role!r} name={name!r} nth={nth}.")
        return matches[nth]


@dataclass(slots=True, frozen=True)
class FlowContext:
    task_path: Path
    task_dir: Path
    artifacts_dir: Path
    automation_path: Path | None = None
    automation_name: str | None = None


def validate_task_metadata(payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TaskMetadataError(f"Task metadata must be a JSON object: {source}")
    missing = [key for key in REQUIRED_TASK_META_SECTIONS if key not in payload]
    if missing:
        joined = ", ".join(missing)
        raise TaskMetadataError(f"Task metadata is missing required sections ({joined}): {source}")
    task_section = payload.get("task")
    if not isinstance(task_section, dict):
        raise TaskMetadataError(f"Task metadata section 'task' must be an object: {source}")
    for key in ("id", "name", "goal"):
        value = task_section.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TaskMetadataError(f"Task metadata requires non-empty task.{key}: {source}")
    failures = payload.get("failures")
    if not isinstance(failures, list):
        raise TaskMetadataError(f"Task metadata section 'failures' must be an array: {source}")
    return payload
