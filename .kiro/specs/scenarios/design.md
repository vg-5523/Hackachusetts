# Design: Demo scenarios (`scenarios/`)

## Overview

Each scenario is a pair of plain JSON files under `scenarios/`:

- `<id>.json` — the scripted transcript: a JSON array of `{text, ts}` utterances,
  exactly the `POST /api/utterance` body shape from `shared/api.md`.
- `<id>.gold.json` — the expected extraction and safety result, used as a fixture by
  eval/demo (read-only here; this spec only authors the files).

No code is added; these are data files plus a README and a one-line validation check.

## File shapes

Transcript:
```json
[
  { "text": "Dispatch, medic one responding...", "ts": "2024-02-01T14:00:00+00:00" }
]
```

Gold:
```json
{
  "fields": {
    "age":                 { "value": "58",    "status": "unverified" },
    "sex":                 { "value": "male",  "status": "unverified" },
    "chief_complaint":     { "value": "...",   "status": "confirmed" },
    "suspected_condition": { "value": "STEMI", "status": "confirmed" },
    "allergies":           { "value": ["penicillin"], "status": "conflicted" },
    "meds_given":          [ { "drug": "aspirin" }, { "drug": "aspirin" } ],
    "acuity_esi":          { "value": 1, "status": "confirmed" }
  },
  "flags": [ { "type": "contradiction", "severity": "critical" } ]
}
```

`status` values follow `shared/schema.py`: `confirmed`, `unverified`, `conflicted`,
`unknown`. Flag `type`/`severity` follow the safety engine.

## Scenario intent and expected flags

| id | Clinical picture | Meds given | Gold flags |
|---|---|---|---|
| stemi_hero | 58M chest pain; "no allergies" then penicillin bracelet | aspirin x2 (~10 min) | contradiction (critical), duplicate_dose (warn) |
| clean_stemi | STEMI, allergies stated once | aspirin x1 | none / missing_info if gaps |
| stroke | facial droop, slurred speech, LKW time | none | missing_info |
| garbled_uncertain | hedged/garbled speech | none clear | missing_info; fields unverified |
| opioid_overdose | unresponsive, naloxone reversal | naloxone x2 | duplicate_dose |

Rationale for the tricky ones:
- **stemi_hero** lists no `allergy_conflict` because aspirin is not a penicillin-class
  drug, so the penicillin allergy never conflicts with a given med.
- **opioid_overdose** gives only naloxone (the reversal agent), so the only
  interaction rules (`morphine+naloxone`, `fentanyl+naloxone`) do not fire — no opioid
  is administered by the crew. The sole flag is `duplicate_dose` for the two naloxone
  doses. This keeps the gold file honest: an `interaction` flag is listed only when a
  `rules.json` rule actually fires.

## Validation

A one-line Python check (run from the repo root, not committed as code) loads every
`scenarios/*.json`, asserts it parses, and for transcript files asserts each `ts` parses
via `datetime.fromisoformat` and carries a UTC offset (`tzinfo is not None`).
