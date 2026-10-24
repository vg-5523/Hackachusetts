# Tasks: Safety engine (`backend/safety/`)

Scope: edit only `backend/safety/` and its tests. `shared/` is read-only.

- [ ] 1. Verify RxNav interaction API state and RxNorm availability
  - Confirm the interaction endpoint is retired and the rxcui endpoint works.
  - _Requirements: R2.1, R6.1_

- [ ] 2. `ids.py` — `flag_id(type, rule_key, evidence)`
  - sha1 over type + rule_key + sorted joined evidence, 12 hex chars, `type:` prefix.
  - _Requirements: R5.1, R5.2_

- [ ] 3. `cache.py` — read-through JSON cache under `cache/`
  - `cached(kind, key, fetch)`: hit returns stored JSON, no `fetch`; miss writes result.
  - _Requirements: R6.2, R6.3_

- [ ] 4. `normalize.py` — RxNorm normalization via cache
  - `normalize(name)` returns an rxcui (or lowercased name fallback); offline-safe.
  - _Requirements: R6.1, R6.3_

- [ ] 5. `rules.json` + `config.py`
  - Curated classes, citations, interaction rules; duplicate window + required fields.
  - _Requirements: R2.2, R2.3, R3.1, R3.5_

- [ ] 6. `rules_meds.py` — duplicate_dose, allergy_conflict, interaction
  - Pure hit builders with evidence quotes and citations.
  - _Requirements: R3.1, R3.2, R3.3, R4.1_

- [ ] 7. `rules_record.py` — contradiction, missing_info
  - One hit per conflicted field (critical) / per unknown required field (info).
  - _Requirements: R3.4, R3.5, R4.1_

- [ ] 8. `phrasing.py` — say_to_crew with template fallback
  - LLM phrases only; any failure → per-type template; ≤ 280 non-blank chars.
  - _Requirements: R1.2, R1.3, R4.1_

- [ ] 9. Wire `evaluate` in `__init__.py`
  - Run rules, build validated `Flag`s with `flag_id` + phrasing, stable order.
  - _Requirements: R1.1, R4.2, R5.2_

- [ ] 10. Pre-warm and commit the cache for all 11 demo drugs
  - _Requirements: R6.3_

- [ ] 11. Tests in `backend/safety/tests/`
  - ids, cache, and hero-case evaluate (offline, template fallback).
  - _Requirements: R5.2, R6.3, R7.1_
