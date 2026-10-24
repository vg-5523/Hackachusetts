"""On-disk, cache-first access to the LLM response for an utterance.

``get_or_call`` keys each entry by a SHA-256 hash of the exact utterance text and
stores ``{"text", "response"}`` under ``backend/extraction/cache/``. On a hit it
returns the cached response WITHOUT calling the LLM, so demos replay offline
(Req 5.2). On a miss - including an unreadable or corrupt entry (Req 5.4) - it
calls ``llm.call_llm`` through the module (so tests can patch it), writes the
result, and returns it. When no key is configured and there is no cache entry,
``call_llm`` raises ``RuntimeError`` and that error is allowed to propagate
unchanged (Req 6.1, 6.2).
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


def _read_cache(path: Path) -> str | None:
    """Return the cached response, or ``None`` if absent/unreadable/corrupt."""
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


def _write_cache(path: Path, text: str, response: str) -> None:
    """Write the cache entry atomically; a write failure is non-fatal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"text": text, "response": response}, ensure_ascii=False, indent=2)
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

    ``cache_dir`` defaults to ``backend/extraction/cache/`` and is overridable so
    tests can isolate the cache in a temporary directory.
    """
    directory = CACHE_DIR if cache_dir is None else Path(cache_dir)
    path = _cache_path(directory, utterance.text)

    cached = _read_cache(path)
    if cached is not None:
        return cached

    # Miss (or corrupt entry): call the LLM. A missing LLM_API_KEY makes
    # ``call_llm`` raise RuntimeError, which propagates unchanged (Req 6.1, 6.2).
    response = llm.call_llm(prompt)
    _write_cache(path, utterance.text, response)
    return response
