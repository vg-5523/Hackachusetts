"""The one pure fold over the Event_Log: ``derive`` and ``apply_event``.

The append-only Event_Log is the single source of truth (Req 1.1). This module
provides the single fold that turns it into derived state (Req 1.2):

- ``apply_event(state, event) -> (PatientRecord, list[Flag])`` applies one
  :class:`Event` to an ``(record, flags)`` state and returns a NEW tuple. It
  never mutates either input: the record and every flag are deep-copied (via
  ``model_copy(deep=True)``) before anything changes, so replay and live
  derivation are identical (Req 1.3).
- ``derive(events)`` folds ``apply_event`` over the whole log starting from the
  empty ``(PatientRecord(), [])``.

Event handling (payload shapes per ``shared/api.md`` "Event kinds"):

- ``utterance`` — provenance only; no change to record or flags.
- ``fact`` ``{path, value, source, confidence}`` — apply to the ``Sourced``
  field addressed by ``path`` using the conflict rules below, or append a new
  entry for the ``meds_given`` / ``vitals_timeline`` list targets.
- ``flag_raised`` ``{flag}`` — add the flag if its id is new; if the id is
  already present, update its content but PRESERVE the existing status
  (flag-status stability, Req 2.5).
- ``flag_relayed`` ``{flag_id}`` — move ``open`` -> ``relayed`` for that id.
- ``flag_acked`` ``{flag_id}`` — move ``relayed`` -> ``acknowledged`` for that
  id.
- ``field_confirmed`` ``{path}`` — set the addressed ``Sourced`` field's status
  to ``confirmed``.

Conflict rules for a scalar / ``allergies`` ``Sourced`` target (Req 2.1-2.3):

- No sources yet: set value, status ``unverified``, append the source, set
  confidence.
- Same value as current: keep value and status, append the source but dedupe on
  ``(utterance_id, quote)``.
- Different value: KEEP the old value, append the new source, set status
  ``conflicted``. The value is never overwritten.

Free-text fields (``chief_complaint`` and ``notes``) are an exception to the
contradiction rule: a differing observation is NOT marked ``conflicted``.
Instead the longer, more specific value is kept as the value, both sources are
merged (deduped on ``(utterance_id, quote)``), and the status stays
``unverified``. The conflict rule above still applies to ``age``, ``sex``,
``suspected_condition``, ``acuity_esi`` and ``eta``; ``allergies`` keeps its
list-merge behaviour.

This module only reads model definitions from ``shared.schema`` and never edits
shared state. Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

from typing import Any

from shared.schema import (
    Event,
    FieldStatus,
    Flag,
    FlagStatus,
    Medication,
    PatientRecord,
    Sourced,
    SourceRef,
    VitalsEntry,
)

__all__ = ["apply_event", "derive"]


State = tuple[PatientRecord, list[Flag]]

# Top-level scalar ``Sourced`` fields reachable by a single-segment dotted path.
# ``allergies`` is conflict-merged like a scalar; the append-type list targets
# ``meds_given`` and ``vitals_timeline`` are handled separately.
_SCALAR_FIELDS: frozenset[str] = frozenset(
    {
        "age",
        "sex",
        "chief_complaint",
        "suspected_condition",
        "eta",
        "acuity_esi",
        "allergies",
    }
)

# Free-text Sourced fields whose differing observations are MERGED rather than
# marked ``conflicted``: the longer value is kept, both sources are merged, and
# the status stays ``unverified``. ``notes`` is included so that if a ``notes``
# Sourced path is ever added it is already covered; today only
# ``chief_complaint`` is a reachable free-text Sourced scalar.
_FREE_TEXT_FIELDS: frozenset[str] = frozenset({"chief_complaint", "notes"})


def _resolve_sourced(record: PatientRecord, path: str) -> Sourced | None:
    """Resolve a dotted ``path`` to a ``Sourced`` field on ``record``.

    Handles the scalar / ``allergies`` single-segment paths and the
    ``meds_given.N`` indexed entries (each a ``Sourced[Medication]``). Returns
    ``None`` when the path does not address a ``Sourced`` field (for example an
    out-of-range index, or ``vitals_timeline.N`` whose entries are plain
    ``VitalsEntry`` values rather than ``Sourced``).
    """
    segments = path.split(".")

    if len(segments) == 1:
        name = segments[0]
        if name in _SCALAR_FIELDS:
            return getattr(record, name)
        return None

    if len(segments) == 2 and segments[0] == "meds_given":
        index = _parse_index(segments[1])
        if index is None:
            return None
        if 0 <= index < len(record.meds_given):
            return record.meds_given[index]
        return None

    return None


def _parse_index(segment: str) -> int | None:
    """Parse a zero-based, non-negative integer list-index segment."""
    if not segment.isdigit():
        return None
    return int(segment)


def _source_from_payload(payload: dict) -> SourceRef:
    """Validate/convert the fact payload's ``source`` into a ``SourceRef``."""
    return SourceRef.model_validate(payload["source"])


def _already_cited(sources: list[SourceRef], candidate: SourceRef) -> bool:
    """Whether ``candidate`` duplicates an existing source on (id, quote)."""
    return any(
        existing.utterance_id == candidate.utterance_id
        and existing.quote == candidate.quote
        for existing in sources
    )


def _apply_scalar_fact(
    field: Sourced,
    value: Any,
    source: SourceRef,
    confidence: float,
    field_name: str,
) -> None:
    """Mutate an already-copied ``Sourced`` ``field`` per the conflict rules.

    ``field`` is a fresh deep copy owned by the new record, so mutating it in
    place does not touch the caller's input state.

    Free-text fields (``field_name`` in :data:`_FREE_TEXT_FIELDS`) never
    conflict: on a differing observation the longer value is kept, the source is
    merged, and the status stays ``unverified``. Every other scalar field keeps
    the contradiction rule (different value -> keep old value, mark
    ``conflicted``).
    """
    if not field.sources:
        # Empty provenance: first observation wins, marked unverified.
        field.value = value
        field.status = FieldStatus.unverified
        field.confidence = confidence
        field.sources.append(source)
        return

    if field.value == value:
        # Same value re-observed: add corroborating source, dedupe on id+quote.
        if not _already_cited(field.sources, source):
            field.sources.append(source)
        return

    # Different value.
    if field_name in _FREE_TEXT_FIELDS:
        # Free-text: do not contradict. Keep the longer, more specific value,
        # merge the source, and leave the field unverified (never conflicted).
        current_len = len(field.value) if isinstance(field.value, str) else 0
        incoming_len = len(value) if isinstance(value, str) else 0
        if incoming_len > current_len:
            field.value = value
        if not _already_cited(field.sources, source):
            field.sources.append(source)
        field.status = FieldStatus.unverified
        return

    # Every other scalar field: never overwrite. Keep the old value, record the
    # conflicting source, mark the field conflicted.
    if not _already_cited(field.sources, source):
        field.sources.append(source)
    field.status = FieldStatus.conflicted


def _apply_allergies_fact(
    field: Sourced,
    value: Any,
    source: SourceRef,
    confidence: float,
) -> None:
    """Merge an ``allergies`` fact into an already-copied ``Sourced[list[str]]``.

    ``allergies`` is list-valued, so unlike a scalar we never "keep the old
    value" wholesale. Instead we union the member strings (order-preserving,
    de-duplicated) so a named allergy observed after a "no known allergies"
    claim is surfaced in ``value`` rather than hidden behind the earlier empty
    list.

    Status follows the record's contradiction contract:

    - First observation (no sources yet): set the value, mark ``unverified``.
    - A later observation that CONTRADICTS an earlier one -- i.e. one claims no
      allergies (empty list) while the other names at least one -- marks the
      field ``conflicted`` (the value still becomes the union so the real
      allergy is visible). Matching the stored "no allergies" claim with another
      "no allergies" (both empty) is corroboration, not conflict.
    - Otherwise (e.g. an additional allergy with no empty-vs-nonempty clash) the
      status is left as-is.

    The new source is always appended (de-duplicated on id+quote) so provenance
    for every observation is preserved.
    """
    incoming = list(value) if isinstance(value, (list, tuple)) else ([] if value is None else [value])

    if not field.sources:
        field.value = incoming
        field.status = FieldStatus.unverified
        field.confidence = confidence
        field.sources.append(source)
        return

    current = list(field.value) if isinstance(field.value, list) else []

    # Detect an empty-vs-non-empty contradiction across observations: a prior
    # "no allergies" (current empty) now contradicted by a named allergy, or the
    # reverse (a named allergy now contradicted by a "no allergies" claim).
    contradicts = (len(current) == 0) != (len(incoming) == 0)

    # Union the members, preserving order and removing duplicates.
    merged = list(current)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    field.value = merged

    if not _already_cited(field.sources, source):
        field.sources.append(source)

    if contradicts:
        field.status = FieldStatus.conflicted


def _apply_fact(record: PatientRecord, payload: dict) -> None:
    """Apply a ``fact`` event to an already-copied ``record`` in place."""
    path = payload["path"]
    value = payload["value"]
    confidence = float(payload["confidence"])
    source = _source_from_payload(payload)

    # Append-type list targets: a new entry, not a conflict merge (Req 2.4).
    if path == "meds_given":
        medication = Medication.model_validate(value)
        record.meds_given.append(
            Sourced[Medication](
                value=medication,
                status=FieldStatus.unverified,
                confidence=confidence,
                sources=[source],
            )
        )
        return

    if path == "vitals_timeline":
        record.vitals_timeline.append(VitalsEntry.model_validate(value))
        return

    target = _resolve_sourced(record, path)
    if target is None:
        # Path does not address a mergeable Sourced field; leave state intact.
        return
    if path == "allergies":
        # ``allergies`` is a LIST-valued Sourced: merge list members rather than
        # treat the whole list as an opaque scalar, so a real allergy is never
        # hidden behind an earlier "no known allergies" (==> value []).
        _apply_allergies_fact(target, value, source, confidence)
        return
    _apply_scalar_fact(target, value, source, confidence, path)


def _apply_flag_raised(flags: list[Flag], payload: dict) -> None:
    """Apply a ``flag_raised`` event to an already-copied ``flags`` list.

    A new id is appended. A re-raised id has its content refreshed from the
    incoming flag but KEEPS its existing status (Req 2.5).
    """
    incoming = Flag.model_validate(payload["flag"])
    for index, existing in enumerate(flags):
        if existing.id == incoming.id:
            refreshed = incoming.model_copy(update={"status": existing.status})
            flags[index] = refreshed
            return
    flags.append(incoming)


def _set_flag_status(
    flags: list[Flag],
    flag_id: str,
    expected: FlagStatus,
    new_status: FlagStatus,
) -> None:
    """Advance a flag's status when it is found and in the expected state."""
    for flag in flags:
        if flag.id == flag_id:
            if flag.status == expected:
                flag.status = new_status
            return


def _apply_field_confirmed(record: PatientRecord, payload: dict) -> None:
    """Set the addressed ``Sourced`` field's status to ``confirmed``."""
    target = _resolve_sourced(record, payload["path"])
    if target is not None:
        target.status = FieldStatus.confirmed


def apply_event(state: State, event: Event) -> State:
    """Apply one :class:`Event` to ``state``, returning a NEW ``(record, flags)``.

    The inputs are never mutated: the record is deep-copied and each flag is
    deep-copied before any change, so the returned tuple is fully independent of
    the argument.
    """
    record, flags = state
    new_record = record.model_copy(deep=True)
    new_flags = [flag.model_copy(deep=True) for flag in flags]

    kind = event.kind
    payload = event.payload

    if kind == "utterance":
        # Provenance only; no change to derived state.
        pass
    elif kind == "fact":
        _apply_fact(new_record, payload)
    elif kind == "flag_raised":
        _apply_flag_raised(new_flags, payload)
    elif kind == "flag_relayed":
        _set_flag_status(
            new_flags, payload["flag_id"], FlagStatus.open, FlagStatus.relayed
        )
    elif kind == "flag_acked":
        _set_flag_status(
            new_flags,
            payload["flag_id"],
            FlagStatus.relayed,
            FlagStatus.acknowledged,
        )
    elif kind == "field_confirmed":
        _apply_field_confirmed(new_record, payload)
    # Unknown kinds are a no-op here; ``validate.py`` gates kinds on append.

    return new_record, new_flags


def derive(events: list[Event]) -> State:
    """Fold ``apply_event`` over ``events`` from the empty initial state."""
    state: State = (PatientRecord(), [])
    for event in events:
        state = apply_event(state, event)
    return state
