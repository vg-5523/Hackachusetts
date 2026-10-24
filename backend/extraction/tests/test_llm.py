"""Tests for backend.llm.call_llm with httpx fully mocked (no real network).

Covers: the request URL/header/body, response parsing, the single-retry on 429
and 5xx, the no-retry failure on other statuses (without leaking the key), and
that a missing key raises before any HTTP request is attempted.
"""

from __future__ import annotations

import json

import httpx
import pytest

import backend.llm as llm


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _gemini_payload(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.fixture
def no_sleep(monkeypatch):
    """Avoid real waits during retry tests."""
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)


def test_request_body_header_and_parsing(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-key-123")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.0-flash")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200, _gemini_payload('{"facts": []}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    out = llm.call_llm("EXTRACT THIS")

    assert out == '{"facts": []}'
    # URL targets the generateContent endpoint for the configured model.
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    # Key travels only in the x-goog-api-key header.
    assert captured["headers"]["x-goog-api-key"] == "secret-key-123"
    # Body shape matches the Gemini contract.
    body = captured["json"]
    assert body["contents"] == [{"parts": [{"text": "EXTRACT THIS"}]}]
    assert body["generationConfig"]["temperature"] == 0
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["timeout"] == 20.0


def test_missing_key_raises_before_request(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # A local .env must not supply the key for this assertion.
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)

    calls = {"n": 0}

    def fake_post(*a, **k):  # pragma: no cover - must never run
        calls["n"] += 1
        return _FakeResponse(200, _gemini_payload("x"))

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.call_llm("hello")

    assert calls["n"] == 0  # no HTTP request was attempted


def test_retry_on_429_up_to_three_times_then_succeeds(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_API_KEY", "k")
    # Three 429s (the max retries) then a 200 success = 4 posts.
    statuses = iter([429, 429, 429, 200])
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        code = next(statuses)
        if code == 200:
            return _FakeResponse(200, _gemini_payload("ok"))
        return _FakeResponse(code)

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    assert llm.call_llm("p") == "ok"
    assert attempts["n"] == 4  # initial + 3 retries


def test_429_exhausts_retries_then_raises_without_key(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        return _FakeResponse(429)

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    with pytest.raises(RuntimeError) as exc:
        llm.call_llm("p")
    assert "super-secret" not in str(exc.value)
    assert "429" in str(exc.value)
    assert attempts["n"] == 4  # initial + 3 retries, then give up


def test_5xx_retries_once_then_raises_without_key(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        return _FakeResponse(503)

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    with pytest.raises(RuntimeError) as exc:
        llm.call_llm("p")
    assert "super-secret" not in str(exc.value)
    assert "503" in str(exc.value)
    assert attempts["n"] == 2  # initial + one 5xx retry


def test_thinking_budget_fallback_on_400(monkeypatch, no_sleep):
    """A 400 on thinkingBudget=0 falls back to the low budget, then succeeds;
    LAST_THINKING_MODE records which mode worked."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    bodies = []

    def fake_post(url, headers=None, json=None, timeout=None):
        bodies.append(json)
        gc = json["generationConfig"]
        budget = gc.get("thinkingConfig", {}).get("thinkingBudget")
        if budget == 0:
            return _FakeResponse(400)  # model rejects budget 0
        return _FakeResponse(200, _gemini_payload("done"))

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    assert llm.call_llm("p") == "done"
    # First attempt used budget 0, second used the low budget.
    assert bodies[0]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
    assert bodies[1]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 128
    assert llm.LAST_THINKING_MODE == "thinkingBudget=low"


def test_all_thinking_modes_400_raises_without_key(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        return _FakeResponse(400)

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    with pytest.raises(RuntimeError) as exc:
        llm.call_llm("p")
    assert "super-secret" not in str(exc.value)
    assert attempts["n"] == 3  # one post per thinking mode


def test_transport_error_retries_then_raises_without_key(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    with pytest.raises(RuntimeError) as exc:
        llm.call_llm("p")
    assert "super-secret" not in str(exc.value)
    assert attempts["n"] == 2  # initial + one retry
