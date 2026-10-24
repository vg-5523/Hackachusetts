"""Read-through, on-disk JSON cache for external API responses.

Every call the safety module makes to an external API (RxNorm) is routed through
:func:`cached`. On a cache hit the stored JSON is returned and ``fetch`` is never
called; on a miss ``fetch`` is called once and its result is written to disk so
subsequent runs (and the committed demo) work with no network access.

Entries live under ``backend/safety/cache/`` as one JSON file per
``(kind, key)`` pair, named by a filesystem-safe slug. The directory is created
on first write.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path(__file__).resolve().parent / "cache"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Return a lowercase, filesystem-safe slug for ``text``."""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "empty"


def cache_path(kind: str, key: str, cache_dir: Path | None = None) -> Path:
    """Return the on-disk path for the ``(kind, key)`` cache entry."""
    base = cache_dir if cache_dir is not None else CACHE_DIR
    return base / f"{_slug(kind)}__{_slug(key)}.json"


def cached(
    kind: str,
    key: str,
    fetch: Callable[[], Any],
    cache_dir: Path | None = None,
) -> Any:
    """Return the cached JSON for ``(kind, key)``, fetching only on a miss.

    On a hit the stored value is returned and ``fetch`` is **not** called. On a
    miss ``fetch`` is called once, its (JSON-serializable) result is written to
    disk, and that result is returned.
    """
    path = cache_path(kind, key, cache_dir)
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    value = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)
    return value
