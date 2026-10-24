"""Deterministic ED pre-alert builder (Phase 2).

``make_pre_alert`` turns a :class:`~shared.schema.PatientRecord` plus the open
:class:`~shared.schema.Flag` list into a short radio-style pre-alert: one compact
line the receiving ED hears before the ambulance arrives. It is fully
deterministic and performs no LLM calls: the output is a pure function of its
inputs, so the same record and flags always render the same string.

Design (store-outputs, Requirement 4):
  * The line is built only from the key handoff fields -- ``age``, ``sex``,
    ``chief_complaint``, ``suspected_condition``, ``acuity_esi`` (ESI), and
    ``eta`` -- plus any CRITICAL-severity flags (Req 4.1). Warn/info flags are
    the SBAR's job and are ignored here.
  * This is a pre-alert, not the full SBAR: it stays to a single compact line,
    including only the fields that are present and skipping any ``Sourced``
    scalar whose value is ``None``/unknown.
  * A value whose status is ``unverified`` or ``conflicted`` is labelled inline
    (e.g. ``"query penicillin allergy (conflicted)"``) so the ED hears the
    uncertainty (Req 4.5).
  * Every rendered fragment traces to a specific record field (Req 4.4).
  * When the record carries no key scalar values and there are no critical
    flags, the pre-alert is empty (``""``), so an empty record yields ``""``
    (Req 4.6).

Targets Python 3.11.
"""

from __future__ import annotations

from shared.schema import FieldStatus, Flag, FlagSeverity, PatientRecord, Sourced

__all__ = ["make_pre_alert"]


def _render(sourced: Sourced) -> str | None:
    """Render a scalar ``Sourced`` value for the pre-alert, or ``None`` to skip.

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


def make_pre_alert(record: PatientRecord, flags: list[Flag]) -> str:
    """Return the deterministic ED pre-alert line for ``record`` and ``flags``.

    The line is assembled from the key handoff fields, in a stable order:
    demographics (age/sex), chief complaint, suspected condition, ESI acuity,
    then ETA, followed by any CRITICAL-severity flags. Only present fields are
    included; ``unverified``/``conflicted`` values are tagged inline.

    Returns ``""`` when there is nothing to announce: every key ``Sourced``
    scalar is ``None`` and no critical flags are present (so an empty record
    yields an empty string).
    """
    parts: list[str] = []

    # Demographics: "<age> <sex>", "<age>", or "<sex>" -- whichever are present.
    age = _render(record.age)
    sex = _render(record.sex)
    if age is not None and sex is not None:
        parts.append(f"{age} {sex}")
    elif age is not None:
        parts.append(age)
    elif sex is not None:
        parts.append(sex)

    complaint = _render(record.chief_complaint)
    if complaint is not None:
        parts.append(complaint)

    condition = _render(record.suspected_condition)
    if condition is not None:
        parts.append(f"suspected {condition}")

    acuity = _render(record.acuity_esi)
    if acuity is not None:
        parts.append(f"ESI {acuity}")

    eta = _render(record.eta)
    if eta is not None:
        parts.append(f"ETA {eta}")

    # Critical flags only; warn/info are left to the fuller SBAR. Prefer the
    # concise message, falling back to the flag type when a message is blank.
    for flag in flags:
        if flag.severity is not FlagSeverity.critical:
            continue
        label = flag.message.strip() or flag.type.value
        parts.append(f"CRITICAL: {label}")

    if not parts:
        return ""

    # Strip a trailing sentence period from each fragment (flag messages often
    # end in one) so the joined line carries a single terminal period.
    parts = [part.rstrip(".").rstrip() for part in parts]
    return "Pre-alert: " + "; ".join(parts) + "."
