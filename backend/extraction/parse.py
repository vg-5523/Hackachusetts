"""Tolerant parser that turns an LLM response into ``Proposal`` records.

The LLM is asked for a strict-JSON object, but real responses sometimes wrap it
in code fences or prose. ``parse_response`` strips fences, locates the first
JSON object, and reads its ``facts`` list. Any malformation yields ``[]`` rather
than raising, so a bad response produces no facts (Req 1.8). Individual entries
missing required keys, or with a confidence outside 0..1, are dropped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Proposal:
    """One candidate fact proposed by the LLM, before quote verification."""

    path: str
    value: Any
    quote: str
    confidence: float
    hedged: bool = False
    # Extra keys from the model are ignored but preserved for debugging.
    extra: dict = field(default_factory=dict)


def _strip_fences(text: str) -> str:
    """Remove Markdown code fences so the raw JSON can be located."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the opening fence line (which may carry a language tag) and any
        # trailing fence.
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _extract_object(text: str) -> str | None:
    """Return the substring from the first ``{`` to its matching ``}``."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_response(text: str) -> list[Proposal]:
    """Parse ``text`` into a list of well-formed :class:`Proposal` records.

    Returns ``[]`` when the text is not a single JSON object, when ``facts`` is
    missing or not a list, or when no entry is well formed. Entries missing
    ``path``/``value``/``quote`` or with a non-numeric/out-of-range
    ``confidence`` are skipped individually.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    candidate = _extract_object(_strip_fences(text))
    if candidate is None:
        return []
    try:
        obj = json.loads(candidate)
    except (ValueError, TypeError):
        return []
    if not isinstance(obj, dict):
        return []

    facts = obj.get("facts")
    if not isinstance(facts, list):
        return []

    proposals: list[Proposal] = []
    for entry in facts:
        if not isinstance(entry, dict):
            continue
        if "path" not in entry or "value" not in entry or "quote" not in entry:
            continue
        path = entry["path"]
        quote = entry["quote"]
        if not isinstance(path, str) or not isinstance(quote, str):
            continue
        confidence = entry.get("confidence", 0.0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            continue
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            continue
        hedged = bool(entry.get("hedged", False))
        known = {"path", "value", "quote", "confidence", "hedged"}
        extra = {k: v for k, v in entry.items() if k not in known}
        proposals.append(
            Proposal(
                path=path,
                value=entry["value"],
                quote=quote,
                confidence=confidence,
                hedged=hedged,
                extra=extra,
            )
        )
    return proposals
