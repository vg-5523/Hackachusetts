"""Deterministic record-shape rules: contradiction and missing_info.

``contradiction`` raises one critical flag per top-level Sourced field whose
status is ``conflicted`` (e.g. allergies first reported as none, then a
penicillin bracelet found). ``missing_info`` raises one info flag per required
field still ``unknown``; its evidence list may be empty, since the whole point
is that no source has supplied the value yet.
"""

from __future__ import annotations

from shared.schema import FieldStatus, FlagSeverity, FlagType, PatientRecord, Sourced

from . import rules_data
from .config import REQUIRED_FIELDS
from .hit import Hit

# Top-level Sourced fields examined for contradictions. ``meds_given`` and
# ``vitals_timeline`` are lists, not scalar Sourced fields, so they are excluded.
_SOURCED_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "chief_complaint",
    "suspected_condition",
    "eta",
    "acuity_esi",
    "allergies",
)


def contradiction(record: PatientRecord) -> list[Hit]:
    """One critical hit per ``conflicted`` Sourced field in the record."""
    hits: list[Hit] = []
    for field_name in _SOURCED_FIELDS:
        sourced: Sourced = getattr(record, field_name)
        if sourced.status is not FieldStatus.conflicted:
            continue
        evidence = [s.quote for s in sourced.sources]
        hits.append(
            Hit(
                type=FlagType.contradiction,
                severity=FlagSeverity.critical,
                rule_key=f"contradiction:{field_name}",
                message=(
                    f"The field '{field_name}' is contradictory: its sources "
                    "disagree."
                ),
                citation=rules_data.citation("contradiction"),
                evidence=evidence,
            )
        )
    return hits


def missing_info(record: PatientRecord) -> list[Hit]:
    """One info hit per required field still ``unknown`` (evidence may be [])."""
    hits: list[Hit] = []
    for field_name in REQUIRED_FIELDS:
        sourced: Sourced = getattr(record, field_name)
        if sourced.status is not FieldStatus.unknown:
            continue
        hits.append(
            Hit(
                type=FlagType.missing_info,
                severity=FlagSeverity.info,
                rule_key=f"missing:{field_name}",
                message=f"Required information '{field_name}' is still unknown.",
                citation=rules_data.citation("missing_info"),
                evidence=[],
            )
        )
    return hits
