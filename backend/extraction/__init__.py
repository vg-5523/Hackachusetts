"""Extraction package: turns paramedic utterances into patient-record facts.

Public entry point ``process_utterance`` keeps the Phase 1 signature and
orchestrates the pipeline:

    build_prompt -> cache.get_or_call -> parse_response -> verify -> apply_proposals

The LLM is reached through ``backend.llm`` (imported as a module) via the cache
layer, so tests can monkeypatch ``backend.llm.call_llm``. Errors from the LLM -
notably the missing-``LLM_API_KEY`` ``RuntimeError`` on a cache miss - are NOT
caught here; they propagate to the caller so the API reports a 500 (Req 6.1,
6.2). A malformed response, by contrast, parses to no facts and simply yields a
record with nothing added (Req 1.8).

Models are imported read-only from ``shared.schema``. All code in this package
edits only files under ``backend/extraction/``.
"""

from __future__ import annotations

from shared.schema import PatientRecord, Utterance

from .apply import apply_proposals
from .cache import get_or_call
from .parse import Proposal, parse_response
from .prompt import build_prompt
from .verify import verify

__all__ = [
    "process_utterance",
    "build_prompt",
    "get_or_call",
    "parse_response",
    "verify",
    "apply_proposals",
    "Proposal",
]


def process_utterance(utterance: Utterance, record: PatientRecord) -> PatientRecord:
    """Extract facts from ``utterance`` and return a new ``PatientRecord``.

    The input ``record`` is never mutated. New facts are appended with their
    provenance; conflict resolution is left to ``backend/store``.
    """
    prompt = build_prompt(utterance, record)
    response = get_or_call(utterance, prompt)
    proposals = parse_response(response)
    proposals = verify(proposals, utterance)
    return apply_proposals(record, proposals, utterance)
