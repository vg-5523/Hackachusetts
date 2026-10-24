"""Required example tests for the extraction pipeline (Req 7.1-7.4).

All tests patch ``backend.llm.call_llm`` so no network call is made, and point
the cache at a temporary directory so the committed demo cache is untouched.
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
    """Point the cache at a temp dir so tests never touch the committed cache."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    return tmp_path


def _patch_llm(monkeypatch, response: str) -> None:
    monkeypatch.setattr("backend.llm.call_llm", lambda prompt: response)


def test_no_allergies_then_penicillin(isolated_cache, monkeypatch):
    """Both allergy values survive with their own sources so the store can
    later mark ``allergies`` conflicted (Req 7.2, 3.2)."""
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

    assert rec.allergies.value == ["none", "penicillin"]
    # One SourceRef per utterance remains, so the store sees two origins.
    ids = {s.utterance_id for s in rec.allergies.sources}
    assert ids == {"u1", "u2"}
    # Extraction itself never sets conflicted; that is the store's job.
    assert rec.allergies.status != FieldStatus.conflicted


def test_aspirin_given_twice(isolated_cache, monkeypatch):
    """Aspirin administered twice yields two ``meds_given`` entries, each with
    its own SourceRef (Req 7.3)."""
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


def test_no_key_no_cache_raises(isolated_cache, monkeypatch):
    """With no key and an empty cache, a RuntimeError naming LLM_API_KEY
    propagates to the caller (Req 6.1, 6.2)."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    rec = PatientRecord()
    u1 = _utt("u1", "Chest pain radiating to the left arm.", minute=0)

    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        ex.process_utterance(u1, rec)

    # No partial write to the record.
    assert rec.chief_complaint.value is None


def test_quote_not_substring_dropped(isolated_cache, monkeypatch):
    """A fact whose quote is not in the utterance text is dropped (Req 2.3,
    2.4)."""
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
    """The input record is byte-for-byte identical after extraction (Req
    3.1)."""
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
