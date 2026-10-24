"""Output builders for the Ambulance Scribe + Safety Check system.

Phase 1 stubs. These three functions define the output interface that the
frontend and FastAPI stub server code against before the real implementations
land in Phase 2 (``sbar.py``, ``pre_alert.py``, ``checklist.py``). The stubs
return non-empty placeholders and perform no LLM calls, so this module imports
and runs cleanly with ``LLM_API_KEY`` unset.

Targets Python 3.11.
"""

from __future__ import annotations

from shared.schema import Flag, PatientRecord

__all__ = ["make_sbar", "make_pre_alert", "make_checklist"]


def make_sbar(record: PatientRecord, flags: list[Flag]) -> str:
    """Build the SBAR handoff text from the record and flags (stub).

    Phase 1 placeholder: returns a non-empty string. The deterministic
    Situation/Background/Assessment/Recommendation builder arrives in Phase 2.
    """
    return "SBAR not yet available."


def make_pre_alert(record: PatientRecord, flags: list[Flag]) -> str:
    """Build the ED pre-alert text from the record and flags (stub).

    Phase 1 placeholder: returns a non-empty string. The real pre-alert builder
    arrives in Phase 2.
    """
    return "Pre-alert not yet available."


def make_checklist(record: PatientRecord) -> list[str]:
    """Build the receiving-team checklist from the record (stub).

    Phase 1 placeholder: returns a non-empty list of strings. The rule-table
    driven checklist builder arrives in Phase 2.
    """
    return ["Prepare bed"]
