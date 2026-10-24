"""Hero-scenario test for process_utterance with a mocked LLM (item 2).

Uses an isolated temp cache and a set LLM_API_KEY so the LLM branch runs, with
``backend.llm.call_llm`` patched to return a fixed JSON response per utterance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import backend.extraction as ex
from backend.extraction import cache as cache_mod
from shared.schema import FieldStatus, PatientRecord, Utterance


def _utt(uid: str, text: str, minute: int = 0) -> Utterance:
    return Utterance(
        id=uid,
        text=text,
        ts=datetime(2026, 10, 24, 12, minute, 0, tzinfo=timezone.utc),
    )


def _facts(*facts: dict) -> str:
    return json.dumps({"facts": list(facts)})


@pytest.fixture
def hero_env(tmp_path, monkeypatch):
    """Isolated cache + a set key so the mocked-LLM branch is exercised."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    return tmp_path


def _patch_llm(monkeypatch, response: str) -> None:
    monkeypatch.setattr("backend.llm.call_llm", lambda prompt: response)


def test_hero_allergies_then_meds(hero_env, monkeypatch):
    rec = PatientRecord()

    # 1. "no known allergies" -> value == [] (empty list, NOT null), unverified,
    #    with a source quote.
    u1 = _utt("u1", "Patient has no known allergies.", minute=0)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "allergies",
                "value": "none",
                "quote": "no known allergies",
                "confidence": 0.9,
                "hedged": True,
            }
        ),
    )
    rec = ex.process_utterance(u1, rec)

    assert rec.allergies.value == []  # empty list, not None
    assert rec.allergies.value is not None
    assert rec.allergies.status == FieldStatus.unverified
    assert len(rec.allergies.sources) == 1
    assert rec.allergies.sources[0].quote == "no known allergies"
    assert rec.allergies.sources[0].utterance_id == "u1"
    first_source = rec.allergies.sources[0]

    # 2. "penicillin allergy bracelet" -> adds "penicillin" with its own source,
    #    keeps the first source.
    u2 = _utt("u2", "Found a penicillin allergy bracelet on the wrist.", minute=4)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "allergies",
                "value": "penicillin",
                "quote": "penicillin allergy bracelet",
                "confidence": 0.95,
                "hedged": False,
            }
        ),
    )
    rec = ex.process_utterance(u2, rec)

    assert rec.allergies.value == ["penicillin"]
    quotes = {s.quote for s in rec.allergies.sources}
    assert "no known allergies" in quotes  # first source kept
    assert "penicillin allergy bracelet" in quotes
    assert first_source in rec.allergies.sources
    assert {s.utterance_id for s in rec.allergies.sources} == {"u1", "u2"}

    # 3. Aspirin given twice -> two meds_given entries with DIFFERENT source
    #    quotes.
    u3 = _utt("u3", "Aspirin 300mg PO given on scene.", minute=6)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "meds_given",
                "value": {"drug": "aspirin", "dose": "300mg", "route": "PO"},
                "quote": "Aspirin 300mg PO given",
                "confidence": 0.95,
                "hedged": False,
            }
        ),
    )
    rec = ex.process_utterance(u3, rec)

    u4 = _utt("u4", "Gave a second aspirin 300mg in the truck.", minute=16)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "meds_given",
                "value": {"drug": "aspirin", "dose": "300mg", "route": "PO"},
                "quote": "second aspirin 300mg",
                "confidence": 0.9,
                "hedged": False,
            }
        ),
    )
    rec = ex.process_utterance(u4, rec)

    aspirin = [m for m in rec.meds_given if m.value.drug == "aspirin"]
    assert len(aspirin) == 2
    med_quotes = [m.sources[0].quote for m in aspirin]
    assert med_quotes[0] != med_quotes[1]
    assert med_quotes == ["Aspirin 300mg PO given", "second aspirin 300mg"]
