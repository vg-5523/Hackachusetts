"""Extraction package: turns paramedic utterances into patient-record facts.

``process_utterance`` resolves one utterance into a new ``PatientRecord`` with
provenance, trying three sources in order:

1. **Disk cache** - a hash-keyed cached LLM response under
   ``backend/extraction/cache/`` (demos replay offline).
2. **LLM** - only when ``LLM_API_KEY`` is set; the response is cached.
3. **Rules fallback** - the deterministic, LLM-free ``rules_extract`` when there
   is no cache hit and no key.

Because of step 3, a missing ``LLM_API_KEY`` never raises here: the pipeline
degrades to rules-based extraction. (The lower-level ``cache.get_or_call`` still
raises on a missing key, but the orchestrator does not call it directly.)

The LLM is reached through ``backend.llm`` so tests can monkeypatch
``backend.llm.call_llm``. Models are imported read-only from ``shared.schema``.
All code in this package edits only files under ``backend/extraction/``.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from shared.schema import PatientRecord, Utterance

from backend import llm
from .apply import apply_proposals
from .cache import cache_key, get_or_call, read_cache, write_cache
from .parse import Proposal, parse_response
from .prompt import build_prompt
from .rules_extract import rules_extract
from .verify import verify

__all__ = [
    "process_utterance",
    "build_prompt",
    "get_or_call",
    "read_cache",
    "write_cache",
    "cache_key",
    "parse_response",
    "verify",
    "apply_proposals",
    "rules_extract",
    "Proposal",
]


def _llm_key_set() -> bool:
    """Return True when LLM_API_KEY is available.

    Consults the process environment first; if absent, loads a repo-root .env
    (the same fallback backend.llm.call_llm uses) so the orchestrator agrees
    with the wrapper about whether a key exists. The key value is never logged.
    """
    if os.environ.get("LLM_API_KEY"):
        return True
    load_dotenv()
    return bool(os.environ.get("LLM_API_KEY"))


def process_utterance(utterance: Utterance, record: PatientRecord) -> PatientRecord:
    """Extract facts from ``utterance`` and return a new ``PatientRecord``.

    The input ``record`` is never mutated. New facts are appended with their
    provenance; conflict resolution is left to ``backend/store``.

    Resolution order: disk cache, then the LLM when ``LLM_API_KEY`` is set, then
    the deterministic rules fallback. A missing key does not raise.
    """
    prompt = build_prompt(utterance, record)

    # 1. Disk cache (offline replay).
    response = read_cache(utterance)

    # 2. LLM, only when a key is configured. The response is cached for replay.
    if response is None and _llm_key_set():
        response = llm.call_llm(prompt)
        write_cache(utterance, response)

    if response is not None:
        proposals = parse_response(response)
        proposals = verify(proposals, utterance)
        if proposals:
            return apply_proposals(record, proposals, utterance)
        # A cached/LLM response that yields no facts falls through to rules so a
        # thin response still benefits from the deterministic extractor.

    # 3. Deterministic rules fallback (no LLM, never raises for a missing key).
    proposals = rules_extract(utterance)
    proposals = verify(proposals, utterance)
    return apply_proposals(record, proposals, utterance)
