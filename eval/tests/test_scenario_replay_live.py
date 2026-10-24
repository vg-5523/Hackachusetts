"""Live-mode scenario replay is idempotent (store-outputs).

Playing a scenario in live mode must first clear the Store (memory + the
event_log.json file) and then play, so replaying the same scenario always
starts from an empty record and yields an identical record each time.

The test drives the real FastAPI app in live mode with the event log redirected
to a temp file. It is fully OFFLINE: no Gemini call is made. We empty
LLM_API_KEY and stub load_dotenv so the extraction pipeline never reaches the
network; the committed scenario cache (and otherwise the deterministic rules
fallback) supplies extraction output. SCRIBE_MODE is read at import time, so we
set it and import backend.main fresh inside the fixture.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIO = "stemi_hero"


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    """A TestClient for backend.main in live mode, fully offline."""
    if not (REPO_ROOT / "scenarios" / f"{SCENARIO}.json").exists():
        pytest.skip(f"scenarios/{SCENARIO}.json not present")

    monkeypatch.setenv("SCRIBE_MODE", "live")
    monkeypatch.setenv("SCENARIO_PLAY_DELAY_S", "0")

    # Guarantee no network: no key, and .env cannot re-supply one. With the
    # committed cache present extraction replays from disk; otherwise it uses
    # the deterministic rules fallback. Either way: no Gemini call.
    monkeypatch.setenv("LLM_API_KEY", "")
    import backend.extraction as extraction
    import backend.llm as llm
    monkeypatch.setattr(extraction, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)

    def _no_network(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("call_llm must not be called in this offline test")

    monkeypatch.setattr(llm, "call_llm", _no_network)

    # Redirect persistence to a temp file BEFORE main's startup replay runs.
    from backend.store import persist, log as store_log

    monkeypatch.setattr(persist, "DEFAULT_PATH", tmp_path / "event_log.json")
    store_log.reset()

    # Import backend.main fresh so module-level SCRIBE_MODE picks up "live".
    sys.modules.pop("backend.main", None)
    main = importlib.import_module("backend.main")

    with TestClient(main.app) as client:
        yield client

    sys.modules.pop("backend.main", None)


def _play(client) -> dict:
    resp = client.post(f"/api/scenario/{SCENARIO}/play")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_replay_scenario_twice_is_identical(live_client):
    """Two consecutive plays of the same scenario return identical records."""
    first = _play(live_client)
    second = _play(live_client)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_replay_clears_so_record_does_not_accumulate(live_client):
    """A second play clears first, so the event log does not accumulate: the
    event count after two plays equals the count after one."""
    import backend.store as store

    _play(live_client)
    events_after_one = len(store.events())

    _play(live_client)
    events_after_two = len(store.events())

    assert events_after_two == events_after_one
