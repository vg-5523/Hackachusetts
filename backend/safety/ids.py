"""Deterministic, idempotent flag ids.

A flag id is ``f"{type}:{sha1(type + rule_key + sorted(evidence))[:12]}"``. The
evidence list is sorted and joined with a fixed separator before hashing so the
id does not depend on the order evidence quotes are discovered. The id is a pure
function of its inputs, so calling :func:`flag_id` twice with the same inputs
always yields the same value (and the ``type:`` prefix plus 12 hex characters is
well under the schema's 64-character limit).
"""

from __future__ import annotations

import hashlib

# A separator that cannot appear mid-quote in a way that collides two different
# evidence lists into the same joined string.
_EVIDENCE_SEP = "\x1f"


def flag_id(flag_type: str, rule_key: str, evidence: list[str]) -> str:
    """Return the deterministic id for a flag.

    ``flag_type`` is the ``FlagType`` value (e.g. ``"duplicate_dose"``),
    ``rule_key`` identifies the specific rule hit, and ``evidence`` is the list
    of evidence quotes. The result is ``f"{flag_type}:{digest[:12]}"``.
    """
    joined_evidence = _EVIDENCE_SEP.join(sorted(evidence))
    material = f"{flag_type}{rule_key}{joined_evidence}".encode("utf-8")
    digest = hashlib.sha1(material).hexdigest()[:12]
    return f"{flag_type}:{digest}"
