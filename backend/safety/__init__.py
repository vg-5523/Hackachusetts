"""Safety package: evaluates a patient record and raises cited safety flags.

The public entry point is :func:`evaluate`. It is deterministic and rule-based:
the rules in :mod:`backend.safety.rules_meds` and
:mod:`backend.safety.rules_record` produce :class:`~backend.safety.hit.Hit`
objects, and :func:`evaluate` turns each into a schema-validated
:class:`~shared.schema.Flag`. The only non-deterministic step is phrasing the
``say_to_crew`` line, which falls back to a per-type template whenever the LLM is
unavailable, so the module runs fully offline (see
:mod:`backend.safety.phrasing`). Drug names are normalized through an on-disk
RxNorm cache committed under ``backend/safety/cache/``.
"""

from __future__ import annotations

from pathlib import Path

from shared.schema import Flag, PatientRecord

from .hit import Hit
from .ids import flag_id
from .phrasing import say_to_crew
from .rules_meds import allergy_conflict, duplicate_dose, interaction
from .rules_record import contradiction, missing_info

__all__ = ["evaluate"]


def _to_flag(hit: Hit) -> Flag:
    """Build a schema-validated :class:`Flag` from a deterministic ``Hit``."""
    return Flag(
        id=flag_id(hit.type.value, hit.rule_key, hit.evidence),
        type=hit.type,
        severity=hit.severity,
        message=hit.message,
        say_to_crew=say_to_crew(hit),
        evidence=hit.evidence,
        source_ref=hit.citation,
    )


def evaluate(record: PatientRecord, cache_dir: Path | None = None) -> list[Flag]:
    """Return the deterministic, cited safety flags for ``record``.

    All rules are run, each hit is converted to a validated :class:`Flag`, and
    the result is returned in a stable order (by flag type, then id). Because ids
    are a pure function of type, rule key, and sorted evidence, calling
    ``evaluate`` twice on the same record returns identical ids in the same
    order. ``cache_dir`` overrides the RxNorm cache location (used by tests).
    """
    hits: list[Hit] = []
    hits += duplicate_dose(record, cache_dir)
    hits += allergy_conflict(record, cache_dir)
    hits += interaction(record, cache_dir)
    hits += contradiction(record)
    hits += missing_info(record)

    flags = [_to_flag(hit) for hit in hits]
    flags.sort(key=lambda f: (f.type.value, f.id))
    return flags
