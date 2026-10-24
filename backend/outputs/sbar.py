"""Deterministic SBAR handoff builder (Phase 2).

``make_sbar`` turns a :class:`~shared.schema.PatientRecord` plus the current
:class:`~shared.schema.Flag` list into a four-section SBAR handoff
(Situation / Background / Assessment / Recommendation): the structured verbal
handoff the receiving team expects. It is fully deterministic and performs no
LLM calls, so the same record and flags always render the same string.

Design (store-outputs, Requirement 4):
  * Each section is built only from specific record fields, and every rendered
    line traces back to the field it came from (Req 4.4):
      - Situation: ``chief_complaint``, ``suspected_condition``, ``acuity_esi``.
      - Background: ``age``, ``sex``, ``allergies``, ``meds_given`` (drug + dose).
      - Assessment: the latest ``vitals_timeline`` entry (highest ``ts``) plus
        any active flags (status ``open`` or ``relayed``), critical first.
      - Recommendation: derived from ``suspected_condition`` and active flags.
  * A ``Sourced`` scalar whose value is ``None``/unknown is skipped entirely, so
    only present fields appear.
  * A value whose status is ``unverified`` or ``conflicted`` is labelled inline
    (e.g. ``"Allergies: penicillin (conflicted)"``) so the receiving team hears
    the uncertainty (Req 4.5).
  * When the record carries no values at all (every ``Sourced`` scalar ``None``,
    no allergies, no meds, no vitals) and there are no flags, the SBAR is empty
    (``""``), so an empty record yields ``""`` (Req 4.6).

Targets Python 3.11.
"""

from __future__ import annotations

from shared.schema import (
    FieldStatus,
    Flag,
    FlagSeverity,
    FlagStatus,
    PatientRecord,
    Sourced,
)

__all__ = ["make_sbar"]

# Flag statuses that count as "active" for the SBAR: a relayed flag is still an
# open concern for the receiving team, but an acknowledged one has been closed.
_ACTIVE_FLAG_STATUSES = (FlagStatus.open, FlagStatus.relayed)


def _render(sourced: Sourced) -> str | None:
    """Render a scalar ``Sourced`` value for the SBAR, or ``None`` to skip.

    Returns ``None`` when the value is absent (``None``), so callers can drop the
    field entirely. Otherwise returns the stringified value with an inline
    ``(unverified)`` / ``(conflicted)`` tag appended when the provenance status
    warrants it (Req 4.5). ``confirmed``/``unknown`` statuses render bare.
    """
    value = sourced.value
    if value is None:
        return None
    text = str(value)
    if sourced.status is FieldStatus.unverified:
        return f"{text} (unverified)"
    if sourced.status is FieldStatus.conflicted:
        return f"{text} (conflicted)"
    return text


def _active_flags(flags: list[Flag]) -> list[Flag]:
    """Return active flags (status ``open``/``relayed``), critical severity first.

    The ordering is stable: critical flags keep their incoming relative order,
    then warn/info flags keep theirs. Acknowledged flags are dropped.
    """
    active = [flag for flag in flags if flag.status in _ACTIVE_FLAG_STATUSES]
    critical = [f for f in active if f.severity is FlagSeverity.critical]
    other = [f for f in active if f.severity is not FlagSeverity.critical]
    return critical + other


def _render_allergies(sourced: Sourced) -> str | None:
    """Render the ``allergies`` list ``Sourced`` as a line body, or ``None``.

    ``allergies`` wraps a ``list[str]`` rather than a scalar, so it needs its own
    renderer: an empty or ``None`` list is skipped, otherwise the allergens are
    joined and the provenance status is tagged inline (Req 4.5).
    """
    value = sourced.value
    if not value:
        return None
    text = ", ".join(str(item) for item in value)
    if sourced.status is FieldStatus.unverified:
        return f"{text} (unverified)"
    if sourced.status is FieldStatus.conflicted:
        return f"{text} (conflicted)"
    return text


def _render_med(sourced: Sourced) -> str | None:
    """Render one ``meds_given`` entry as ``"<drug> <dose>"``, or ``None``.

    Uses the medication's drug and dose (the two handoff-relevant fields); an
    entry with neither is skipped. The provenance status of the ``Sourced``
    wrapper is tagged inline when ``unverified``/``conflicted`` (Req 4.5).
    """
    med = sourced.value
    if med is None:
        return None
    pieces = [piece for piece in (med.drug, med.dose) if piece]
    if not pieces:
        return None
    text = " ".join(str(piece) for piece in pieces)
    if sourced.status is FieldStatus.unverified:
        return f"{text} (unverified)"
    if sourced.status is FieldStatus.conflicted:
        return f"{text} (conflicted)"
    return text


def _latest_vitals_line(record: PatientRecord) -> str | None:
    """Render the most recent vitals entry as a compact line, or ``None``.

    Picks the ``vitals_timeline`` entry with the highest ``ts`` (the latest
    reading) and formats whichever of HR, BP, SpO2, and RR are present. Returns
    ``None`` when the timeline is empty or the latest entry has no measurements.
    """
    if not record.vitals_timeline:
        return None
    latest = max(record.vitals_timeline, key=lambda entry: entry.ts)
    pieces: list[str] = []
    if latest.hr is not None:
        pieces.append(f"HR {latest.hr}")
    if latest.bp is not None:
        pieces.append(f"BP {latest.bp}")
    if latest.spo2 is not None:
        pieces.append(f"SpO2 {latest.spo2}%")
    if latest.rr is not None:
        pieces.append(f"RR {latest.rr}")
    if not pieces:
        return None
    return ", ".join(pieces)


def make_sbar(record: PatientRecord, flags: list[Flag]) -> str:
    """Return the deterministic SBAR handoff for ``record`` and ``flags``.

    Builds four labelled sections -- Situation, Background, Assessment,
    Recommendation -- each from the specific fields named in the module
    docstring. Only present fields appear; ``unverified``/``conflicted`` values
    are tagged inline, and active flags (status ``open``/``relayed``) list
    critical severity first.

    Returns ``""`` when there is nothing to hand off: every ``Sourced`` scalar
    is ``None``, there are no allergies, meds, or vitals, and ``flags`` is empty
    (so an empty record with no flags yields an empty string).
    """
    active_flags = _active_flags(flags)

    # Situation: why this patient, how sick.
    situation: list[str] = []
    complaint = _render(record.chief_complaint)
    if complaint is not None:
        situation.append(f"Chief complaint: {complaint}")
    condition = _render(record.suspected_condition)
    if condition is not None:
        situation.append(f"Suspected: {condition}")
    acuity = _render(record.acuity_esi)
    if acuity is not None:
        situation.append(f"Acuity ESI {acuity}")

    # Background: demographics, allergies, meds given.
    background: list[str] = []
    age = _render(record.age)
    if age is not None:
        background.append(f"Age: {age}")
    sex = _render(record.sex)
    if sex is not None:
        background.append(f"Sex: {sex}")
    allergies = _render_allergies(record.allergies)
    if allergies is not None:
        background.append(f"Allergies: {allergies}")
    med_lines = [line for line in (_render_med(m) for m in record.meds_given) if line]
    if med_lines:
        background.append("Meds given: " + "; ".join(med_lines))

    # Assessment: latest vitals plus active flags (critical first).
    assessment: list[str] = []
    vitals = _latest_vitals_line(record)
    if vitals is not None:
        assessment.append(f"Latest vitals: {vitals}")
    for flag in active_flags:
        label = flag.message.strip() or flag.type.value
        prefix = "CRITICAL" if flag.severity is FlagSeverity.critical else "Flag"
        assessment.append(f"{prefix}: {label}")

    # Recommendation: derived from suspected condition and active flags.
    recommendation: list[str] = []
    if condition is not None:
        recommendation.append(f"Prepare for {condition} per protocol")
    critical_flags = [f for f in active_flags if f.severity is FlagSeverity.critical]
    for flag in critical_flags:
        say = flag.say_to_crew.strip()
        if say:
            recommendation.append(say)
    if condition is None and not critical_flags and active_flags:
        # No condition and no critical flags, but non-critical concerns remain:
        # still give the receiving team an actionable nudge.
        recommendation.append("Review flagged concerns before handoff")

    sections: list[tuple[str, list[str]]] = [
        ("Situation", situation),
        ("Background", background),
        ("Assessment", assessment),
        ("Recommendation", recommendation),
    ]

    # Nothing to hand off at all -> empty string (empty record, no flags).
    if not any(body for _, body in sections):
        return ""

    lines: list[str] = []
    for label, body in sections:
        if not body:
            continue
        lines.append(f"{label}:")
        lines.extend(f"- {item}" for item in body)
    return "\n".join(lines)
