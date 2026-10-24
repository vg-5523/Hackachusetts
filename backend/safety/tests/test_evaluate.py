"""Unit tests for the safety ``evaluate`` engine (offline, template phrasing).

These tests never touch the network: drug normalization reads the committed
cache under ``backend/safety/cache/`` (pre-warmed for the demo drugs), and
``LLM_API_KEY`` is cleared so ``say_to_crew`` uses the deterministic template.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.safety import evaluate
from shared.schema import (
    FieldStatus,
    FlagType,
    Medication,
    PatientRecord,
    SourceRef,
    Sourced,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


def _ts(minute: int) -> datetime:
    return datetime(2024, 1, 15, 9, minute, 0, tzinfo=timezone.utc)


def _hero_record() -> PatientRecord:
    """Allergies first 'none' then 'penicillin' (conflicted); aspirin twice."""
    record = PatientRecord()
    record.allergies = Sourced[list[str]](
        value=["penicillin"],
        status=FieldStatus.conflicted,
        confidence=0.7,
        sources=[
            SourceRef(
                utterance_id="utt-0005",
                quote="He says he has no allergies.",
                ts=_ts(15),
            ),
            SourceRef(
                utterance_id="utt-0009",
                quote="Found a penicillin allergy bracelet on his wrist.",
                ts=_ts(19),
            ),
        ],
    )
    record.meds_given = [
        Sourced[Medication](
            value=Medication(
                drug="aspirin",
                dose="324 mg",
                route="chewed oral",
                time="2024-01-15T09:16:20+00:00",
            ),
            status=FieldStatus.confirmed,
            confidence=0.9,
            sources=[
                SourceRef(
                    utterance_id="utt-0006",
                    quote="Aspirin 324 milligrams chewed, given.",
                    ts=_ts(16),
                )
            ],
        ),
        Sourced[Medication](
            value=Medication(
                drug="aspirin",
                dose="324 mg",
                route="chewed oral",
                time="2024-01-15T09:20:15+00:00",
            ),
            status=FieldStatus.confirmed,
            confidence=0.85,
            sources=[
                SourceRef(
                    utterance_id="utt-0010",
                    quote="Give him another aspirin, 324 chewable.",
                    ts=_ts(20),
                )
            ],
        ),
    ]
    return record


@pytest.fixture(autouse=True)
def _no_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)


def test_hero_case_yields_duplicate_and_contradiction() -> None:
    flags = evaluate(_hero_record(), cache_dir=CACHE_DIR)
    types = {f.type for f in flags}

    assert FlagType.duplicate_dose in types
    # The hero case must surface the allergy problem as a conflict and/or a
    # cross-reactive allergy conflict.
    assert (
        FlagType.allergy_conflict in types or FlagType.contradiction in types
    )


def test_idempotent_ids() -> None:
    record = _hero_record()
    first = [f.id for f in evaluate(record, cache_dir=CACHE_DIR)]
    second = [f.id for f in evaluate(record, cache_dir=CACHE_DIR)]
    assert first == second
    assert first == sorted(first) or len(first) == len(set(first))


def test_say_to_crew_uses_template_without_key() -> None:
    flags = evaluate(_hero_record(), cache_dir=CACHE_DIR)
    assert flags, "expected at least one flag"
    for flag in flags:
        assert flag.say_to_crew.strip()
        assert len(flag.say_to_crew) <= 280


def test_flags_are_schema_valid_and_cited() -> None:
    flags = evaluate(_hero_record(), cache_dir=CACHE_DIR)
    for flag in flags:
        assert flag.source_ref.name
        assert str(flag.source_ref.url).startswith("http")
        assert flag.id.startswith(flag.type.value + ":")


def test_missing_allergies_when_unknown() -> None:
    record = PatientRecord()  # allergies status defaults to unknown
    flags = evaluate(record, cache_dir=CACHE_DIR)
    assert any(f.type is FlagType.missing_info for f in flags)
