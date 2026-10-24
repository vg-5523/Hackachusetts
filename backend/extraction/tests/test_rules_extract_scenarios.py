"""Evaluate the deterministic rules extractor against scenario gold files (item 5).

For each scenario in ``scenarios/<id>.json``, run ``rules_extract`` on every
utterance and compare the extracted facts against the scenario's gold
expectations. The test SKIPS cleanly when the scenario file is absent (the
scenarios are owned by another contributor and may not exist yet).

Expected scenario format (superset of the utterance format):

    {
      "id": "stemi_hero",
      "utterances": [
        {"id": "u1", "text": "...", "ts": "...",
         "gold": [{"path": "age", "value": "54"}, ...]}
      ]
    }

``gold`` is optional per utterance. When no utterance carries a ``gold`` list,
the test still runs and reports what rules_extract found (informational), so it
is useful even before gold labels are added.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.extraction.rules_extract import rules_extract
from shared.schema import Utterance

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scenarios"
SCENARIO_IDS = ["stemi_hero", "clean_stemi"]


def _load(scenario_id: str):
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        pytest.skip(f"{path} not present yet (owned by another contributor)")
    data = json.loads(path.read_text(encoding="utf-8"))
    utterances = data.get("utterances", []) if isinstance(data, dict) else []
    return utterances


def _paths_values(proposals):
    """Return a set of (path, normalized-value) pairs for comparison."""
    out = set()
    for p in proposals:
        value = p.value
        if isinstance(value, dict):
            value = value.get("drug", json.dumps(value, sort_keys=True))
        out.add((p.path, str(value).lower()))
    return out


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_rules_extract_against_gold(scenario_id, capsys):
    utterances = _load(scenario_id)
    assert utterances, f"{scenario_id}: no utterances found"

    total_expected = 0
    total_hit = 0
    report_lines = [f"=== {scenario_id} ==="]

    for i, item in enumerate(utterances):
        utt = Utterance(
            id=item.get("id", f"{scenario_id}-{i}"),
            text=item["text"],
            ts=item["ts"],
        )
        proposals = rules_extract(utt)
        got = _paths_values(proposals)

        # Every quote must be a genuine substring of the utterance text.
        for p in proposals:
            assert p.quote in utt.text, (
                f"{scenario_id} {utt.id}: quote {p.quote!r} not in utterance"
            )

        gold = item.get("gold")
        if gold is None:
            report_lines.append(
                f"[info] {utt.id}: extracted {sorted(got)} (no gold labels)"
            )
            continue

        expected = {(g["path"], str(g["value"]).lower()) for g in gold}
        hit = expected & got
        missed = expected - got
        extra = got - expected
        total_expected += len(expected)
        total_hit += len(hit)
        report_lines.append(
            f"{utt.id}: correct={sorted(hit)} missed={sorted(missed)} "
            f"spurious={sorted(extra)}"
        )

    if total_expected:
        report_lines.append(
            f"[score] {scenario_id}: {total_hit}/{total_expected} gold facts recovered"
        )
    print("\n".join(report_lines))

    # The report is always emitted; when gold labels exist, require that the
    # extractor recovers at least one of them (a smoke-level quality bar).
    if total_expected:
        assert total_hit > 0, f"{scenario_id}: rules_extract recovered no gold facts"
