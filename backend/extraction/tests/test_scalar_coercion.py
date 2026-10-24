"""Tests for string-scalar type coercion in backend.extraction.apply.

PatientRecord scalar fields age/sex/chief_complaint/suspected_condition/eta are
``Sourced[str]`` in shared/schema.py, so a non-string proposal value (e.g. the
int 58 for age) must be coerced to str at apply time -- otherwise pydantic emits
a serializer warning on model_dump_json. acuity_esi stays an int (1..5).
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone

import pytest

from backend.extraction.apply import apply_proposals
from backend.extraction.parse import Proposal
from shared.schema import PatientRecord, Utterance


def _utt(text: str) -> Utterance:
    return Utterance(id="u1", text=text, ts=datetime(2024, 1, 1, tzinfo=timezone.utc))


def _prop(path: str, value, quote: str) -> Proposal:
    return Proposal(path=path, value=value, quote=quote, confidence=0.9, hedged=False)


def test_age_int_coerced_to_str_and_no_serializer_warning():
    """An age proposed as the int 58 is stored as "58" and model_dump_json emits
    no pydantic serializer warning."""
    utt = _utt("He is 58 years old.")
    rec = apply_proposals(PatientRecord(), [_prop("age", 58, "58 years old")], utt)

    assert rec.age.value == "58"
    assert isinstance(rec.age.value, str)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rec.model_dump_json()
    assert caught == [], f"unexpected warnings: {[str(w.message) for w in caught]}"


def test_all_string_scalars_coerce_non_string_values():
    """Every Sourced[str] scalar coerces a non-string value to str."""
    utt = _utt("58 male chest pain STEMI 12 minutes")
    props = [
        _prop("age", 58, "58"),
        _prop("sex", 0, "male"),  # contrived non-string
        _prop("chief_complaint", 12.0, "chest pain"),  # integral float -> "12"
        _prop("suspected_condition", 7, "STEMI"),
        _prop("eta", 12, "12 minutes"),
    ]
    rec = apply_proposals(PatientRecord(), props, utt)

    for name in ("age", "sex", "chief_complaint", "suspected_condition", "eta"):
        assert isinstance(getattr(rec, name).value, str), name
    assert rec.chief_complaint.value == "12"  # 12.0 rendered without ".0"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rec.model_dump_json()
    assert caught == []


def test_acuity_esi_stays_int():
    """acuity_esi is Sourced[int 1..5] and must NOT be coerced to a string."""
    utt = _utt("This is a level 2 patient.")
    rec = apply_proposals(PatientRecord(), [_prop("acuity_esi", 2, "level 2")], utt)

    assert rec.acuity_esi.value == 2
    assert isinstance(rec.acuity_esi.value, int)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rec.model_dump_json()
    assert caught == []


def test_string_scalar_value_passes_through_unchanged():
    """A value already a string is stored unchanged."""
    utt = _utt("fifty-eight years old")
    rec = apply_proposals(
        PatientRecord(), [_prop("age", "fifty-eight", "fifty-eight years old")], utt
    )
    assert rec.age.value == "fifty-eight"


@pytest.mark.parametrize("bad", [True, False, None])
def test_non_meaningful_scalar_values_are_skipped(bad):
    """bool/None are not meaningful string scalars and are skipped, leaving the
    field unknown rather than storing a misleading "True"/"None"."""
    utt = _utt("some text")
    rec = apply_proposals(PatientRecord(), [_prop("age", bad, "some text")], utt)
    assert rec.age.value is None
