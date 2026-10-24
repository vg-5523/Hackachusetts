"""Warm the on-disk extraction cache from scenario scripts.

Usage (from the repo root):

    python -m backend.extraction.warm_cache stemi_hero clean_stemi

For each scenario id, reads ``scenarios/<id>.json`` and runs every utterance
through ``process_utterance`` in order, so the LLM response for each utterance
is written to ``backend/extraction/cache/`` for offline replay. A scenario file
that is missing or malformed is skipped with a clear message (the scenarios are
authored by another contributor and may not exist yet).

Scenario format: ``{"id": str, "utterances": [{"text": str, "ts": iso8601}]}``.
Warming requires ``LLM_API_KEY`` to be set (a cold cache needs a live model).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shared.schema import PatientRecord, Utterance

from . import process_utterance

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios"


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
    raw = data.get("utterances") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        print(f"[skip] {path} has no 'utterances' list.")
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


def warm_scenario(scenario_id: str) -> int:
    """Run every utterance in one scenario through the pipeline. Returns the
    number of utterances processed (0 when skipped)."""
    utterances = _load_scenario(scenario_id)
    if not utterances:
        return 0
    record = PatientRecord()
    for utt in utterances:
        record = process_utterance(utt, record)
        print(f"[warm] {scenario_id}: cached response for utterance '{utt.id}'.")
    print(f"[done] {scenario_id}: processed {len(utterances)} utterance(s).")
    return len(utterances)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m backend.extraction.warm_cache <scenario_id> [...]")
        return 2
    total = 0
    for scenario_id in argv:
        total += warm_scenario(scenario_id)
    print(f"[summary] warmed {total} utterance(s) across {len(argv)} scenario(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
