"""Prompt builder for the extraction pipeline.

``build_prompt`` turns an utterance (and the current record, for light context)
into a single instruction string that asks the LLM for a strict-JSON object. The
model is told to copy quotes verbatim from the utterance and to resolve relative
times against the utterance timestamp. The actual LLM call is made by
``backend.llm.call_llm`` through the cache layer, not here.
"""

from __future__ import annotations

from shared.schema import PatientRecord, Utterance

# The record fields the extractor may target. Scalars take a single value;
# ``allergies`` is a list of strings; ``meds_given`` and ``vitals_timeline`` are
# appended to. These mirror ``shared.schema.PatientRecord``.
EXTRACTABLE_PATHS = (
    "age",
    "sex",
    "chief_complaint",
    "suspected_condition",
    "acuity_esi",
    "eta",
    "allergies",
    "meds_given",
    "vitals_timeline",
)

_INSTRUCTIONS = """\
You are a clinical scribe for an ambulance run. Read ONE paramedic utterance and
return ONLY a single JSON object, no prose and no code fences, of the form:

{"facts": [{"path": str, "value": any, "quote": str, "confidence": number, "hedged": bool}]}

Rules:
- Emit one fact per distinct piece of information you can support with the words.
- "path" must be exactly one of: %(paths)s
- "quote" MUST be copied VERBATIM (character for character) from the utterance
  text below. Never paraphrase a quote. If you cannot quote it, omit the fact.
- "confidence" is a number from 0 to 1.
- "hedged" is true when the speaker is uncertain ("maybe", "I think", "possibly")
  or the words are garbled/incomplete; otherwise false.
- "acuity_esi" value must be an integer from 1 to 5.
- For "meds_given", "value" is an object {"drug","dose","route","time","given_by"}
  (any field may be omitted).
- For "vitals_timeline", "value" is an object {"ts","hr","bp","spo2","rr","source"}.
- For "allergies", emit one fact per allergy; "value" is the allergy string
  (use "none" when the patient reports no allergies).
- Resolve any relative time (e.g. "two minutes ago") against the utterance
  timestamp and express the result as an offset-aware ISO 8601 string.
"""


def build_prompt(utterance: Utterance, record: PatientRecord) -> str:
    """Return the strict-JSON extraction prompt for ``utterance``.

    ``record`` is accepted for future context use and to keep the Phase 1
    orchestration signature; the current prompt does not embed it to keep the
    cache key (a hash of the utterance text) stable across record states.
    """
    header = _INSTRUCTIONS % {"paths": ", ".join(EXTRACTABLE_PATHS)}
    return (
        f"{header}\n"
        f"Utterance timestamp: {utterance.ts.isoformat()}\n"
        f"Utterance text:\n{utterance.text}\n"
    )
