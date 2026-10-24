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

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app, state
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


def test_stream_emits_initial_record_flags_clocks(client: TestClient) -> None:
    """``GET /api/stream`` → 200 ``text/event-stream`` with the initial burst.

    The stream emits a ``clocks`` event every second forever, so this test must
    never read it unboundedly. It reads at most ``MAX_LINES`` lines, records the
    SSE ``event:`` names in order until it has seen the three initial events,
    then breaks and closes the stream. It asserts the content type and that the
    first three event types are exactly ``record``, ``flags``, ``clocks`` in
    order.
    """
    max_lines = 50
    seen_events: list[str] = []

    with client.stream("GET", "/api/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        for line_number, line in enumerate(response.iter_lines()):
            if line_number >= max_lines:
                break
            # ``iter_lines`` yields str for a text stream; normalize defensively.
            text = line.decode() if isinstance(line, bytes) else line
            if text.startswith("event:"):
                seen_events.append(text[len("event:") :].strip())
            # Stop as soon as the initial burst has been observed so we never
            # fall into the steady 1 s ``clocks`` cadence.
            if len(seen_events) >= 3:
                break

    assert seen_events[:3] == ["record", "flags", "clocks"]
