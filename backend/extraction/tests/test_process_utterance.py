"""Example tests for the extraction pipeline.

Tests that drive the LLM branch patch ``backend.llm.call_llm`` AND set
``LLM_API_KEY`` so the orchestrator takes the LLM path (not the rules fallback).
The cache is pointed at a temp dir so the committed cache is untouched.
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
def isolated_cache(tmp_path, monkeypatch):
    """Temp cache + a set key so the LLM branch runs when call_llm is patched."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    return tmp_path


def _patch_llm(monkeypatch, response: str) -> None:
    monkeypatch.setattr("backend.llm.call_llm", lambda prompt: response)


def test_no_allergies_then_penicillin(isolated_cache, monkeypatch):
    """"no known allergies" records value == [] with a source; a later
    penicillin fact adds the allergy and keeps the first source, so the store
    can mark ``allergies`` conflicted."""
    rec = PatientRecord()

    u1 = _utt("u1", "Patient reports no known allergies.", minute=0)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "allergies",
                "value": "none",
                "quote": "no known allergies",
                "confidence": 0.9,
                "hedged": False,
            }
        ),
    )
    rec = ex.process_utterance(u1, rec)
    assert rec.allergies.value == []  # empty list, not null

    u2 = _utt("u2", "Found a penicillin allergy bracelet on the patient.", minute=3)
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
    # One SourceRef per utterance remains, so the store sees two origins.
    ids = {s.utterance_id for s in rec.allergies.sources}
    assert ids == {"u1", "u2"}
    # Extraction itself never sets conflicted; that is the store's job.
    assert rec.allergies.status != FieldStatus.conflicted


def test_aspirin_given_twice(isolated_cache, monkeypatch):
    """Aspirin administered twice yields two ``meds_given`` entries, each with
    its own SourceRef."""
    rec = PatientRecord()

    u1 = _utt("u1", "Aspirin 300mg PO given.", minute=0)
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
    rec = ex.process_utterance(u1, rec)

    u2 = _utt("u2", "Gave another aspirin 300mg by mouth just now.", minute=10)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "meds_given",
                "value": {"drug": "aspirin", "dose": "300mg", "route": "PO"},
                "quote": "another aspirin 300mg",
                "confidence": 0.9,
                "hedged": False,
            }
        ),
    )
    rec = ex.process_utterance(u2, rec)

    assert len(rec.meds_given) == 2
    assert all(m.value.drug == "aspirin" for m in rec.meds_given)
    assert all(len(m.sources) == 1 for m in rec.meds_given)
    assert [m.sources[0].utterance_id for m in rec.meds_given] == ["u1", "u2"]


def test_no_key_no_cache_falls_back_to_rules(tmp_path, monkeypatch):
    """With no key and an empty cache, process_utterance does NOT raise: it
    falls back to the deterministic rules extractor."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # Stop a real repo-root .env from supplying a key via load_dotenv, so the
    # no-key branch is exercised deterministically.
    monkeypatch.setattr("backend.extraction.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("backend.llm.load_dotenv", lambda *a, **k: None)

    # Guard: call_llm must never be reached on this path.
    def _boom(prompt):  # pragma: no cover - should not be called
        raise AssertionError("call_llm must not be called without a key")

    monkeypatch.setattr("backend.llm.call_llm", _boom)

    rec = PatientRecord()
    u1 = _utt("u1", "54 year old male with chest pain, aspirin 300mg given.", minute=0)
    out = ex.process_utterance(u1, rec)  # must not raise

    # Rules recovered some facts, all marked unverified.
    assert out.chief_complaint.value == "chest pain"
    assert out.chief_complaint.status == FieldStatus.unverified
    assert any(m.value.drug == "aspirin" for m in out.meds_given)
    assert rec.chief_complaint.value is None  # input untouched


def test_quote_not_substring_dropped(isolated_cache, monkeypatch):
    """A fact whose quote is not in the utterance text is dropped."""
    rec = PatientRecord()
    u1 = _utt("u1", "Patient is 54 years old.", minute=0)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "age",
                "value": "54",
                "quote": "54 years old",
                "confidence": 0.9,
                "hedged": False,
            },
            {
                "path": "sex",
                "value": "female",
                "quote": "female patient",  # not present in the utterance
                "confidence": 0.9,
                "hedged": False,
            },
        ),
    )
    out = ex.process_utterance(u1, rec)

    assert out.age.value == "54"
    assert out.sex.value is None
    assert out.sex.status == FieldStatus.unknown


def test_input_record_not_mutated(isolated_cache, monkeypatch):
    """The input record is byte-for-byte identical after extraction."""
    rec = PatientRecord()
    before = rec.model_dump_json()

    u1 = _utt("u1", "Suspected STEMI, ESI 2.", minute=0)
    _patch_llm(
        monkeypatch,
        _facts(
            {
                "path": "suspected_condition",
                "value": "STEMI",
                "quote": "Suspected STEMI",
                "confidence": 0.9,
                "hedged": False,
            },
            {
                "path": "acuity_esi",
                "value": 2,
                "quote": "ESI 2",
                "confidence": 0.9,
                "hedged": False,
            },
        ),
    )
    out = ex.process_utterance(u1, rec)

    assert rec.model_dump_json() == before
    assert out is not rec
    assert out.suspected_condition.value == "STEMI"
    assert out.acuity_esi.value == 2
