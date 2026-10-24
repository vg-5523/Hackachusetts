"""Free-text fields merge instead of conflicting (store-outputs requirement 1).

``chief_complaint`` (and ``notes`` if ever added as a Sourced path) are free
text: a differing later observation must NOT mark the field ``conflicted``.
Instead the longer, more specific value is kept, both sources are merged, and
the status stays ``unverified``. Other scalar fields (e.g. suspected_condition)
keep the contradiction rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.store.derive import derive
from shared.schema import Event, FieldStatus


def _fact(eid: str, path: str, value, uid: str, quote: str, minute: int) -> Event:
    return Event(
        id=eid,
        ts=datetime(2024, 2, 1, 14, minute, tzinfo=timezone.utc),
        kind="fact",
        payload={
            "path": path,
            "value": value,
            "source": {
                "utterance_id": uid,
                "quote": quote,
                "ts": f"2024-02-01T14:{minute:02d}:00+00:00",
            },
            "confidence": 0.8,
        },
    )


def test_chief_complaint_merges_longer_value_not_conflicted():
    """A longer later observation replaces the value; status stays unverified."""
    events = [
        _fact("e0", "chief_complaint", "chest pain", "u1", "chest pain", 1),
        _fact(
            "e1",
            "chief_complaint",
            "crushing central chest pain radiating to the left arm",
            "u2",
            "crushing central chest pain radiating to the left arm",
            2,
        ),
    ]
    record, _ = derive(events)
    cc = record.chief_complaint
    assert cc.value == "crushing central chest pain radiating to the left arm"
    assert cc.status is FieldStatus.unverified
    assert cc.status is not FieldStatus.conflicted
    assert len(cc.sources) == 2


def test_chief_complaint_keeps_longer_when_shorter_arrives_second():
    """A shorter later observation does not shorten the value; no conflict."""
    events = [
        _fact("e0", "chief_complaint", "crushing substernal chest pain", "u1", "crushing substernal chest pain", 1),
        _fact("e1", "chief_complaint", "chest pain", "u2", "chest pain", 2),
    ]
    record, _ = derive(events)
    cc = record.chief_complaint
    assert cc.value == "crushing substernal chest pain"
    assert cc.status is FieldStatus.unverified
    assert len(cc.sources) == 2


def test_suspected_condition_still_conflicts():
    """Non-free-text scalar fields keep the contradiction rule (regression)."""
    events = [
        _fact("e0", "suspected_condition", "STEMI", "u1", "stemi", 1),
        _fact("e1", "suspected_condition", "stroke", "u2", "stroke", 2),
    ]
    record, _ = derive(events)
    sc = record.suspected_condition
    assert sc.value == "STEMI"  # old value kept
    assert sc.status is FieldStatus.conflicted
