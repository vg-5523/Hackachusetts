"""Evaluate the deterministic rules extractor against scenario gold files (item 5).

Scenario files (``scenarios/<id>.json``) are bare JSON arrays of ``{text, ts}``.
Gold files (``scenarios/<id>.gold.json``) hold a ``fields`` object describing the
expected final record. This test runs ``rules_extract`` over every utterance in
order, folds the surviving proposals into a record, and compares that record's
field VALUES against the gold values (status is set by the store/safety layers,
not by extraction, so status is reported but not asserted). It SKIPS cleanly
when a scenario or gold file is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.extraction import apply_proposals, rules_extract, verify
from shared.schema import PatientRecord, Utterance

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scenarios"
SCENARIO_IDS = ["stemi_hero", "clean_stemi"]


def _load_pair(scenario_id: str):
    scen = SCENARIOS_DIR / f"{scenario_id}.json"
    gold = SCENARIOS_DIR / f"{scenario_id}.gold.json"
    if not scen.exists() or not gold.exists():
        pytest.skip(f"{scenario_id}: scenario or gold file not present yet")
    data = json.loads(scen.read_text(encoding="utf-8"))
    utterances = data if isinstance(data, list) else data.get("utterances", [])
    fields = json.loads(gold.read_text(encoding="utf-8")).get("fields", {})
    return utterances, fields


def _norm(x):
    return str(x).strip().lower() if x is not None else None


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_rules_extract_against_gold(scenario_id):
    utterances, gold = _load_pair(scenario_id)
    assert utterances, f"{scenario_id}: no utterances found"

    record = PatientRecord()
    for i, item in enumerate(utterances):
        utt = Utterance(
            id=item.get("id", f"{scenario_id}-{i}") if isinstance(item, dict) else f"{scenario_id}-{i}",
            text=item["text"],
            ts=item["ts"],
        )
        proposals = rules_extract(utt)
        # Every rules quote must be a genuine substring of the utterance.
        for p in proposals:
            assert p.quote in utt.text, f"{scenario_id} {utt.id}: bad quote {p.quote!r}"
        record = apply_proposals(record, verify(proposals, utt), utt)

    correct, wrong = [], []

    def check(name, got_value, gold_value):
        if _norm(got_value) == _norm(gold_value):
            correct.append(f"{name}={got_value!r}")
        else:
            wrong.append(f"{name}: gold={gold_value!r} got={got_value!r}")

    for scalar in ("age", "sex", "chief_complaint", "suspected_condition", "acuity_esi"):
        if scalar in gold:
            check(scalar, getattr(record, scalar).value, gold[scalar]["value"])

    if "allergies" in gold:
        got = sorted(_norm(x) for x in (record.allergies.value or []))
        want = sorted(_norm(x) for x in (gold["allergies"].get("value") or []))
        (correct if got == want else wrong).append(
            f"allergies: gold={want} got={got}"
        )

    if "meds_given" in gold:
        got = sorted(_norm(m.value.drug) for m in record.meds_given)
        want = sorted(_norm(m.get("drug")) for m in gold["meds_given"])
        (correct if got == want else wrong).append(
            f"meds_given: gold={want} got={got}"
        )

    print(f"\n=== {scenario_id}: rules_extract vs gold ===")
    print("CORRECT:")
    for c in correct:
        print(f"  + {c}")
    print("WRONG/MISSING:")
    for w in wrong:
        print(f"  - {w}")

    # Smoke-level bar: the deterministic extractor must recover at least one
    # gold field value from the scenario.
    assert correct, f"{scenario_id}: rules_extract recovered no gold field values"
