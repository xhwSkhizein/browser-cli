"""Sync packaged Browser CLI skill docs from the canonical repo skills."""

from __future__ import annotations

from pathlib import Path

SKILL_NAMES = (
    "browser-cli-delivery",
    "browser-cli-explore",
    "browser-cli-converge",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def canonical_skill_doc_path(root: Path, skill_name: str) -> Path:
    return root / "skills" / skill_name / "SKILL.md"


def packaged_skill_doc_path(root: Path, skill_name: str) -> Path:
    return root / "src" / "browser_cli" / "packaged_skills" / skill_name / "SKILL.md"


def expected_packaged_skill_docs(root: Path) -> dict[str, str]:
    return {
        skill_name: canonical_skill_doc_path(root, skill_name).read_text(encoding="utf-8")
        for skill_name in SKILL_NAMES
    }


def sync_packaged_skill_docs(root: Path) -> None:
    for skill_name, content in expected_packaged_skill_docs(root).items():
        destination = packaged_skill_doc_path(root, skill_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def main() -> int:
    sync_packaged_skill_docs(repo_root())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
