"""Unit tests for the read-through on-disk cache."""

from __future__ import annotations

from pathlib import Path

from backend.safety.cache import cached


def test_miss_calls_fetch_and_writes(tmp_path: Path) -> None:
    calls = {"n": 0}

    def fetch() -> dict:
        calls["n"] += 1
        return {"rxcui": "1191"}

    value = cached("rxnorm", "aspirin", fetch, cache_dir=tmp_path)
    assert value == {"rxcui": "1191"}
    assert calls["n"] == 1
    assert (tmp_path / "rxnorm__aspirin.json").exists()


def test_hit_does_not_call_fetch(tmp_path: Path) -> None:
    def fetch() -> dict:
        return {"rxcui": "1191"}

    cached("rxnorm", "aspirin", fetch, cache_dir=tmp_path)

    def boom() -> dict:  # pragma: no cover - must never run
        raise AssertionError("fetch should not be called on a cache hit")

    value = cached("rxnorm", "aspirin", boom, cache_dir=tmp_path)
    assert value == {"rxcui": "1191"}
