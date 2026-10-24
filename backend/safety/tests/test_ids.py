"""Unit tests for the deterministic flag id."""

from __future__ import annotations

from backend.safety.ids import flag_id


def test_deterministic() -> None:
    a = flag_id("duplicate_dose", "duplicate:1191", ["q1", "q2"])
    b = flag_id("duplicate_dose", "duplicate:1191", ["q1", "q2"])
    assert a == b


def test_evidence_order_does_not_matter() -> None:
    a = flag_id("interaction", "nitro+sild", ["alpha", "beta"])
    b = flag_id("interaction", "nitro+sild", ["beta", "alpha"])
    assert a == b


def test_different_rule_key_differs_with_empty_evidence() -> None:
    a = flag_id("missing_info", "missing:allergies", [])
    b = flag_id("missing_info", "missing:age", [])
    assert a != b


def test_prefix_and_length() -> None:
    fid = flag_id("contradiction", "contradiction:allergies", ["x"])
    assert fid.startswith("contradiction:")
    assert len(fid) <= 64
    # type prefix + colon + 12 hex chars
    assert len(fid.split(":", 1)[1]) == 12
