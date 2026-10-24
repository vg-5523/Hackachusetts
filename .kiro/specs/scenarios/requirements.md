# Requirements: Demo scenarios (`scenarios/`)

## Introduction

`scenarios/` (Account D) holds synthetic, scripted paramedic transcripts that drive
the demo and replays. Each scenario is a JSON list of `{text, ts}` utterances matching
the `POST /api/utterance` body in `shared/api.md`, paired with a `<id>.gold.json` of the
expected extracted fields and safety flags. Scope is limited to `scenarios/` and this
spec; `shared/`, `backend/`, and `eval/` are read-only.

Drugs mentioned as administered must appear in `backend/safety/rules.json`
(aspirin, nitroglycerin, sildenafil, morphine, fentanyl, naloxone; penicillin and
amoxicillin only as allergy classes). Data is synthetic only.

## Requirements

### R1 Transcript format
- 1.1 Each scenario file is a JSON array of `{text, ts}` objects.
- 1.2 `text` is radio-style paramedic speech, 1 to 2000 chars; `ts` is ISO 8601 with a
  UTC offset, strictly increasing within a file.
- 1.3 Each file has 6 to 12 utterances.

### R2 Five scenarios
- 2.1 `stemi_hero.json`: 58yo male, chest pain; "no known allergies" early, "penicillin
  allergy bracelet" later; aspirin given twice ~10 min apart, the second phrased
  differently; vitals at two or more times (HR, BP, SpO2, RR); chest pain onset and ETA.
- 2.2 `clean_stemi.json`: STEMI; allergies stated once, never contradicted; one aspirin
  dose; no conflicts.
- 2.3 `stroke.json`: facial droop, slurred speech, last-known-well time; no blood thinners.
- 2.4 `garbled_uncertain.json`: hedged/garbled speech so fields are unverified.
- 2.5 `opioid_overdose.json`: unresponsive patient; naloxone given twice.

### R3 Gold files
- 3.1 Each scenario has `<id>.gold.json` with `fields` (age, sex, chief_complaint,
  suspected_condition, allergies, meds_given, acuity_esi — value and status) and `flags`
  (each `type` and `severity` only).
- 3.2 Expected flags:
  - stemi_hero: `contradiction` (critical) + `duplicate_dose` (warn/critical); no
    `allergy_conflict` (no penicillin-class drug given).
  - clean_stemi: none except `missing_info` if allergies/weight unknown.
  - stroke: `missing_info` only.
  - garbled_uncertain: `missing_info` only; uncertain fields `unverified`.
  - opioid_overdose: `duplicate_dose`; an `interaction` flag only if a `rules.json` rule fires.

### R4 Constraints and validation
- 4.1 Only drugs in `rules.json`; synthetic data only (no real names, institutions,
  phone numbers, or addresses).
- 4.2 `scenarios/README.md` lists each file and what it demonstrates.
- 4.3 Every JSON file parses and every `ts` is valid ISO 8601 with a UTC offset.
