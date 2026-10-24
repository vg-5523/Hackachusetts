"""RxNorm drug-name normalization, cached on disk and offline-safe.

:func:`normalize` maps a free-text drug name to a stable RxNorm concept id
(``rxcui``) so that two spellings of the same drug compare equal. Every RxNorm
response is routed through :func:`backend.safety.cache.cached`, so once the demo
drugs are pre-warmed (and committed), normalization needs no network. When a
name is not in the cache and the network is unavailable, normalization degrades
gracefully to the lowercased name rather than raising.

Confirmed at design time: the RxNav drug-interaction endpoint is retired
(HTTP 404), but the RxNorm ``rxcui`` endpoint works (aspirin -> 1191). Only the
``rxcui`` and ``approximateTerm`` endpoints are used here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache import cached

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
_HTTP_TIMEOUT = 20.0


def _fetch_rxcui(name: str) -> dict[str, Any]:
    """Fetch the RxNorm response for ``name`` (network; miss path only).

    Tries the exact ``rxcui`` lookup first, then falls back to an approximate
    match. Returns a small dict ``{"rxcui": str | None}``. ``httpx`` is imported
    lazily so the module imports cleanly in a no-network environment and so the
    cache hit path never requires the dependency.
    """
    import httpx

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(
            f"{RXNORM_BASE}/rxcui.json",
            params={"name": name, "search": 1},
        )
        resp.raise_for_status()
        ids = (
            resp.json().get("idGroup", {}).get("rxnormId", [])
            if isinstance(resp.json(), dict)
            else []
        )
        if ids:
            return {"rxcui": str(ids[0])}

        # Fall back to an approximate match (handles e.g. bare "penicillin").
        approx = client.get(
            f"{RXNORM_BASE}/approximateTerm.json",
            params={"term": name, "maxEntries": 1},
        )
        approx.raise_for_status()
        candidates = (
            approx.json().get("approximateGroup", {}).get("candidate", [])
            if isinstance(approx.json(), dict)
            else []
        )
        if candidates and isinstance(candidates[0], dict):
            rxcui = candidates[0].get("rxcui")
            if rxcui:
                return {"rxcui": str(rxcui)}

    return {"rxcui": None}


def normalize(name: str | None, cache_dir: Path | None = None) -> str:
    """Return a normalized identifier for drug ``name``.

    The result is the RxNorm ``rxcui`` when one is known (from cache, or fetched
    once on a miss), otherwise the lowercased, stripped name. An empty or
    ``None`` name returns ``""``. This function never raises for a network
    failure: an un-cached name simply falls back to its lowercased form.
    """
    if not name or not name.strip():
        return ""
    key = name.strip().lower()

    try:
        entry = cached("rxnorm", key, lambda: _fetch_rxcui(key), cache_dir)
    except Exception:
        # Network (or any fetch) failure on a cache miss: degrade to the name.
        return key

    rxcui = entry.get("rxcui") if isinstance(entry, dict) else None
    return str(rxcui) if rxcui else key
