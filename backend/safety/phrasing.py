"""Phrasing of the ``say_to_crew`` line.

The LLM's *only* role in the safety engine is to phrase the single
``say_to_crew`` sentence a human operator may relay to the crew. It never
changes a flag's type, severity, evidence, or citation. Every LLM call goes
through :func:`backend.llm.call_llm`; if that call is unavailable or fails for
any reason (including ``LLM_API_KEY`` being unset), a deterministic per-type
template sentence is used instead. The result is always 1 to 280 non-blank
characters so it satisfies the schema.
"""

from __future__ import annotations

from shared.schema import FlagType

from .hit import Hit

_MAX = 280

_TEMPLATES: dict[FlagType, str] = {
    FlagType.duplicate_dose: (
        "Heads up: a medication may have been given more than once. "
        "Confirm the total dose before any further administration."
    ),
    FlagType.allergy_conflict: (
        "Allergy conflict: a drug given may conflict with a listed allergy. "
        "Review before further doses and flag it to the receiving team."
    ),
    FlagType.interaction: (
        "Possible drug interaction between medications given. "
        "Review before any further administration."
    ),
    FlagType.contradiction: (
        "Conflicting information in the record. "
        "Clarify before handoff and treat conservatively until resolved."
    ),
    FlagType.missing_info: (
        "Missing critical information. "
        "Confirm the detail with the crew when able."
    ),
}


def _template(hit: Hit) -> str:
    """The deterministic fallback line for ``hit``'s type."""
    return _TEMPLATES[hit.type][:_MAX]


def _build_prompt(hit: Hit) -> str:
    evidence = "\n".join(f"- {q}" for q in hit.evidence) or "- (none)"
    return (
        "You phrase one short line for a human operator to optionally relay to "
        "an ambulance crew. Do not give clinical advice or invent facts. Use at "
        "most 280 characters, one or two sentences.\n\n"
        f"Safety issue: {hit.message}\n"
        f"Evidence quotes:\n{evidence}\n\n"
        "Line:"
    )


def say_to_crew(hit: Hit) -> str:
    """Return the ``say_to_crew`` line for ``hit``.

    Tries :func:`backend.llm.call_llm`; accepts its reply only when the reply is
    1 to 280 non-blank characters, otherwise (and on any exception) returns the
    per-type template. The reply is defensively truncated to 280 characters.
    """
    try:
        # Imported through the module so tests can patch ``backend.llm.call_llm``.
        from backend import llm

        reply = llm.call_llm(_build_prompt(hit))
    except Exception:
        return _template(hit)

    if not isinstance(reply, str):
        return _template(hit)
    cleaned = reply.strip()
    if not cleaned:
        return _template(hit)
    return cleaned[:_MAX]
