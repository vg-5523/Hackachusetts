"""Warm the on-disk extraction cache from scenario scripts.

Usage (from the repo root):

    python -m backend.extraction.warm_cache stemi_hero clean_stemi

For each scenario id, reads ``scenarios/<id>.json`` and runs every utterance
through the extraction pipeline in order, so each utterance's LLM response is
written to ``backend/extraction/cache/`` for offline replay. For every scenario
it prints the number of utterances processed and how many proposed facts were
dropped for failing the quote-substring check (proposals whose quote is not a
verbatim substring of the utterance text).

Scenario files may be either a bare JSON array of ``{"text", "ts"}`` objects or
an object ``{"utterances": [...]}``. A missing or malformed file is skipped with
a clear message. Warming a cold cache requires ``LLM_API_KEY`` to be set; with
no key and no cache entry the deterministic rules extractor is used instead.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from shared.schema import PatientRecord, Utterance

from . import (
    _llm_key_set,
    apply_proposals,
    build_prompt,
    parse_response,
    read_cache,
    rules_extract,
    verify,
    write_cache,
)
from backend import llm

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios"
# Pause between live LLM calls so the free tier does not rate-limit us.
# Free-tier flash models allow only a few requests per minute; a short
# pause bursts past that, so default to 6s (overridable via WARM_PAUSE_S).
import os as _os
_PACING_PAUSE_S = float(_os.environ.get("WARM_PAUSE_S", "6"))


def _load_scenario(scenario_id: str) -> list[Utterance] | None:
    """Return the utterances for ``scenario_id``, or ``None`` if unavailable."""
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        print(f"[skip] {path} does not exist; nothing to warm for '{scenario_id}'.")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[skip] could not read {path}: {exc}")
        return None

    # Accept a bare array or an object with an "utterances" list.
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict) and isinstance(data.get("utterances"), list):
        raw = data["utterances"]
    else:
        print(f"[skip] {path}: unrecognized scenario shape.")
        return None

    utterances: list[Utterance] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            utterances.append(
                Utterance(
                    id=item.get("id", f"{scenario_id}-{i}"),
                    text=item["text"],
                    ts=item["ts"],
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            print(f"[warn] {path} utterance {i} skipped: {exc}")
    return utterances


def _resolve_response(utterance: Utterance) -> tuple[str | None, bool]:
    """Return ``(response, called_llm)`` for ``utterance`` (cache then LLM).

    Returns ``None`` when there is no cache hit and no key, signalling the
    caller to use the rules fallback.
    """
    response = read_cache(utterance)
    if response is not None:
        return response, False
    if _llm_key_set():
        prompt = build_prompt(utterance, PatientRecord())
        response = llm.call_llm(prompt)
        write_cache(utterance, response)
        return response, True
    return None, False


def warm_scenario(scenario_id: str) -> tuple[int, int]:
    """Warm one scenario. Returns (utterances_processed, facts_dropped)."""
    utterances = _load_scenario(scenario_id)
    if not utterances:
        print(f"[done] {scenario_id}: 0 utterances, 0 facts dropped.")
        return (0, 0)

    record = PatientRecord()
    dropped = 0
    used_rules = False

    for utt in utterances:
        response, called_llm = _resolve_response(utt)
        if called_llm:
            # Pace live calls so the free tier does not rate-limit us.
            time.sleep(_PACING_PAUSE_S)
        if response is not None:
            proposals = parse_response(response)
            if not proposals:
                # Thin/empty response: fall through to the rules extractor.
                proposals = rules_extract(utt)
                used_rules = True
        else:
            proposals = rules_extract(utt)
            used_rules = True

        kept = verify(proposals, utt)
        dropped += len(proposals) - len(kept)
        record = apply_proposals(record, kept, utt)

    source = "rules fallback" if used_rules else "cache/LLM"
    print(
        f"[done] {scenario_id}: processed {len(utterances)} utterance(s), "
        f"dropped {dropped} fact(s) failing the quote-substring check "
        f"(source: {source})."
    )
    return (len(utterances), dropped)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m backend.extraction.warm_cache <scenario_id> [...]")
        return 2

    total_utts = 0
    total_dropped = 0
    print("scenario,utterances,dropped_facts")
    for scenario_id in argv:
        utts, dropped = warm_scenario(scenario_id)
        print(f"{scenario_id},{utts},{dropped}")
        total_utts += utts
        total_dropped += dropped

    print(
        f"[summary] {total_utts} utterance(s) across {len(argv)} scenario(s); "
        f"{total_dropped} fact(s) dropped for failing the quote-substring check."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
