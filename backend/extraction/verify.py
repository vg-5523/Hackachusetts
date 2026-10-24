"""Quote verification: keep only proposals backed by a verbatim quote.

A proposal survives ``verify`` only when its ``quote`` is a case-sensitive,
character-for-character substring of ``utterance.text`` and its ``path`` is a
known ``PatientRecord`` path (Req 2.2, 2.3, 2.4). Everything else is dropped so
no unsupported fact can reach the record.
"""

from __future__ import annotations

from shared.schema import Utterance

from .parse import Proposal
from .prompt import EXTRACTABLE_PATHS

KNOWN_PATHS = frozenset(EXTRACTABLE_PATHS)


def verify(proposals: list[Proposal], utterance: Utterance) -> list[Proposal]:
    """Return the subset of ``proposals`` with a verified quote and known path."""
    text = utterance.text
    kept: list[Proposal] = []
    for proposal in proposals:
        if proposal.path not in KNOWN_PATHS:
            continue
        if not proposal.quote:
            continue
        if proposal.quote not in text:
            continue
        kept.append(proposal)
    return kept
