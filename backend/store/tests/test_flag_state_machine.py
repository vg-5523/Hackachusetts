# Feature: store-outputs, Property 3: Flag state machine
"""Property-based test for the flag lifecycle state machine (Property 3).

**Validates: Requirements 8.3, 2.5**

Two properties are exercised here:

1. **Forward-only flag state machine over the HTTP relay/ack endpoints.**
   The lifecycle is ``open -> relayed -> acknowledged`` and nothing runs it
   backward. Driving the stub ``POST /api/flags/{id}/relay`` and
   ``POST /api/flags/{id}/ack`` endpoints with a Hypothesis-generated sequence
   of actions, every response must match the state machine:

   - ``relay``: ``open -> relayed`` (200), ``relayed -> relayed`` idempotent
     (200), ``acknowledged`` -> relay is illegal (409).
   - ``ack``: ``relayed -> acknowledged`` (200), ``acknowledged ->
     acknowledged`` idempotent (200), ``open`` -> ack is illegal (409, ack
     before relay).
   - an unknown flag id -> 404 for either action.
   - on 200 the returned flag's ``status`` equals the expected new status; on
     409/404 the flag's status is UNCHANGED (verified by a follow-up GET).

   The test runs against ``backend.main.app`` in STUB mode (the default), whose
   stub endpoints implement exactly this state machine. ``state.reset()`` runs
   at the start of every example so flags always start ``open`` and no example
   bleeds into the next.

2. **Flag-status stability at the derive level (Req 2.5).** Re-raising a flag
   that already exists must refresh its content but preserve the existing
   status: a ``flag_raised(open)`` then ``flag_relayed`` then
   ``flag_raised(open again)`` sequence must leave the derived flag ``relayed``,
   not reset to ``open``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

# STUB mode is required so the canned mock flags exist and the stub endpoints
# implement the state machine under test. Force it before importing the app,
# which reads SCRIBE_MODE once at import time.
os.environ.setdefault("SCRIBE_MODE", "stub")

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.main import app, state
from backend.store.derive import derive
from shared.schema import (
    Citation,
    Event,
    Flag,
    FlagSeverity,
    FlagStatus,
    FlagType,
)

# A module-global TestClient (not a fixture), so Hypothesis does not warn about
# a function-scoped fixture being reused across examples. State is reset at the
# start of each example body instead.
client = TestClient(app)

# A bogus id that is never a real flag id, used to drive the 404 path.
BOGUS_ID = "does-not-exist"


def _real_flag_ids() -> list[str]:
    """Read the current real flag ids from the stub after a reset."""
    response = client.get("/api/flags")
    assert response.status_code == 200
    return [flag["id"] for flag in response.json()]


def _status_of(flag_id: str) -> str | None:
    """Return the current status of ``flag_id`` per a fresh GET, or None."""
    response = client.get("/api/flags")
    assert response.status_code == 200
    for flag in response.json():
        if flag["id"] == flag_id:
            return flag["status"]
    return None


# Forward-only transition table for the two actions, keyed by current status.
# Each entry gives (expected_http_status, resulting_status_on_200_or_None).
_RELAY_RULES = {
    "open": (200, "relayed"),
    "relayed": (200, "relayed"),  # idempotent
    "acknowledged": (409, None),  # illegal: no going back / sideways
}
_ACK_RULES = {
    "open": (409, None),  # illegal: ack before relay
    "relayed": (200, "acknowledged"),
    "acknowledged": (200, "acknowledged"),  # idempotent
}


def _action_strategy(real_ids: list[str]):
    """A strategy over ("relay"|"ack", flag_id) actions.

    ``flag_id`` is drawn from the real ids most of the time, with an occasional
    bogus id so the 404 path is exercised too.
    """
    verbs = st.sampled_from(["relay", "ack"])
    # Weight toward real ids so the state machine actually advances, but keep a
    # healthy chance of the bogus id to cover 404s.
    ids = st.sampled_from(real_ids + [BOGUS_ID, BOGUS_ID])
    return st.tuples(verbs, ids)


@settings(max_examples=100, derandomize=True, deadline=None)
@given(data=st.data())
def test_flag_state_machine_forward_only(data: st.DataObject) -> None:
    """A random sequence of relay/ack actions obeys the forward-only machine."""
    # Fresh baseline for this example: every real flag starts ``open``.
    state.reset()
    real_ids = _real_flag_ids()
    assert real_ids, "stub must expose at least one mock flag"

    # The EXPECTED status model, per real flag id, mirrors the API's machine.
    expected: dict[str, str] = {flag_id: "open" for flag_id in real_ids}

    actions = data.draw(
        st.lists(_action_strategy(real_ids), min_size=1, max_size=25)
    )

    for verb, flag_id in actions:
        endpoint = f"/api/flags/{flag_id}/{'relay' if verb == 'relay' else 'ack'}"
        response = client.post(endpoint)

        if flag_id == BOGUS_ID:
            # Unknown id -> 404 for either action; nothing changes.
            assert response.status_code == 404, (verb, flag_id, response.text)
            continue

        current = expected[flag_id]
        rules = _RELAY_RULES if verb == "relay" else _ACK_RULES
        want_status, want_new = rules[current]

        assert response.status_code == want_status, (
            verb,
            flag_id,
            current,
            response.status_code,
            response.text,
        )

        if want_status == 200:
            # The body is the updated flag; its status is the new status.
            body = response.json()
            assert body["id"] == flag_id
            assert body["status"] == want_new
            expected[flag_id] = want_new
        else:
            # 409: the flag's status must be UNCHANGED. Confirm via a GET.
            assert _status_of(flag_id) == current

    # Final cross-check: a GET of every flag matches the expected model, and no
    # flag ever regressed to an earlier lifecycle state.
    order = {"open": 0, "relayed": 1, "acknowledged": 2}
    for flag_id, want in expected.items():
        got = _status_of(flag_id)
        assert got == want, (flag_id, got, want)
        # Forward-only: the final state is never before where the model says.
        assert order[got] >= order["open"]


# ---------------------------------------------------------------------------
# Flag-status stability at the derive level (Req 2.5)
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)


def _flag(flag_id: str, status: FlagStatus) -> Flag:
    """Build a minimal valid :class:`Flag` with the given id and status."""
    return Flag(
        id=flag_id,
        type=FlagType.duplicate_dose,
        severity=FlagSeverity.warn,
        message="Potential duplicate dose detected.",
        say_to_crew="Confirm total dose before further administration.",
        evidence=["gave aspirin", "gave aspirin again"],
        source_ref=Citation(
            name="Synthetic reference",
            url="https://example.org/meds/aspirin",
        ),
        status=status,
    )


def _flag_raised_event(event_id: str, flag: Flag) -> Event:
    return Event(
        id=event_id,
        ts=_TS,
        kind="flag_raised",
        payload={"flag": flag.model_dump(mode="json")},
    )


def _flag_relayed_event(event_id: str, flag_id: str) -> Event:
    return Event(
        id=event_id,
        ts=_TS,
        kind="flag_relayed",
        payload={"flag_id": flag_id},
    )


def test_reraise_does_not_reset_flag_status() -> None:
    """Re-raising an existing flag preserves its advanced status (Req 2.5)."""
    flag_id = "duplicate_dose:stability"

    events = [
        # Raise the flag (open).
        _flag_raised_event("evt-0", _flag(flag_id, FlagStatus.open)),
        # Advance it to relayed.
        _flag_relayed_event("evt-1", flag_id),
        # Re-raise the SAME id with an ``open`` payload: content refreshes but
        # the status must stay ``relayed``, not reset to ``open``.
        _flag_raised_event("evt-2", _flag(flag_id, FlagStatus.open)),
    ]

    _, flags = derive(events)

    assert len(flags) == 1
    assert flags[0].id == flag_id
    assert flags[0].status is FlagStatus.relayed


def test_reraise_preserves_acknowledged_status() -> None:
    """Stability also holds once a flag has reached ``acknowledged`` (Req 2.5)."""
    flag_id = "duplicate_dose:acked"

    events = [
        _flag_raised_event("evt-0", _flag(flag_id, FlagStatus.open)),
        _flag_relayed_event("evt-1", flag_id),
        Event(
            id="evt-2",
            ts=_TS,
            kind="flag_acked",
            payload={"flag_id": flag_id},
        ),
        # Re-raise with ``open``: must remain ``acknowledged``.
        _flag_raised_event("evt-3", _flag(flag_id, FlagStatus.open)),
    ]

    _, flags = derive(events)

    assert len(flags) == 1
    assert flags[0].status is FlagStatus.acknowledged
