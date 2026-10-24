"""Extraction package: turns paramedic utterances into patient-record facts.

Phase 1 stub. The real pipeline (prompt, LLM call, parse, verify, apply) is
wired in Phase 2 (task 9). This stub returns the received record unchanged and
imports cleanly with ``LLM_API_KEY`` unset, since it makes no LLM call.
"""

from shared.schema import PatientRecord, Utterance


def process_utterance(utterance: Utterance, record: PatientRecord) -> PatientRecord:
    """Return the patient record unchanged (Phase 1 stub).

    The real implementation will derive facts from ``utterance`` and apply them
    to ``record``; for now it returns the same ``record`` object with no field
    modified.
    """
    return record
