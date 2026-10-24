"""On-disk cache for LLM responses, keyed by a hash of the utterance text.

Entries live under ``backend/extraction/cache/`` as ``{"text", "response"}``
JSON files named by the SHA-256 of the exact utterance text, so demos replay
offline. This module exposes three pieces the orchestrator composes:

- ``read_cache(utterance, cache_dir=None)`` -> cached response or ``None``
  (``None`` also for an unreadable/corrupt entry).
- ``write_cache(utterance, response, cache_dir=None)`` -> best-effort write.
- ``get_or_call(utterance, prompt, cache_dir=None)`` -> cache-first, else call
  ``llm.call_llm`` and cache the result. A missing ``LLM_API_KEY`` makes
  ``call_llm`` raise ``RuntimeError``; ``get_or_call`` lets it propagate. The
  package orchestrator uses ``read_cache`` + the LLM separately so a missing key
  can fall through to the rules extractor instead of raising.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend import llm
from shared.schema import Utterance

CACHE_DIR = Path(__file__).resolve().parent / "cache"


def cache_key(text: str) -> str:
    """Return the deterministic cache key (hex SHA-256) for ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, text: str) -> Path:
    return cache_dir / f"{cache_key(text)}.json"


def _resolve_dir(cache_dir: Path | None) -> Path:
    return CACHE_DIR if cache_dir is None else Path(cache_dir)


def read_cache(utterance: Utterance, cache_dir: Path | None = None) -> str | None:
    """Return the cached response for ``utterance``, or ``None`` on miss.

    A missing, unreadable, or corrupt entry is reported as a miss (``None``).
    """
    path = _cache_path(_resolve_dir(cache_dir), utterance.text)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    response = obj.get("response")
    return response if isinstance(response, str) else None


def write_cache(utterance: Utterance, response: str, cache_dir: Path | None = None) -> None:
    """Write the cache entry for ``utterance`` atomically; failures are ignored."""
    path = _cache_path(_resolve_dir(cache_dir), utterance.text)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"text": utterance.text, "response": response}, ensure_ascii=False, indent=2
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Caching is best-effort; the response is still returned to the caller.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def get_or_call(utterance: Utterance, prompt: str, cache_dir: Path | None = None) -> str:
    """Return the LLM response for ``utterance``, using the cache first.

    On a miss, calls ``llm.call_llm(prompt)`` and caches the result. A missing
    ``LLM_API_KEY`` makes ``call_llm`` raise ``RuntimeError``, which propagates
    unchanged.
    """
    cached = read_cache(utterance, cache_dir)
    if cached is not None:
        return cached
    response = llm.call_llm(prompt)
    write_cache(utterance, response, cache_dir)
    return response
