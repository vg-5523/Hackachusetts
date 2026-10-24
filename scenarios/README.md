# scenarios

Owner: Account D. Synthetic-data-only scripted paramedic transcripts that drive the
demo and replays. Every file here is fabricated: no real names, institutions, phone
numbers, or addresses.

## Format

Each `<id>.json` is a JSON array of utterances, one per line of radio traffic, matching
the `POST /api/utterance` body in `shared/api.md`:

```json
[ { "text": "radio-style speech", "ts": "2024-02-01T14:00:00+00:00" } ]
```

`ts` is ISO 8601 with a UTC offset and strictly increases within a file. Each transcript
has 6 to 12 utterances. Any administered drug is one of the drugs in
`backend/safety/rules.json` (aspirin, nitroglycerin, sildenafil, morphine, fentanyl,
naloxone).

Each scenario also ships `<id>.gold.json`, the expected result used as a fixture:

- `fields`: expected `value` and `status` for `age`, `sex`, `chief_complaint`,
  `suspected_condition`, `allergies`, `meds_given`, and `acuity_esi`.
- `flags`: the expected safety flags, each as `type` and `severity` only.

## Scenarios

| File | Demonstrates |
|---|---|
| `stemi_hero.json` | 58M chest pain STEMI. Allergy history contradicts itself ("no known allergies", then a penicillin bracelet) and aspirin is given twice ~10 min apart with the second dose phrased differently. Exercises `contradiction` and `duplicate_dose`. No `allergy_conflict`: aspirin is not a penicillin-class drug. |
| `clean_stemi.json` | A clean STEMI. Allergies stated once and never contradicted, a single aspirin dose. No safety flags. |
| `stroke.json` | Suspected acute stroke: facial droop, slurred speech, last-known-well time, no blood thinners and no allergy list. No meds given. Exercises `missing_info` (unknown allergies). |
| `garbled_uncertain.json` | Hedged and garbled radio traffic ("uh", "maybe", "I think", "couldn't hear") so extracted fields land as `unverified` rather than `confirmed`. Exercises `missing_info`. |
| `opioid_overdose.json` | Unresponsive patient with respiratory depression; naloxone given twice. Exercises `duplicate_dose`. No `interaction` flag: only naloxone is given, so the opioid+naloxone rules do not fire. |

## Validate

From the repo root, confirm every file parses and every transcript `ts` is ISO 8601 with
a UTC offset:

```bash
python - <<'PY'
import glob, json
from datetime import datetime

for path in sorted(glob.glob("scenarios/*.json")):
    data = json.load(open(path))
    if path.endswith(".gold.json"):
        continue
    for utt in data:
        ts = datetime.fromisoformat(utt["ts"])
        assert ts.tzinfo is not None, f"{path}: ts missing UTC offset: {utt['ts']}"
print("OK")
PY
```
