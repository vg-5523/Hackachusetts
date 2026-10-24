"""Tests for the resilient write path in backend.store.persist.save.

Covers the three strategies: (1) os.replace retried up to 5 times with a wait
between tries, (2) plain-write fallback when every replace fails, and (3) a
warn-and-return (no raise) when even the plain write fails, so a live request is
never failed by a disk problem and the caller keeps the event in memory.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.store import persist
from backend.store import log as store_log
from shared.schema import Event


def _event(eid: str) -> Event:
    return Event(
        id=eid,
        ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        kind="utterance",
        payload={
            "utterance": {"id": "u1", "text": "hi", "ts": "2024-01-01T00:00:00+00:00"}
        },
    )


@pytest.fixture
def no_wait(monkeypatch):
    """Skip the 50 ms inter-retry sleeps so the tests run fast."""
    monkeypatch.setattr(persist.time, "sleep", lambda *_: None)


def test_replace_retries_then_succeeds(tmp_path, monkeypatch, no_wait):
    """os.replace fails the first 4 times, succeeds on the 5th; the file is
    written atomically and no retry wait leaks through."""
    path = tmp_path / "event_log.json"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] < persist.REPLACE_RETRIES:  # fail attempts 1..4
            raise OSError("transient lock")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(persist.os, "replace", flaky_replace)

    persist.save([_event("e1")], path)

    assert calls["n"] == persist.REPLACE_RETRIES  # retried up to the limit
    assert path.exists()
    assert persist.load(path)[0].id == "e1"
    # No leftover temp files.
    assert list(tmp_path.glob("*.tmp")) == []


def test_waits_between_replace_retries(tmp_path, monkeypatch):
    """A 50 ms wait happens between retries (one fewer wait than attempts)."""
    path = tmp_path / "event_log.json"
    waits = {"n": 0}
    monkeypatch.setattr(persist.time, "sleep", lambda *_: waits.__setitem__("n", waits["n"] + 1))

    def always_fail(src, dst, *a, **k):
        raise OSError("locked")

    monkeypatch.setattr(persist.os, "replace", always_fail)

    # Force the plain-write fallback to also fail so we exercise only the retry
    # waits here; the point is the count of inter-retry waits.
    def no_open(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", no_open)

    persist.save([_event("e1")], path)  # must not raise

    assert waits["n"] == persist.REPLACE_RETRIES - 1  # 4 waits across 5 tries


def test_plain_write_fallback_when_replace_always_fails(tmp_path, monkeypatch, no_wait):
    """When os.replace always fails, save falls back to a plain write and the
    file still ends up correct."""
    path = tmp_path / "event_log.json"

    def always_fail(src, dst, *a, **k):
        raise OSError("replace blocked")

    monkeypatch.setattr(persist.os, "replace", always_fail)

    persist.save([_event("e2")], path)  # must not raise

    assert path.exists()
    assert persist.load(path)[0].id == "e2"


def test_total_disk_failure_does_not_raise(tmp_path, monkeypatch, no_wait, caplog):
    """When both the atomic replace and the plain write fail, save logs a
    warning and returns WITHOUT raising (the event is kept in memory)."""
    path = tmp_path / "event_log.json"

    monkeypatch.setattr(
        persist.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("no replace"))
    )

    real_open = open

    def open_blocks_target(file, *a, **k):
        # Block only the plain write of the target log; allow temp files so the
        # atomic path reaches os.replace (which fails) first.
        if Path(file) == path and (a[:1] == ("w",) or k.get("mode") == "w"):
            raise OSError("disk full")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", open_blocks_target)

    with caplog.at_level("WARNING"):
        persist.save([_event("e3")], path)  # must not raise

    # File was never written, but no exception escaped.
    assert not path.exists()
    assert any("keeping events in memory only" in r.message for r in caplog.records)


def test_log_append_keeps_event_in_memory_on_disk_failure(tmp_path, monkeypatch, no_wait):
    """End-to-end: a total disk failure during append still commits the event to
    the in-memory log, so a live utterance request is never failed."""
    path = tmp_path / "event_log.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", path)
    store_log.reset()

    # Make every on-disk write fail: replace always errors, plain open errors.
    monkeypatch.setattr(
        persist.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    )
    real_open = open

    def open_fail_target(file, *a, **k):
        if Path(file) == path:
            raise OSError("disk full")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", open_fail_target)

    returned = store_log.append(_event("e4"))

    assert returned.id == "e4"
    assert [e.id for e in store_log.events()] == ["e4"]  # kept in memory
    assert not path.exists()  # disk write genuinely failed

    store_log.reset()  # leave the shared in-memory log clean for other tests
