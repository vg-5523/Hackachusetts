"""Tunable configuration for the safety engine.

Keeping these values in one module makes the duplicate-dose window and the
required-field list for ``missing_info`` easy to adjust without touching rule
logic.
"""

from __future__ import annotations

# A second dose of the same drug counts as a duplicate when it falls within this
# many minutes of an earlier dose. Configurable per Requirement R3.1.
DUPLICATE_WINDOW_MINUTES: int = 60

# Top-level ``PatientRecord`` Sourced fields that a ``missing_info`` flag is
# raised for while their status is still ``unknown``. ``allergies`` is first:
# an unknown allergy status is the safety-critical gap this product watches for.
REQUIRED_FIELDS: tuple[str, ...] = (
    "allergies",
    "chief_complaint",
    "age",
)
