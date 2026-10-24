"""Turn a record diff into ``fact`` events: ``facts_from``.

The live pipeline runs ``extraction.process_utterance(utt, old) -> new`` and
then needs to persist the *delta* as append-only ``fact`` events so the
Event_Log stays the single source of truth (Req 1.2). This module computes that
delta: given the utterance and the ``old``/``new`` :class:`PatientRecord`
snapshots, it emits one ``fact`` :class:`Event` per newly-added value/source
that ``new`` carries and ``old`` does not.

Each emitted event mirrors the ``fact`` payload contract from
``shared/api.md`` — ``{path, value, source, confidence}`` — where ``source`` is
a :class:`SourceRef` serialized to a JSON-friendly dict. The ``apply_event``
fold in ``derive.py`` consumes exactly these payloads, so emit + replay is a
round trip.

Path conventions mirror ``derive.py``:

- Scalar ``Sourced`` fields reachable by a single-segment path: ``age``,
  ``sex``, ``chief_complaint``, ``suspected_condition``, ``eta``,
  ``acuity_esi``, plus ``allergies`` (conflict-merged like a scalar). For each,
  we emit one fact per *new* :class:`SourceRef` — a source present in
  ``new.<field>.sources`` but not in ``old.<field>.sources``, compared on
  ``(utterance_id, quote)``.
- Append-type list targets ``meds_given`` and ``vitals_timeline``: for each
  entry present in ``new`` beyond what ``old`` already held (``new`` has more
  entries), emit one fact carrying the entry. ``meds_given`` entries are
  ``Sourced[Medication]`` and carry their own source; ``vitals_timeline``
  entries are plain :class:`VitalsEntry` with no provenance wrapper, so a
  :class:`SourceRef` is synthesized from the utterance.

Quote-substring guard (critical): every emitted fact's ``source.quote`` MUST be
a verbatim substring of ``utt.text``. Any candidate whose quote is not a
substring is dropped (not emitted). This is the store-side mirror of the same
guard in extraction.

Determinism: event ids follow ``f"{utt.id}:fact:{index}"`` where ``index`` runs
over emitted facts in a fixed field/entry order, and ``ts`` is always
``utt.ts``. There is no ``datetime.now()`` and no randomness, so replay is
stable. Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

from typing import Any

from shared.schema import (
    Event,
    Medication,
    PatientRecord,
    Sourced,
    SourceRef,
    Utterance,
    VitalsEntry,
)

__all__ = ["facts_from"]


# Scalar ``Sourced`` fields (and ``allergies``) addressable by a single-segment
# path. Order is fixed so emitted event ids are deterministic across replays.
_SCALAR_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "chief_complaint",
    "suspected_condition",
    "eta",
    "acuity_esi",
    "allergies",
)


def _source_key(source: SourceRef) -> tuple[str, str]:
    """Identity of a source for diffing: ``(utterance_id, quote)``."""
    return (source.utterance_id, source.quote)


def _new_sources(old: Sourced, new: Sourced) -> list[SourceRef]:
    """Sources in ``new`` not present in ``old`` (compared on id+quote).

    Order follows ``new.sources`` so emission order is stable.
    """
    seen = {_source_key(source) for source in old.sources}
    return [source for source in new.sources if _source_key(source) not in seen]


def _source_dict(source: SourceRef) -> dict[str, Any]:
    """Serialize a :class:`SourceRef` to a JSON-friendly dict for a payload."""
    return source.model_dump(mode="json")


def _value_dict(model: Any) -> Any:
    """Serialize a Pydantic model value to a JSON-friendly dict."""
    return model.model_dump(mode="json")


def facts_from(
    utt: Utterance, old: PatientRecord, new: PatientRecord
) -> list[Event]:
    """Diff ``old`` vs ``new`` into deterministic ``fact`` events.

    Emits one ``fact`` :class:`Event` per newly-added value/source present in
    ``new`` and absent from ``old``. Any candidate whose ``source.quote`` is not
    a verbatim substring of ``utt.text`` is dropped. Event ids are
    ``f"{utt.id}:fact:{index}"`` in a fixed order and every ``ts`` is
    ``utt.ts``; the function performs no I/O and uses no clock or randomness.
    """
    text = utt.text
    events: list[Event] = []

    def _emit(path: str, value: Any, source: SourceRef, confidence: float) -> None:
        # Store-side guard: the quote must be verbatim text from the utterance.
        if source.quote not in text:
            return
        index = len(events)
        events.append(
            Event(
                id=f"{utt.id}:fact:{index}",
                ts=utt.ts,
                kind="fact",
                payload={
                    "path": path,
                    "value": value,
                    "source": _source_dict(source),
                    "confidence": confidence,
                },
            )
        )

    # --- Scalar / allergies fields: one fact per NEW SourceRef. ---
    for name in _SCALAR_FIELDS:
        old_field: Sourced = getattr(old, name)
        new_field: Sourced = getattr(new, name)
        for source in _new_sources(old_field, new_field):
            _emit(name, new_field.value, source, new_field.confidence)

    # --- meds_given: new Sourced[Medication] entries beyond old's length. ---
    for entry in new.meds_given[len(old.meds_given):]:
        if not entry.sources:
            # No provenance to anchor the fact's quote; cannot pass the guard.
            continue
        source = entry.sources[0]
        value = _value_dict(entry.value) if entry.value is not None else None
        _emit("meds_given", value, source, entry.confidence)

    # --- vitals_timeline: new VitalsEntry rows; synthesize a source. ---
    for entry in new.vitals_timeline[len(old.vitals_timeline):]:
        # Vitals carry no Sourced wrapper, so anchor provenance to the whole
        # utterance text (which is, trivially, a substring of itself).
        source = SourceRef(utterance_id=utt.id, quote=text, ts=utt.ts)
        _emit("vitals_timeline", _value_dict(entry), source, 1.0)

    return events
