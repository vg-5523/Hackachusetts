# Feature: store-outputs, Property 1: Schema JSON round-trip
"""Property 1 — Schema JSON round-trip for the shared Pydantic contract.

**Validates: Requirements 8.1**

For any valid instance ``m`` of a shared model,
``type(m).model_validate_json(m.model_dump_json()) == m`` and
``type(m).model_validate(json.loads(m.model_dump_json())) == m``.

The strategies below generate only *valid* instances that respect the field
constraints declared in ``shared/schema.py`` (length bounds, numeric ranges,
the ``bp`` pattern, aware timestamps, ESI 1..5, etc.) so that construction
never trips a validator and the test exercises serialization, not rejection.

Two canonicalization choices keep round-trip equality exact rather than merely
structural:

* **Timestamps.** Generic ``AwareDatetime`` fields round-trip at full
  microsecond precision, so they are generated freely. ``Event.ts`` however is
  serialized with a custom ``field_serializer`` at *millisecond* precision, so
  microseconds below a millisecond would be truncated on the way out and the
  reloaded value would differ. Event timestamps are therefore generated at
  exact millisecond precision (microsecond forced to a multiple of 1000).
* **URLs.** ``Citation.url`` is an ``AnyHttpUrl``; Pydantic normalizes it the
  same way on both the original construction and the reload, so a simple
  ``https://<host>/<path>`` composed value round-trips unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from shared.schema import (
    Citation,
    Event,
    FieldStatus,
    Flag,
    FlagSeverity,
    FlagStatus,
    FlagType,
    Medication,
    PatientRecord,
    SourceRef,
    Sourced,
    VitalsEntry,
)

MAX_EXAMPLES = 100


# --------------------------------------------------------------------------- #
# Primitive / shared strategies
# --------------------------------------------------------------------------- #

# A small spread of timezones so non-UTC offsets are exercised too. Pydantic
# preserves the concrete offset across a round-trip, so any fixed-offset tz is
# safe here.
_TIMEZONES = st.sampled_from(
    [
        timezone.utc,
        timezone(timedelta(hours=5, minutes=30)),
        timezone(timedelta(hours=-8)),
        timezone(timedelta(hours=1)),
    ]
)

# Aware datetimes at full microsecond precision; fine for every field that is a
# plain ``AwareDatetime`` (SourceRef.ts, VitalsEntry.ts).
aware_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=_TIMEZONES,
)


@st.composite
def ms_datetimes(draw: st.DrawFn) -> datetime:
    """An aware datetime truncated to millisecond precision.

    ``Event.ts`` serializes with ``timespec="milliseconds"``; generating at ms
    precision keeps round-trip equality exact.
    """
    dt = draw(aware_datetimes)
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


def http_urls() -> st.SearchStrategy[str]:
    """Simple, canonical http/https URLs built from safe tokens."""
    scheme = st.sampled_from(["http", "https"])
    host = st.sampled_from(["example.com", "ed.example.org", "hospital.test"])
    path = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=0,
        max_size=20,
    )
    return st.builds(
        lambda s, h, p: f"{s}://{h}/{p}",
        scheme,
        host,
        path,
    )


def field_statuses() -> st.SearchStrategy[FieldStatus]:
    return st.sampled_from(list(FieldStatus))


confidences = st.floats(
    min_value=0, max_value=1, allow_nan=False, allow_infinity=False
)


@st.composite
def source_refs(draw: st.DrawFn) -> SourceRef:
    return SourceRef(
        utterance_id=draw(st.text(min_size=1, max_size=128)),
        quote=draw(st.text(min_size=1, max_size=1000)),
        ts=draw(aware_datetimes),
    )


@st.composite
def citations(draw: st.DrawFn) -> Citation:
    return Citation(
        name=draw(st.text(min_size=1, max_size=200)),
        url=draw(http_urls()),
    )


def sourced(
    value_strategy: st.SearchStrategy[object],
) -> st.SearchStrategy[Sourced]:
    """A ``Sourced`` whose ``value`` is ``None`` or a draw of ``value_strategy``."""

    @st.composite
    def _build(draw: st.DrawFn) -> Sourced:
        return Sourced(
            value=draw(st.none() | value_strategy),
            status=draw(field_statuses()),
            confidence=draw(confidences),
            sources=draw(st.lists(source_refs(), max_size=20)),
        )

    return _build()


@st.composite
def medications(draw: st.DrawFn) -> Medication:
    opt_str = st.none() | st.text(min_size=0, max_size=200)
    return Medication(
        drug=draw(opt_str),
        dose=draw(opt_str),
        route=draw(opt_str),
        time=draw(opt_str),
        given_by=draw(opt_str),
    )


def bp_strings() -> st.SearchStrategy[str]:
    """Blood-pressure strings matching ``^\\d{2,3}/\\d{2,3}$``."""
    side = st.integers(min_value=10, max_value=999)
    return st.builds(lambda a, b: f"{a}/{b}", side, side)


@st.composite
def vitals_entries(draw: st.DrawFn) -> VitalsEntry:
    return VitalsEntry(
        ts=draw(aware_datetimes),
        hr=draw(st.none() | st.integers(min_value=0, max_value=300)),
        bp=draw(st.none() | bp_strings()),
        spo2=draw(st.none() | st.integers(min_value=0, max_value=100)),
        rr=draw(st.none() | st.integers(min_value=0, max_value=100)),
        source=draw(st.text(min_size=0, max_size=200)),
    )


@st.composite
def patient_records(draw: st.DrawFn) -> PatientRecord:
    str_values = st.text(min_size=0, max_size=200)
    return PatientRecord(
        age=draw(sourced(str_values)),
        sex=draw(sourced(str_values)),
        chief_complaint=draw(sourced(str_values)),
        suspected_condition=draw(sourced(str_values)),
        eta=draw(sourced(str_values)),
        acuity_esi=draw(sourced(st.integers(min_value=1, max_value=5))),
        allergies=draw(
            sourced(st.lists(st.text(min_size=0, max_size=50), max_size=10))
        ),
        meds_given=draw(st.lists(sourced(medications()), max_size=4)),
        vitals_timeline=draw(st.lists(vitals_entries(), max_size=4)),
        notes=draw(st.text(min_size=0, max_size=5000)),
    )


@st.composite
def flags(draw: st.DrawFn) -> Flag:
    # ``say_to_crew`` must contain at least one non-whitespace character; prefix
    # a printable char so ``value.strip()`` is never empty.
    say_tail = draw(st.text(min_size=0, max_size=279))
    say_to_crew = "x" + say_tail
    return Flag(
        id=draw(st.text(min_size=1, max_size=64)),
        type=draw(st.sampled_from(list(FlagType))),
        severity=draw(st.sampled_from(list(FlagSeverity))),
        message=draw(st.text(min_size=1, max_size=500)),
        say_to_crew=say_to_crew,
        evidence=draw(
            st.lists(st.text(min_size=1, max_size=500), max_size=10)
        ),
        source_ref=draw(citations()),
        status=draw(st.sampled_from(list(FlagStatus))),
    )


def payloads() -> st.SearchStrategy[dict]:
    """A tiny JSON-serializable dict, far below the 64 KB payload limit."""
    return st.dictionaries(
        st.text(max_size=10),
        st.integers() | st.text(max_size=20),
        max_size=5,
    )


@st.composite
def events(draw: st.DrawFn) -> Event:
    return Event(
        id=draw(st.text(min_size=1, max_size=128)),
        ts=draw(ms_datetimes()),
        kind=draw(st.text(min_size=1, max_size=64)),
        payload=draw(payloads()),
    )


# --------------------------------------------------------------------------- #
# The round-trip property, applied once per model
# --------------------------------------------------------------------------- #


def _assert_roundtrip(model) -> None:
    """``model`` survives a JSON dump + reload, both parse paths, unchanged."""
    dumped = model.model_dump_json()
    cls = type(model)
    assert cls.model_validate_json(dumped) == model
    assert cls.model_validate(json.loads(dumped)) == model


@settings(max_examples=MAX_EXAMPLES)
@given(source_refs())
def test_source_ref_roundtrip(m: SourceRef) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(citations())
def test_citation_roundtrip(m: Citation) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(sourced(st.text(min_size=0, max_size=200)))
def test_sourced_str_roundtrip(m: Sourced) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(sourced(st.lists(st.text(min_size=0, max_size=50), max_size=10)))
def test_sourced_list_roundtrip(m: Sourced) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(medications())
def test_medication_roundtrip(m: Medication) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(vitals_entries())
def test_vitals_entry_roundtrip(m: VitalsEntry) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(patient_records())
def test_patient_record_roundtrip(m: PatientRecord) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(flags())
def test_flag_roundtrip(m: Flag) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)


@settings(max_examples=MAX_EXAMPLES)
@given(events())
def test_event_roundtrip(m: Event) -> None:
    # Feature: store-outputs, Property 1: Schema JSON round-trip
    _assert_roundtrip(m)
