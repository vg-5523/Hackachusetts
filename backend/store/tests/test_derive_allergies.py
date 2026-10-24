"""Tests for allergies list-merge in backend.store.derive.

Regression for the hero case: "no known allergies" (value []) followed by a
"penicillin" observation must derive to value ['penicillin'] with status
conflicted and BOTH sources preserved -- the real allergy must never be hidden
behind the earlier empty-list claim.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.store.derive import derive
from shared.schema import Event, FieldStatus


def _ts(minute: int) -> str:
    return datetime(2024, 2, 1, 14, minute, 0, tzinfo=timezone.utc).isoformat()


def _allergy_fact(evt_id: str, value, utt_id: str, quote: str, minute: int) -> Event:
    return Event(
        id=evt_id,
        ts=datetime(2024, 2, 1, 14, minute, 0, tzinfo=timezone.utc),
        kind="fact",
        payload={
            "path": "allergies",
            "value": value,
            "source": {"utterance_id": utt_id, "quote": quote, "ts": _ts(minute)},
            "confidence": 1.0,
        },
    )


def test_no_allergies_then_named_allergy_is_conflicted_with_value():
    """[] then ['penicillin'] -> value ['penicillin'], conflicted, both sources."""
    events = [
        _allergy_fact("f0", [], "u3", "no known allergies", 4),
        _allergy_fact("f1", ["penicillin"], "u7", "penicillin allergy bracelet", 12),
    ]
    record, _ = derive(events)

    assert record.allergies.value == ["penicillin"]
    assert record.allergies.status == FieldStatus.conflicted
    quotes = {s.quote for s in record.allergies.sources}
    assert quotes == {"no known allergies", "penicillin allergy bracelet"}
    ids = {s.utterance_id for s in record.allergies.sources}
    assert ids == {"u3", "u7"}


def test_named_allergy_then_no_allergies_is_conflicted_but_keeps_allergy():
    """['sulfa'] then [] (a later 'no allergies' claim) still surfaces sulfa and
    marks conflicted -- the empty claim never erases a named allergy."""
    events = [
        _allergy_fact("f0", ["sulfa"], "u1", "sulfa allergy", 2),
        _allergy_fact("f1", [], "u5", "no known allergies", 9),
    ]
    record, _ = derive(events)

    assert record.allergies.value == ["sulfa"]
    assert record.allergies.status == FieldStatus.conflicted


def test_two_distinct_allergies_union_without_false_conflict():
    """['penicillin'] then ['penicillin','sulfa'] -> union, not an empty-vs-
    nonempty contradiction, so it is not marked conflicted by this rule."""
    events = [
        _allergy_fact("f0", ["penicillin"], "u1", "penicillin allergy", 2),
        _allergy_fact("f1", ["penicillin", "sulfa"], "u2", "also a sulfa allergy", 5),
    ]
    record, _ = derive(events)

    assert record.allergies.value == ["penicillin", "sulfa"]
    assert record.allergies.status != FieldStatus.conflicted
    assert len(record.allergies.sources) == 2


def test_repeated_no_allergies_corroborates_not_conflicts():
    """Two 'no known allergies' observations corroborate: value stays [] and the
    field is not conflicted."""
    events = [
        _allergy_fact("f0", [], "u1", "no known allergies", 2),
        _allergy_fact("f1", [], "u2", "no known allergies", 5),
    ]
    record, _ = derive(events)

    assert record.allergies.value == []
    assert record.allergies.status != FieldStatus.conflicted
    # Deduped on (utterance_id, quote): distinct utterance ids -> two sources.
    assert len(record.allergies.sources) == 2
