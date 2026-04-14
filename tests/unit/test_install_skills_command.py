from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from browser_cli.commands import install_skills as install_skills_module
from browser_cli.errors import InvalidInputError


def _write_skill(root: Path, name: str, *, body: str | None = None) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body or f"# {name}\n", encoding="utf-8")
    return skill_dir


def test_get_skills_target_path_defaults_to_agents_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(install_skills_module.Path, "home", lambda: tmp_path)
    assert install_skills_module.get_skills_target_path(None) == tmp_path / ".agents" / "skills"


def test_get_skills_target_path_honors_explicit_target(tmp_path: Path) -> None:
    target = tmp_path / "custom-skills"
    assert install_skills_module.get_skills_target_path(str(target)) == target.resolve()


def test_discover_packaged_skills_returns_three_public_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source"
    for name in install_skills_module.PUBLIC_SKILL_NAMES:
        _write_skill(source_root, name)
    monkeypatch.setattr(install_skills_module, "_packaged_skills_root", lambda: source_root)

    discovered = install_skills_module.discover_packaged_skills()

    assert [item.name for item in discovered] == list(install_skills_module.PUBLIC_SKILL_NAMES)


def test_discover_packaged_skills_fails_when_a_required_skill_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source"
    _write_skill(source_root, "browser-cli-delivery")
    _write_skill(source_root, "browser-cli-explore")
    monkeypatch.setattr(install_skills_module, "_packaged_skills_root", lambda: source_root)

    with pytest.raises(InvalidInputError, match="browser-cli-converge"):
        install_skills_module.discover_packaged_skills()


def test_install_skills_from_paths_reports_install_and_update(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    skills = [
        install_skills_module.PackagedSkill(
            name="browser-cli-converge",
            source=_write_skill(source_root, "browser-cli-converge"),
        ),
        install_skills_module.PackagedSkill(
            name="browser-cli-delivery",
            source=_write_skill(source_root, "browser-cli-delivery"),
        ),
        install_skills_module.PackagedSkill(
            name="browser-cli-explore",
            source=_write_skill(source_root, "browser-cli-explore"),
        ),
    ]
    (target_root / "browser-cli-delivery").mkdir(parents=True)

    results = install_skills_module.install_skills_from_paths(skills, target_root, dry_run=True)

    assert results == [
        ("browser-cli-converge", "would install"),
        ("browser-cli-delivery", "would update"),
        ("browser-cli-explore", "would install"),
    ]


def test_install_skills_from_paths_replaces_existing_skill_directory(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source = _write_skill(source_root, "browser-cli-delivery", body="# new\n")
    target = target_root / "browser-cli-delivery"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# old\n", encoding="utf-8")
    (target / "stale.txt").write_text("stale\n", encoding="utf-8")

    results = install_skills_module.install_skills_from_paths(
        [install_skills_module.PackagedSkill(name="browser-cli-delivery", source=source)],
        target_root,
        dry_run=False,
    )

    assert results == [("browser-cli-delivery", "updated")]
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "# new\n"
    assert not (target / "stale.txt").exists()


def test_run_install_skills_command_uses_explicit_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    packaged = [
        install_skills_module.PackagedSkill(
            name=name,
            source=_write_skill(source_root, name),
        )
        for name in install_skills_module.PUBLIC_SKILL_NAMES
    ]
    monkeypatch.setattr(install_skills_module, "discover_packaged_skills", lambda: packaged)

    output = install_skills_module.run_install_skills_command(
        Namespace(dry_run=True, target=str(tmp_path / "custom"))
    )

    assert "Installing skills to" in output
    assert str((tmp_path / "custom").resolve()) in output
    assert "Total: 3 skill(s)" in output
