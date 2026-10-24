"""Deterministic bed/resuscitation checklist builder (Phase 2).

``make_checklist`` turns a :class:`~shared.schema.PatientRecord` into a short,
stable list of bed-preparation and resuscitation actions for the receiving
team. It is fully deterministic and performs no LLM calls: the output is a pure
function of the record's ``suspected_condition`` and ``acuity_esi`` fields.

Design (store-outputs, Requirement 4):
  * The condition table is keyed on ``suspected_condition.value`` via
    case-insensitive keyword matching (Req 4.2 STEMI, Req 4.3 stroke, plus
    opioid overdose).
  * An ESI acuity of 1 or 2 adds a resus-bay line.
  * When no condition matches and there is no acuity signal, the checklist is
    empty (``[]``) so an empty record yields ``[]`` (Req 4.6).

Every returned line traces to a specific record field (Req 4.4): the condition
lines to ``suspected_condition`` and the resus-bay line to ``acuity_esi``.

Targets Python 3.11.
"""

from __future__ import annotations

from shared.schema import PatientRecord

__all__ = ["make_checklist"]

# Condition keyword table. Each entry maps a set of lowercase keywords (any of
# which, as a substring of ``suspected_condition.value``, selects the entry) to
# an ordered list of checklist lines. Order within the table defines the stable
# order of condition lines in the output; the first matching entry wins so a
# single condition never contributes two blocks.
_CONDITION_TABLE: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("stemi",),
        [
            "Defibrillator to bedside",
            "Crash cart ready",
            "12-lead ECG on arrival",
            "Notify cath lab",
        ],
    ),
    (
        ("stroke",),
        [
            "Reserve CT slot",
            "Confirm last-known-well time",
        ],
    ),
    (
        ("opioid", "overdose"),
        [
            "Naloxone available",
            "Bag-valve mask ready",
        ],
    ),
]

# ESI acuity levels that warrant a prepared resuscitation bay.
_RESUS_ACUITY = (1, 2)
_RESUS_LINE = "Resus bay prepared"


def make_checklist(record: PatientRecord) -> list[str]:
    """Return the deterministic bed/resuscitation checklist for ``record``.

    The list is keyed on the suspected condition and ESI acuity:

      * ``suspected_condition.value`` is matched case-insensitively against the
        condition table; the first matching entry contributes its lines in
        table order.
      * An ``acuity_esi.value`` of 1 or 2 appends ``"Resus bay prepared"``.

    Returns ``[]`` when the suspected condition is unknown/``None`` and there is
    no acuity signal, so an empty record yields an empty checklist.

    The result is deterministic and stably ordered: condition lines first (in
    table order), then the resus-bay line.
    """
    checklist: list[str] = []

    condition_value = record.suspected_condition.value
    if condition_value is not None:
        condition_lc = condition_value.casefold()
        for keywords, lines in _CONDITION_TABLE:
            if any(keyword in condition_lc for keyword in keywords):
                checklist.extend(lines)
                break

    acuity_value = record.acuity_esi.value
    if acuity_value in _RESUS_ACUITY:
        checklist.append(_RESUS_LINE)

    return checklist
