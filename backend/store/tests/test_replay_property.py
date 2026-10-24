# Feature: store-outputs, Property 2: Replay equals live derivation
"""Property 2: Replay equals live derivation.

**Validates: Requirements 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 8.2**

The append-only Event_Log is the single source of truth and ``derive`` is the
one pure fold over it, so two things must hold for *any* valid Event_Log:

A. Incremental folding equals whole-log folding. Folding ``apply_event`` one
   event at a time from the empty ``(PatientRecord(), [])`` state yields the
   SAME ``(record, flags)`` as ``derive(all_events)``. (``derive`` is literally
   that fold, so this pins down that ``apply_event`` is a pure step function
   whose accumulation never depends on anything but the running state — the
   conflict/append/stability rules hold throughout the fold.)

B. Persist/reload round-trip is transparent to derivation. Saving the log with
   ``persist.save`` and reloading it with ``persist.load`` produces a log that
   derives to the exact same ``(record, flags)`` as the original in-memory log.

Both tests generate a coherent sequence of events (facts that exercise the
same-value dedupe and different-value conflict rules, plus flag raise / relay /
ack events that exercise flag-status stability) so ``derive`` is driven over a
meaningful slice of its behavior. Equality is compared on the JSON model dumps
of the record and each flag.

A unique temporary directory is used for every persistence round-trip so the
real ``backend/store/event_log.json`` is never read or written.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from functools import reduce
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.store import persist
from backend.store.derive import apply_event, derive
from backend.store.validate import validate_event
from shared.schema import Event, Flag, PatientRecord


# --------------------------------------------------------------------------- #
# Fixed vocab the generators draw from. Small pools make repeats / re-raises   #
# likely, so the conflict and flag-stability rules are actually exercised.     #
# --------------------------------------------------------------------------- #

# (path, value) pairs for scalar ``fact`` events. Two distinct values per path
# so a run can observe the same value (dedupe) or a different value (conflict).
_SCALAR_FACTS: list[tuple[str, Any]] = [
    ("age", "45"),
    ("age", "72"),
    ("sex", "male"),
    ("sex", "female"),
    ("chief_complaint", "chest pain"),
    ("chief_complaint", "shortness of breath"),
    ("suspected_condition", "STEMI"),
    ("suspected_condition", "stroke"),
    ("eta", "5 min"),
    ("eta", "10 min"),
    ("acuity_esi", 1),
    ("acuity_esi", 2),
    ("allergies", ["penicillin"]),
    ("allergies", ["aspirin"]),
]

# A small pool of flag ids so re-raise (stability) and relay/ack of a known id
# are frequently generated.
_FLAG_IDS: list[str] = ["flag-a", "flag-b", "flag-c"]

_BASE_TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _source_payload(index: int) -> dict:
    """A valid ``SourceRef`` dict with an aware, ms-precision timestamp.

    The utterance id and quote are drawn from a tiny alphabet so that the same
    ``(utterance_id, quote)`` recurs across events — that collision is what the
    same-value dedupe rule (Req 2.2) is meant to collapse.
    """
    uid = f"u{index % 3}"
    quote = f"q{index % 2}"
    ts = (_BASE_TS + timedelta(milliseconds=index)).isoformat(
        timespec="milliseconds"
    )
    return {"utterance_id": uid, "quote": quote, "ts": ts}


def _flag_dict(flag_id: str) -> dict:
    """A minimal valid ``Flag`` dict for a ``flag_raised`` payload."""
    return {
        "id": flag_id,
        "type": "missing_info",
        "severity": "warn",
        "message": f"message for {flag_id}",
        "say_to_crew": f"relay {flag_id}",
        "evidence": [],
        "source_ref": {
            "name": "Protocol",
            "url": "https://example.com/protocol",
        },
        "status": "open",
    }


# --------------------------------------------------------------------------- #
# Strategy: produce a list of (kind, payload) step specs, then materialize     #
# them into Events with unique ids and strictly increasing ms-precision ts.    #
# --------------------------------------------------------------------------- #

@st.composite
def _step(draw: st.DrawFn) -> tuple[str, dict]:
    """Draw one coherent ``(kind, payload)`` spec (source/ts filled in later)."""
    kind = draw(
        st.sampled_from(
            ["fact", "flag_raised", "flag_relayed", "flag_acked"]
        )
    )

    if kind == "fact":
        path, value = draw(st.sampled_from(_SCALAR_FACTS))
        confidence = draw(
            st.floats(
                min_value=0.0,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        # ``source`` is a placeholder here; it is replaced per-event in
        # ``_build_events`` so each event gets a deterministic valid SourceRef.
        return "fact", {
            "path": path,
            "value": value,
            "source": None,
            "confidence": confidence,
        }

    flag_id = draw(st.sampled_from(_FLAG_IDS))
    if kind == "flag_raised":
        return "flag_raised", {"flag": _flag_dict(flag_id)}
    # flag_relayed / flag_acked reference an id from the same pool.
    return kind, {"flag_id": flag_id}


def _build_events(steps: list[tuple[str, dict]]) -> list[Event]:
    """Materialize step specs into validated Events.

    Each event gets a unique id ``e{i}`` and a strictly increasing aware,
    millisecond-precision timestamp. Fact sources are filled in with a valid
    ``SourceRef`` keyed on the event index. Every event is passed through
    ``validate_event`` so the log is valid by construction.
    """
    events: list[Event] = []
    for index, (kind, payload) in enumerate(steps):
        payload = dict(payload)
        if kind == "fact":
            payload["source"] = _source_payload(index)
        event = Event(
            id=f"e{index}",
            ts=_BASE_TS + timedelta(milliseconds=index),
            kind=kind,
            payload=payload,
        )
        # Guard: the generator targets valid events by construction; this makes
        # that an enforced invariant rather than an assumption.
        validate_event(event)
        events.append(event)
    return events


_events_strategy = st.lists(_step(), min_size=0, max_size=25).map(_build_events)


# --------------------------------------------------------------------------- #
# Equality helpers: PatientRecord / Flag are pydantic models, so compare their #
# JSON model dumps (stable, order-preserving for lists).                       #
# --------------------------------------------------------------------------- #

def _dump_state(state: tuple[PatientRecord, list[Flag]]) -> tuple[dict, list[dict]]:
    record, flags = state
    return (
        record.model_dump(mode="json"),
        [flag.model_dump(mode="json") for flag in flags],
    )


# --------------------------------------------------------------------------- #
# Property 2A: incremental fold == whole-log derive.                           #
# --------------------------------------------------------------------------- #

@settings(max_examples=100)
@given(events=_events_strategy)
def test_incremental_fold_equals_whole_derive(events: list[Event]) -> None:
    """Folding apply_event one event at a time equals derive(all_events)."""
    incremental = reduce(apply_event, events, (PatientRecord(), []))
    whole = derive(events)

    assert _dump_state(incremental) == _dump_state(whole)


# --------------------------------------------------------------------------- #
# Property 2B: persist/reload round-trip is transparent to derivation.         #
# --------------------------------------------------------------------------- #

@settings(max_examples=100)
@given(events=_events_strategy)
def test_persist_reload_then_derive_matches_live(events: list[Event]) -> None:
    """derive(events) == derive(load(save(events))) via a temp path.

    A fresh temporary directory is created for each example so the real
    ``backend/store/event_log.json`` is never touched.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="store_replay_"))
    try:
        log_path = tmp_dir / "event_log.json"
        persist.save(events, log_path)
        reloaded = persist.load(log_path)

        live = derive(events)
        replayed = derive(reloaded)

        assert _dump_state(live) == _dump_state(replayed)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
