# Implementation Plan: Extraction

## Overview

Build the `backend/extraction/` pipeline in dependency order: prompt → cache →
parse → verify → apply → orchestration wiring, plus seed cache entries and a
pytest suite with a patched `call_llm`. All edits stay inside
`backend/extraction/` (and its `tests/` and `cache/`); `shared.schema` and
`backend.llm` are read-only imports.

## Tasks

- [ ] 1. Build the prompt
  - [ ] 1.1 Implement `build_prompt(utterance, record)` in `backend/extraction/prompt.py`
    - Request a single strict-JSON object `{"facts": [{path, value, quote, confidence, hedged}]}`; quote verbatim; relative times resolved against `utterance.ts` as offset-aware ISO 8601; list extractable paths
    - _Requirements: 1.1, 1.2, 4.3_

- [ ] 2. Parse and verify proposals
  - [ ] 2.1 Implement `parse_response(text) -> list[Proposal]` in `backend/extraction/parse.py`
    - Define internal `Proposal` dataclass; tolerant parse (strip fences, locate object, read `facts`); malformed → `[]`; drop entries missing keys or with `confidence` outside 0..1
    - _Requirements: 1.8_
  - [ ] 2.2 Implement `verify(proposals, utterance) -> list[Proposal]` in `backend/extraction/verify.py`
    - Keep a proposal only when `quote` is a case-sensitive substring of `utterance.text` and `path` is a known record path; drop the rest
    - _Requirements: 2.2, 2.3, 2.4_
  - [ ]* 2.3 Hypothesis property test for parse
    - **Property 4: Non-conforming output yields no facts** — Feature: extraction, Property 4
    - **Validates: Requirements 1.8**
  - [ ]* 2.4 Hypothesis property test for verify
    - **Property 5: Only verified substring quotes survive** — Feature: extraction, Property 5
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [ ] 3. Cache layer
  - [ ] 3.1 Implement `get_or_call(utterance, prompt) -> str` in `backend/extraction/cache.py`
    - `key = sha256(utterance.text).hexdigest()`; file `backend/extraction/cache/{key}.json` `{text, response}`; cache-first; corrupt/unreadable → miss; on miss call `llm.call_llm(prompt)`, write, return; let key `RuntimeError` propagate
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2_
  - [ ]* 3.2 Hypothesis property test for cache round-trip
    - **Property 10: Cache round-trip and reuse** — Feature: extraction, Property 10 (temp dir, patched `call_llm`)
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [ ] 4. Apply proposals
  - [ ] 4.1 Implement `apply_proposals(record, proposals, utterance) -> PatientRecord` in `backend/extraction/apply.py`
    - `model_copy(deep=True)`; build `SourceRef(utterance.id, quote, utterance.ts)`; map scalars/`allergies`/`meds_given`/`vitals_timeline`; `hedged` → `unverified` else `confirmed`; `acuity_esi` outside 1..5 skipped; differing value appends and keeps prior sources; never `conflicted`; cap sources at 20
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.5, 3.1, 3.2, 3.3, 4.1, 4.2, 7.2, 7.3_
  - [ ]* 4.2 Hypothesis property tests for apply
    - **Property 1: Provenance on every applied field** — Property 2: Untouched fields preserved — Property 3: acuity_esi stays 1..5 — Property 6: Input never mutated — Property 7: Differing values append, prior sources remain — Property 8: Status never conflicted — Property 9: Hedged facts unverified and no more confident. Feature: extraction, Properties 1,2,3,6,7,8,9
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 2.1, 2.5, 3.1, 3.2, 3.3, 4.1, 4.2**

- [ ] 5. Orchestration and seed cache
  - [ ] 5.1 Wire `process_utterance` in `backend/extraction/__init__.py`
    - `import from backend import llm`; keep Phase 1 signature; sequence `build_prompt` → `get_or_call` → `parse_response` → `verify` → `apply_proposals`; no try/except around `call_llm`; export public helpers
    - _Requirements: 1.1, 6.1, 6.2_
  - [ ] 5.2 Commit seed cache entries under `backend/extraction/cache/`
    - Add tracked `{text, response}` files for the no-allergies, penicillin, and aspirin sample utterances so demos replay offline
    - _Requirements: 5.1, 5.5_

- [ ] 6. Required example tests
  - [ ] 6.1 Add five pytest example tests in `backend/extraction/tests/` (patched `call_llm`, no network)
    - no-allergies-then-penicillin (two `allergies` values, each with source); aspirin-twice (two `meds_given`, each with source); no-key-no-cache raises `RuntimeError` naming `LLM_API_KEY`; quote-not-substring dropped; input-not-mutated
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 2.3, 2.4, 3.1, 6.1, 6.2_

- [ ] 7. Final checkpoint
  - Run `pytest backend/extraction` from the repo root. Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked `*` are optional property-based tests and can be skipped for a faster MVP.
- All edits are confined to `backend/extraction/`; `shared.schema` and `backend.llm` are read-only imports.
- Each task references its requirements; property tests cite their design Property number.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2", "3.1", "4.1"] },
    { "id": 1, "tasks": ["2.3", "2.4", "3.2", "4.2", "5.1"] },
    { "id": 2, "tasks": ["5.2"] },
    { "id": 3, "tasks": ["6.1"] }
  ]
}
```
