from __future__ import annotations

from browser_cli.refs.generator import SemanticSnapshotGenerator
from browser_cli.refs.resolver import SemanticRefResolver


def test_parse_ref_accepts_supported_formats() -> None:
    resolver = SemanticRefResolver()
    assert resolver.parse_ref("deadbeef") == "deadbeef"
    assert resolver.parse_ref("@deadbeef") == "deadbeef"
    assert resolver.parse_ref("ref=DEADBEEF") == "deadbeef"
    assert resolver.parse_ref("not-a-ref") is None


def test_compute_stable_ref_is_deterministic_and_frame_aware() -> None:
    generator = SemanticSnapshotGenerator()
    ref_a = generator._compute_stable_ref("button", "Save", (), 0)
    ref_b = generator._compute_stable_ref("button", "Save", (), 0)
    ref_c = generator._compute_stable_ref("button", "Save", (0,), 0)
    ref_d = generator._compute_stable_ref("button", "Save", (), 1)

    assert ref_a == ref_b
    assert ref_a != ref_c
    assert ref_a != ref_d


def test_normalize_raw_snapshot_strips_yaml_quote_wrapping() -> None:
    raw = """- heading "Normal"\n- 'paragraph "Quoted \\'\\'Name\\'\\'" [ref=e1]':"""
    normalized = SemanticSnapshotGenerator._normalize_raw_snapshot(raw)
    assert "paragraph" in normalized
    assert "''" not in normalized
