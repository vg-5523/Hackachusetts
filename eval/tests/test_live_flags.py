"""Live flags are always the CURRENT safety evaluation (store-outputs req 2).

GET /api/flags, the SSE flags event, and the outputs must reflect what
``safety.evaluate`` produces for the record derived right now -- not the folded
``flag_raised`` snapshots in the log. A flag that evaluate no longer produces
must disappear, while relay/ack progress recorded in the log is overlaid by id.

These tests exercise ``backend.main._live_record_and_flags`` directly against a
controlled in-memory event log (persistence is redirected to a temp path, so the
real event_log.json is never touched).
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared.schema import Event, FlagStatus


def _fact(eid, path, value, uid, quote, minute):
    return Event(
        id=eid,
        ts=datetime(2024, 2, 1, 14, minute, tzinfo=timezone.utc),
        kind="fact",
        payload={
            "path": path,
            "value": value,
            "source": {"utterance_id": uid, "quote": quote,
                       "ts": f"2024-02-01T14:{minute:02d}:00+00:00"},
            "confidence": 0.9,
        },
    )


@pytest.fixture()
def live_main(tmp_path, monkeypatch):
    """Import backend.main in live mode with persistence on a temp path."""
    monkeypatch.setenv("SCRIBE_MODE", "live")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    import backend.store.persist as persist
    log_path = tmp_path / "event_log.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", log_path)
    import backend.store.log as log
    monkeypatch.setattr(log.persist, "DEFAULT_PATH", log_path)

    import backend.main as main
    main = importlib.reload(main)  # re-read SCRIBE_MODE under the env override
    import backend.store as store
    store.reset()
    return main, store


def test_conflicted_allergies_yields_contradiction_flag(live_main):
    main, store = live_main
    # No allergies, then a named allergy -> allergies conflicted -> a
    # contradiction flag is the CURRENT evaluation.
    store.reset()
    for e in [
        _fact("e0", "allergies", [], "u1", "no known allergies", 1),
        _fact("e1", "allergies", ["penicillin"], "u2", "penicillin bracelet", 2),
    ]:
        store.append(e)

    record, flags = main._live_record_and_flags()
    assert record.allergies.status.value == "conflicted"
    types = {f.type.value for f in flags}
    assert "contradiction" in types
    # No stale "allergies unknown" missing_info flag, since allergies is known.
    assert not any(
        f.type.value == "missing_info" and "allerg" in f.message.lower()
        for f in flags
    )


def test_relay_status_is_overlaid_on_current_flags(live_main):
    main, store = live_main
    store.reset()
    for e in [
        _fact("e0", "allergies", [], "u1", "no known allergies", 1),
        _fact("e1", "allergies", ["penicillin"], "u2", "penicillin bracelet", 2),
    ]:
        store.append(e)

    _, flags = main._live_record_and_flags()
    contradiction = next(f for f in flags if f.type.value == "contradiction")
    assert contradiction.status is FlagStatus.open

    # Relay it: append a flag_relayed event for that id.
    store.append(
        Event(
            id="r0",
            ts=datetime(2024, 2, 1, 14, 5, tzinfo=timezone.utc),
            kind="flag_relayed",
            payload={"flag_id": contradiction.id},
        )
    )
    _, flags2 = main._live_record_and_flags()
    relayed = next(f for f in flags2 if f.id == contradiction.id)
    # The flag still comes from evaluate(), but its status is overlaid.
    assert relayed.status is FlagStatus.relayed


def test_stale_flag_disappears_when_no_longer_produced(live_main):
    main, store = live_main
    # An empty record: missing_info flags are produced (required fields unknown).
    store.reset()
    _, empty_flags = main._live_record_and_flags()
    assert any(f.type.value == "missing_info" for f in empty_flags)

    # Supply the required fields so missing_info no longer fires for them.
    for e in [
        _fact("e0", "allergies", ["penicillin"], "u1", "penicillin", 1),
        _fact("e1", "chief_complaint", "chest pain", "u2", "chest pain", 2),
        _fact("e2", "age", "58", "u3", "58 year old", 3),
    ]:
        store.append(e)

    _, flags = main._live_record_and_flags()
    # The previously-present missing_info flags for those fields are gone: the
    # live list reflects the CURRENT evaluation, not stale snapshots.
    msg_fields = " ".join(f.message.lower() for f in flags if f.type.value == "missing_info")
    assert "allerg" not in msg_fields
    assert "chief_complaint" not in msg_fields
