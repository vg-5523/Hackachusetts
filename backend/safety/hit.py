"""The internal ``Hit`` produced by rule functions.

A ``Hit`` is the deterministic, rule-authored core of a flag: its type,
severity, a ``rule_key`` that identifies the specific rule, a plain message, the
evidence quotes taken verbatim from the record's sources, and the citation used
as the flag's ``source_ref``. :func:`backend.safety.evaluate` turns each ``Hit``
into a schema-validated :class:`~shared.schema.Flag`, attaching the deterministic
id and the (LLM- or template-) phrased ``say_to_crew``. Nothing the LLM does can
change a ``Hit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.schema import Citation, FlagSeverity, FlagType


@dataclass(frozen=True)
class Hit:
    """One deterministic rule result, pre-phrasing."""

    type: FlagType
    severity: FlagSeverity
    rule_key: str
    message: str
    citation: Citation
    evidence: list[str] = field(default_factory=list)
