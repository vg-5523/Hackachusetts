"""Loader for the curated ``rules.json`` interaction/allergy data.

``rules.json`` is the primary source of truth for drug interactions (the RxNav
interaction API is retired). This module loads it once and exposes typed helpers
for citations, drug classes, and interaction rules.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.schema import Citation

RULES_PATH = Path(__file__).resolve().parent / "rules.json"


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    with RULES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def citation(key: str) -> Citation:
    """Return the :class:`Citation` registered under ``key`` in ``rules.json``."""
    entry = _data().get("citations", {})[key]
    return Citation(name=entry["name"], url=entry["url"])


def classes() -> dict[str, list[str]]:
    """Return the drug-class map (class name -> member drug names)."""
    return {k: list(v) for k, v in _data().get("classes", {}).items()}


def interactions() -> list[dict[str, Any]]:
    """Return the curated interaction rules."""
    return list(_data().get("interactions", []))
