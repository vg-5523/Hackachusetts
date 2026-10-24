"""Safety package: evaluates a patient record and raises cited safety flags.

Phase 1 stub. The real engine (duplicate dose, allergy conflict, interaction,
and contradiction rules, each producing a cited :class:`Flag`) is wired in a
later phase. This stub returns no flags and imports cleanly with
``LLM_API_KEY`` unset, since it makes no LLM call.
"""

from shared.schema import Flag, PatientRecord


def evaluate(record: PatientRecord) -> list[Flag]:
    """Return an empty list of flags (Phase 1 stub).

    The real implementation will derive deterministic, cited safety flags from
    ``record``; for now it raises none.
    """
    return []
