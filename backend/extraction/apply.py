"""Apply verified proposals onto a deep copy of the patient record.

``apply_proposals`` never mutates the input ``record``: it works on
``record.model_copy(deep=True)``. Each applied fact gets a ``SourceRef`` built
from the utterance. Hedged facts become ``unverified`` and keep a confidence no
greater than an unhedged fact; otherwise a verified fact is ``confirmed``.
``acuity_esi`` outside 1..5 is skipped. When a scalar already holds a different
value, the new value is assigned but the prior ``SourceRef`` is left in place so
the store can detect the conflict. This module never sets ``conflicted``.
Source lists are capped at 20.

``allergies`` has a sentinel: a proposal value of ``"none"`` / ``"no known
allergies"`` / ``""`` records "patient has no known allergies" as ``value == []``
(empty list, not null) WITH a source, so the empty-list-with-source state is
itself a recorded fact.
"""

from __future__ import annotations

from typing import Any

from shared.schema import (
    FieldStatus,
    Medication,
    PatientRecord,
    Sourced,
    SourceRef,
    Utterance,
    VitalsEntry,
)

from .parse import Proposal

MAX_SOURCES = 20
_SCALAR_PATHS = ("age", "sex", "chief_complaint", "suspected_condition", "eta")
# Allergy values that mean "no known allergies" -> empty list with a source.
_NO_ALLERGY_SENTINELS = {"", "none", "no known allergies", "nka", "no allergies"}


def _status_for(hedged: bool) -> FieldStatus:
    return FieldStatus.unverified if hedged else FieldStatus.confirmed


def _append_source(sourced: Sourced, ref: SourceRef) -> None:
    """Append ``ref`` to ``sourced.sources`` unless it would exceed the cap."""
    if len(sourced.sources) >= MAX_SOURCES:
        return
    for existing in sourced.sources:
        if existing.utterance_id == ref.utterance_id and existing.quote == ref.quote:
            return
    sourced.sources.append(ref)


def _confidence_for(hedged: bool, proposed: float) -> float:
    """Clamp confidence to 0..1; hedged facts are capped so they never exceed
    an equivalent unhedged fact."""
    value = max(0.0, min(1.0, float(proposed)))
    if hedged:
        value = min(value, 0.5)
    return value


def _apply_scalar(sourced: Sourced, value: Any, ref: SourceRef, proposal: Proposal) -> None:
    sourced.value = value
    sourced.status = _status_for(proposal.hedged)
    sourced.confidence = _confidence_for(proposal.hedged, proposal.confidence)
    _append_source(sourced, ref)


def _coerce_acuity(value: Any) -> int | None:
    """Return an int in 1..5, or ``None`` when the value is out of range."""
    if isinstance(value, bool):
        return None
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return None
    return ivalue if 1 <= ivalue <= 5 else None


def apply_proposals(
    record: PatientRecord, proposals: list[Proposal], utterance: Utterance
) -> PatientRecord:
    """Return a new record with ``proposals`` applied; input is untouched."""
    out = record.model_copy(deep=True)

    for proposal in proposals:
        ref = SourceRef(
            utterance_id=utterance.id, quote=proposal.quote, ts=utterance.ts
        )

        if proposal.path in _SCALAR_PATHS:
            _apply_scalar(getattr(out, proposal.path), proposal.value, ref, proposal)

        elif proposal.path == "acuity_esi":
            acuity = _coerce_acuity(proposal.value)
            if acuity is None:
                continue
            _apply_scalar(out.acuity_esi, acuity, ref, proposal)

        elif proposal.path == "allergies":
            _apply_allergy(out, proposal, ref)

        elif proposal.path == "meds_given":
            med = _build_medication(proposal.value)
            if med is None:
                continue
            out.meds_given.append(
                Sourced[Medication](
                    value=med,
                    status=_status_for(proposal.hedged),
                    confidence=_confidence_for(proposal.hedged, proposal.confidence),
                    sources=[ref],
                )
            )

        elif proposal.path == "vitals_timeline":
            entry = _build_vitals(proposal.value, utterance)
            if entry is None:
                continue
            out.vitals_timeline.append(entry)

    return out


def _apply_allergy(out: PatientRecord, proposal: Proposal, ref: SourceRef) -> None:
    """Apply one allergy proposal, handling the no-allergies sentinel.

    A sentinel value records "no known allergies" as ``value == []`` with a
    source; a real allergy string is appended (deduped). Either way the field
    gains a source for this utterance so the store can detect the fact.
    """
    value = proposal.value
    if not isinstance(value, str):
        return
    normalized = value.strip().lower()

    if normalized in _NO_ALLERGY_SENTINELS:
        # "no known allergies": keep whatever strings are already present (none
        # on an empty record) and ensure value is a list, not null.
        out.allergies.value = list(out.allergies.value or [])
    else:
        current = list(out.allergies.value or [])
        if value not in current:
            current.append(value)
        out.allergies.value = current

    out.allergies.status = _status_for(proposal.hedged)
    out.allergies.confidence = _confidence_for(proposal.hedged, proposal.confidence)
    _append_source(out.allergies, ref)


def _build_medication(value: Any) -> Medication | None:
    if isinstance(value, dict):
        fields = {k: value.get(k) for k in ("drug", "dose", "route", "time", "given_by")}
    elif isinstance(value, str) and value:
        fields = {"drug": value}
    else:
        return None
    try:
        return Medication(**{k: v for k, v in fields.items() if v is not None})
    except Exception:
        return None


def _build_vitals(value: Any, utterance: Utterance) -> VitalsEntry | None:
    if not isinstance(value, dict):
        return None
    data = dict(value)
    data.setdefault("ts", utterance.ts)
    try:
        return VitalsEntry(**data)
    except Exception:
        return None
