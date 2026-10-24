"""Stub smoke test: call every endpoint in ``shared/api.md`` once (Req 9.1, 9.2).

This test exercises the Phase 1 FastAPI stub (``backend.main:app``) end to end
with FastAPI's :class:`~fastapi.testclient.TestClient`. It hits every endpoint
listed in the API contract exactly once and asserts both the HTTP status code
and that the response body is schema-valid against the shared Pydantic models
in ``shared/schema.py``.

Later checkpoints (and the account-level test runs in ``tasks.md``) rely on this
file to confirm the stub still serves the whole contract, so it is written to be
robust: a fixture resets the in-memory server state before each test so the
relay/ack/confirm mutations one test performs never bleed into another, and the
SSE test reads only a bounded number of lines so it can never hang.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend.main import app, state, stream
from shared.schema import (
    Event,
    FieldStatus,
    Flag,
    FlagStatus,
    PatientRecord,
    Sourced,
)


@pytest.fixture()
def client() -> TestClient:
    """A ``TestClient`` over a freshly reset server state.

    ``state.reset()`` re-copies the pristine mock, so mutations from relay, ack,
    and confirm in one test can never leak into another test's assertions. The
    ``with`` block drives FastAPI's startup/shutdown events (the startup hook
    also calls ``state.reset()``), matching how the app runs in production.
    """
    state.reset()
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------


def test_get_record_returns_valid_patient_record(client: TestClient) -> None:
    """``GET /api/record`` → 200 with a ``PatientRecord`` body."""
    response = client.get("/api/record")
    assert response.status_code == 200
    # ``model_validate`` raises if the body is not schema-valid, which fails
    # the test with a descriptive pydantic error.
    PatientRecord.model_validate(response.json())


def test_get_flags_returns_list_of_valid_flags(client: TestClient) -> None:
    """``GET /api/flags`` → 200 with a list whose items validate as ``Flag``."""
    response = client.get("/api/flags")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for item in body:
        Flag.model_validate(item)


def test_get_sbar_returns_string(client: TestClient) -> None:
    """``GET /api/sbar`` → 200 with a JSON ``str`` body."""
    response = client.get("/api/sbar")
    assert response.status_code == 200
    assert isinstance(response.json(), str)


def test_get_pre_alert_returns_string(client: TestClient) -> None:
    """``GET /api/preAlert`` → 200 with a JSON ``str`` body."""
    response = client.get("/api/preAlert")
    assert response.status_code == 200
    assert isinstance(response.json(), str)


def test_get_checklist_returns_list_of_strings(client: TestClient) -> None:
    """``GET /api/checklist`` → 200 with a JSON ``list[str]`` body."""
    response = client.get("/api/checklist")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert all(isinstance(item, str) for item in body)


def test_get_events_returns_list_of_valid_events(client: TestClient) -> None:
    """``GET /api/events`` → 200 with a list whose items validate as ``Event``."""
    response = client.get("/api/events")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for item in body:
        Event.model_validate(item)


# ---------------------------------------------------------------------------
# POST /api/utterance + scenarios
# ---------------------------------------------------------------------------


def test_post_utterance_returns_valid_patient_record(client: TestClient) -> None:
    """``POST /api/utterance`` with a valid ``{text, ts}`` → 200 ``PatientRecord``."""
    payload = {
        "text": "68 year old male, chest pain, aspirin given.",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/utterance", json=payload)
    assert response.status_code == 200
    PatientRecord.model_validate(response.json())


def test_get_scenarios_lists_stemi_hero(client: TestClient) -> None:
    """``GET /api/scenarios`` → 200 with a ``list[str]`` containing ``stemi_hero``."""
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert all(isinstance(item, str) for item in body)
    assert "stemi_hero" in body


def test_post_scenario_play_returns_valid_patient_record(
    client: TestClient,
) -> None:
    """``POST /api/scenario/stemi_hero/play`` → 200 with a ``PatientRecord``."""
    response = client.post("/api/scenario/stemi_hero/play")
    assert response.status_code == 200
    PatientRecord.model_validate(response.json())


# ---------------------------------------------------------------------------
# Flag state machine: relay then ack the same flag
# ---------------------------------------------------------------------------


def test_relay_then_ack_flow(client: TestClient) -> None:
    """Relay a real flag (→ ``relayed``), then ack that same flag (→ ``acknowledged``).

    The flag id is taken from a live ``GET /api/flags`` call rather than
    hard-coded, so the test tracks whatever the mock ships. Because the fixture
    resets state first, the flag starts ``open`` and the forward-only machine
    ``open → relayed → acknowledged`` applies.
    """
    flags = client.get("/api/flags")
    assert flags.status_code == 200
    flag_list = flags.json()
    assert flag_list, "the mock must ship at least one flag to exercise relay/ack"
    flag_id = flag_list[0]["id"]

    relayed = client.post(f"/api/flags/{flag_id}/relay")
    assert relayed.status_code == 200
    relayed_flag = Flag.model_validate(relayed.json())
    assert relayed_flag.status is FlagStatus.relayed

    acked = client.post(f"/api/flags/{flag_id}/ack")
    assert acked.status_code == 200
    acked_flag = Flag.model_validate(acked.json())
    assert acked_flag.status is FlagStatus.acknowledged


# ---------------------------------------------------------------------------
# Field confirm
# ---------------------------------------------------------------------------


def test_confirm_age_field(client: TestClient) -> None:
    """``POST /api/fields/age/confirm`` → 200 with a confirmed ``Sourced`` body."""
    response = client.post("/api/fields/age/confirm")
    assert response.status_code == 200
    # ``age`` is a ``Sourced[str]``; validate the Sourced shape and status.
    sourced = Sourced.model_validate(response.json())
    assert sourced.status is FieldStatus.confirmed


# ---------------------------------------------------------------------------
# SSE stream — bounded read so the test cannot hang
# ---------------------------------------------------------------------------


def _parse_sse_event_names(frame_text: str, into: list[str]) -> None:
    """Append every SSE ``event:`` name found in ``frame_text`` to ``into``.

    A single yielded frame is ``event: <name>\\ndata: <json>\\n\\n``; splitting
    on newlines and keeping the lines that start with ``event:`` recovers the
    event name regardless of how frames are chunked together.
    """
    for line in frame_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("event:"):
            into.append(stripped[len("event:") :].strip())


async def _collect_initial_stream_events(max_frames: int = 12) -> tuple[int, str, list[str]]:
    """Drive the real ``/api/stream`` generator and collect its opening events.

    Why not ``client.stream(...)``? The pinned ``starlette`` ``TestClient`` is
    not truly streaming: its transport runs the ASGI app to completion and
    buffers the whole body before handing back a response, so a request against
    an endpoint that streams forever deadlocks on entry — the server generator
    only ends on client disconnect, but the harness only signals disconnect once
    the generator has ended. There is no client-side bounded read that escapes
    that loop.

    Instead we exercise the endpoint's own async generator directly against a
    real :class:`~fastapi.Request`. The request's ASGI ``receive`` reports
    ``http.disconnect`` immediately, so ``request.is_disconnected()`` is true the
    first time the steady-state loop checks it: the generator yields its three
    initial frames (``record``, ``flags``, ``clocks``) and then exits on the very
    next iteration instead of settling into the 1 s ``clocks`` cadence. This runs
    the genuine endpoint code — no mocks, no fakes — and cannot hang.

    Returns the HTTP status code, the ``content-type`` header, and the ordered
    list of SSE event names observed.
    """

    async def receive() -> dict[str, str]:
        # A disconnected client: the generator's ``is_disconnected()`` check
        # returns True on its first steady-state iteration, so it stops after the
        # initial burst rather than streaming ``clocks`` forever.
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/stream",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope, receive)

    response = await stream(request)

    status_code = response.status_code
    content_type = response.headers.get("content-type", "")

    seen_events: list[str] = []
    frames = 0
    # Hard safety bound on frames so even a misbehaving generator cannot loop
    # forever; the initial burst is three frames, well under the cap.
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        _parse_sse_event_names(text, seen_events)
        frames += 1
        if len(seen_events) >= 3 or frames >= max_frames:
            break

    # Close the generator so it cannot keep running after we stop reading.
    aclose = getattr(response.body_iterator, "aclose", None)
    if aclose is not None:
        await aclose()

    return status_code, content_type, seen_events


def test_stream_emits_initial_record_flags_clocks(client: TestClient) -> None:
    """``GET /api/stream`` → 200 ``text/event-stream`` with the initial burst.

    The endpoint emits ``record``, ``flags``, ``clocks`` on connect and then a
    ``clocks`` event once per second forever. This test reads only the three
    initial events and then stops, so it can never hang on the periodic cadence.

    It drives the real endpoint generator via :func:`_collect_initial_stream_events`
    (see that helper for why ``client.stream`` would deadlock under the pinned
    test harness) and asserts a 200 status, a ``text/event-stream`` content type,
    that at least three events were seen, and that the first three are exactly
    ``record``, ``flags``, ``clocks`` in order.

    The ``client`` fixture is requested so server state is reset first, keeping
    this test consistent with the rest of the file.
    """
    status_code, content_type, seen_events = asyncio.run(
        asyncio.wait_for(_collect_initial_stream_events(), timeout=10)
    )

    assert status_code == 200
    assert content_type.startswith("text/event-stream")
    assert len(seen_events) >= 3
    assert seen_events[:3] == ["record", "flags", "clocks"]
