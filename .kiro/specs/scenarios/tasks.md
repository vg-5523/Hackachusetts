# Tasks: Demo scenarios (`scenarios/`)

Scope: edit only `scenarios/` and `.kiro/specs/scenarios/`.

- [ ] 1. Author `stemi_hero.json` + `stemi_hero.gold.json`
  - 58M chest pain; "no known allergies" then penicillin bracelet; aspirin twice ~10 min
    apart (second phrased differently); vitals at 2+ times; onset and ETA.
  - Gold flags: contradiction (critical), duplicate_dose (warn).
  - _Requirements: R2.1, R3.1, R3.2_

- [ ] 2. Author `clean_stemi.json` + `clean_stemi.gold.json`
  - STEMI; allergies stated once, no contradiction; one aspirin dose.
  - Gold flags: none except missing_info for any unknown (e.g. weight).
  - _Requirements: R2.2, R3.2_

- [ ] 3. Author `stroke.json` + `stroke.gold.json`
  - Facial droop, slurred speech, last-known-well; no blood thinners.
  - Gold flags: missing_info only.
  - _Requirements: R2.3, R3.2_

- [ ] 4. Author `garbled_uncertain.json` + `garbled_uncertain.gold.json`
  - Hedged/garbled speech; uncertain fields status unverified.
  - Gold flags: missing_info only.
  - _Requirements: R2.4, R3.2_

- [ ] 5. Author `opioid_overdose.json` + `opioid_overdose.gold.json`
  - Unresponsive; naloxone given twice; no opioid administered by crew.
  - Gold flags: duplicate_dose (no interaction rule fires).
  - _Requirements: R2.5, R3.2_

- [ ] 6. Write `scenarios/README.md`
  - List each file and what it demonstrates.
  - _Requirements: R4.2_

- [ ] 7. Validate all JSON parses and every ts is ISO 8601 with a UTC offset
  - One-line Python check from the repo root.
  - _Requirements: R1.2, R4.3_
