"""Output builders for the Ambulance Scribe + Safety Check system.

Public interface for the three deterministic output generators. The real
Phase 2 implementations live in sibling modules -- ``sbar.py``, ``pre_alert.py``,
and ``checklist.py`` -- and are re-exported here so callers can keep importing
``make_sbar`` / ``make_pre_alert`` / ``make_checklist`` straight from
``backend.outputs``, exactly as they did against the Phase 1 stubs. The public
signatures are unchanged.

Targets Python 3.11.
"""

from __future__ import annotations

from backend.outputs.checklist import make_checklist
from backend.outputs.pre_alert import make_pre_alert
from backend.outputs.sbar import make_sbar

__all__ = ["make_sbar", "make_pre_alert", "make_checklist"]
