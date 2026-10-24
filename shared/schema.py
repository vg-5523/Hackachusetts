"""Shared Pydantic v2 contract for the Ambulance Scribe + Safety Check system.

This module is the single source of truth for the data shapes used across the
backend (extraction, safety, outputs, store) and mirrored by hand in
``shared/types.ts``. Every model forbids unknown fields (``extra="forbid"``) and
every timestamp that must carry a UTC offset uses ``AwareDatetime``.

Only the provenance primitives live here: the ``str, Enum`` enumerations,
``SourceRef``, ``Citation``, and the generic ``Sourced[T]`` wrapper. The record,
flag, event, and utterance models are appended to this file by later tasks.

Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Generic, TypeVar

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

__all__ = [
    "FieldStatus",
    "FlagType",
    "FlagSeverity",
    "FlagStatus",
    "SourceRef",
    "Citation",
    "Sourced",
    "Medication",
    "VitalsEntry",
    "PatientRecord",
    "Flag",
    "ErrorBody",
    "Utterance",
    "UtteranceRequest",
    "Event",
    "ClockEntry",
    "Clocks",
]


class FieldStatus(str, Enum):
    """Provenance status of a :class:`Sourced` field."""

    confirmed = "confirmed"
    unverified = "unverified"
    conflicted = "conflicted"
    unknown = "unknown"


class FlagType(str, Enum):
    """Category of a safety flag."""

    duplicate_dose = "duplicate_dose"
    allergy_conflict = "allergy_conflict"
    interaction = "interaction"
    contradiction = "contradiction"
    missing_info = "missing_info"


class FlagSeverity(str, Enum):
    """Severity of a safety flag."""

    critical = "critical"
    warn = "warn"
    info = "info"


class FlagStatus(str, Enum):
    """Lifecycle state of a safety flag."""

    open = "open"
    relayed = "relayed"
    acknowledged = "acknowledged"


class SourceRef(BaseModel):
    """A pointer to the utterance that supports a :class:`Sourced` value."""

    model_config = ConfigDict(extra="forbid")

    utterance_id: str = Field(min_length=1, max_length=128)
    quote: str = Field(min_length=1, max_length=1000)
    ts: AwareDatetime


class Citation(BaseModel):
    """A named, linkable source backing a safety flag."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl = Field(max_length=2048)


T = TypeVar("T")


class Sourced(BaseModel, Generic[T]):
    """A value wrapped with provenance: status, confidence, and source quotes."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    status: FieldStatus = FieldStatus.unknown
    # ``allow_inf_nan=False`` rejects NaN and +/-inf; ge/le pin it to [0, 1].
    confidence: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    sources: list[SourceRef] = Field(default_factory=list, max_length=20)


class Medication(BaseModel):
    """One administered drug, every field optional provenance-free text."""

    model_config = ConfigDict(extra="forbid")

    drug: str | None = Field(default=None, min_length=0, max_length=200)
    dose: str | None = Field(default=None, min_length=0, max_length=200)
    route: str | None = Field(default=None, min_length=0, max_length=200)
    time: str | None = Field(default=None, min_length=0, max_length=200)
    given_by: str | None = Field(default=None, min_length=0, max_length=200)


class VitalsEntry(BaseModel):
    """One vitals measurement at a point in time."""

    model_config = ConfigDict(extra="forbid")

    ts: AwareDatetime
    hr: int | None = Field(default=None, ge=0, le=300)
    # Systolic/diastolic, e.g. "120/80"; two or three digits on each side.
    bp: str | None = Field(default=None, pattern=r"^\d{2,3}/\d{2,3}$")
    spo2: int | None = Field(default=None, ge=0, le=100)
    rr: int | None = Field(default=None, ge=0, le=100)
    source: str = Field(default="", min_length=0, max_length=200)


# ESI acuity is an integer from 1 to 5 inclusive; wrapping it in ``Annotated``
# keeps the bound inside the ``Sourced[...].value`` field so a violation names
# ``acuity_esi`` as the offending field.
AcuityESI = Annotated[int, Field(ge=1, le=5)]


class PatientRecord(BaseModel):
    """The structured patient record. Every value carries provenance.

    Created with no arguments it is a valid empty record: each ``Sourced``
    scalar field defaults to ``value=None`` with ``status=unknown`` and an empty
    source list, ``allergies`` defaults to a ``Sourced`` whose value is an empty
    list, the ``meds_given`` and ``vitals_timeline`` lists are empty, and
    ``notes`` is an empty string.
    """

    model_config = ConfigDict(extra="forbid")

    age: Sourced[str] = Field(default_factory=Sourced[str])
    sex: Sourced[str] = Field(default_factory=Sourced[str])
    chief_complaint: Sourced[str] = Field(default_factory=Sourced[str])
    suspected_condition: Sourced[str] = Field(default_factory=Sourced[str])
    eta: Sourced[str] = Field(default_factory=Sourced[str])
    acuity_esi: Sourced[AcuityESI] = Field(default_factory=Sourced[AcuityESI])
    # Req 4.7: allergies defaults to an ``unknown`` Sourced whose value is ``[]``.
    allergies: Sourced[list[str]] = Field(
        default_factory=lambda: Sourced[list[str]](value=[])
    )
    meds_given: list[Sourced[Medication]] = Field(
        default_factory=list, max_length=100
    )
    vitals_timeline: list[VitalsEntry] = Field(
        default_factory=list, max_length=100
    )
    notes: str = Field(default="", min_length=0, max_length=5000)


class Flag(BaseModel):
    """A deterministic, cited safety alert. The LLM only phrases ``say_to_crew``.

    ``say_to_crew`` is the single human-readable line a human operator relays to
    the crew; it must carry at least one non-whitespace character so a blank or
    whitespace-only line can never be presented for relay (Req 11.1, 11.2).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    type: FlagType
    severity: FlagSeverity
    message: str = Field(min_length=1, max_length=500)
    say_to_crew: str = Field(min_length=1, max_length=280)
    evidence: list[str] = Field(max_length=10)
    source_ref: Citation
    status: FlagStatus = FlagStatus.open

    @field_validator("evidence")
    @classmethod
    def _evidence_quote_lengths(cls, value: list[str]) -> list[str]:
        """Each evidence quote is 1 to 500 characters (the list is 0 to 10)."""
        for quote in value:
            if not 1 <= len(quote) <= 500:
                raise ValueError(
                    "evidence quotes must each be 1 to 500 characters"
                )
        return value

    @field_validator("say_to_crew")
    @classmethod
    def _say_to_crew_non_blank(cls, value: str) -> str:
        """Reject a whitespace-only ``say_to_crew``; the error names the field."""
        if not value.strip():
            raise ValueError("say_to_crew must not be blank")
        return value


class ErrorBody(BaseModel):
    """The JSON body of every error response (see ``shared/api.md``)."""

    model_config = ConfigDict(extra="forbid")

    category: str
    field: str | None = None
    detail: str


class Utterance(BaseModel):
    """A unit of paramedic speech or typed text, logged as an Event payload."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    ts: AwareDatetime


class UtteranceRequest(BaseModel):
    """The ``POST /api/utterance`` request body (an :class:`Utterance` sans id)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    ts: AwareDatetime


class Event(BaseModel):
    """One entry in the append-only Event_Log, the single source of truth.

    ``ts`` is serialized with millisecond precision. ``payload`` is an arbitrary
    JSON object (an empty object is permitted) whose serialized size is capped
    at 64 KB; a payload that exceeds that limit is rejected naming ``payload``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    ts: AwareDatetime
    kind: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)

    @field_serializer("ts")
    def _serialize_ts_millis(self, value: datetime) -> str:
        """Serialize ``ts`` to ISO 8601 with exactly millisecond precision."""
        return value.isoformat(timespec="milliseconds")

    @field_validator("payload")
    @classmethod
    def _payload_size_limit(cls, value: dict) -> dict:
        """Reject a ``payload`` whose JSON serialization exceeds 64 KB.

        A ``field_validator`` keeps the raised error attached to ``payload`` so
        the validation error names the offending field.
        """
        try:
            serialized = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"payload is not JSON-serializable: {exc}") from exc
        if len(serialized.encode("utf-8")) > 64 * 1024:
            raise ValueError("payload exceeds the 64 KB serialized size limit")
        return value


class ClockEntry(BaseModel):
    """Elapsed-time timer for one administered medication in the clock bar."""

    model_config = ConfigDict(extra="forbid")

    med_id: str = Field(min_length=1)
    last_dose_ts: AwareDatetime
    elapsed_s: int = Field(ge=0)


class Clocks(BaseModel):
    """The running-timer snapshot broadcast on the SSE ``clocks`` channel."""

    model_config = ConfigDict(extra="forbid")

    contact_ts: AwareDatetime | None = None
    eta: AwareDatetime | None = None
    door_to_ecg_target_ts: AwareDatetime | None = None
    meds: list[ClockEntry] = Field(default_factory=list)
