# Implementation Plan: store-outputs

## Overview

Build the event-sourced Store, Outputs generators, scenario corpus, eval harness, and `SCRIBE_MODE` wiring in `backend/main.py`. Tasks are ordered so the Phase 1 stub keeps working throughout; only `backend/store/`, `backend/outputs/`, `scenarios/`, `eval/`, and `backend/main.py` are edited.

## Tasks

- [x] 1. Store
  - [x] 1.1 `backend/store/validate.py` — `validate_event(event)`: kind in allowed set, payload matches that kind's shape; errors name field + reason. _Requirements: 1.6_
  - [x] 1.2 `backend/store/persist.py` — `save(events, path)` atomic (tmp + `os.replace`), `load(path)->list[Event]`, corrupt file raises; default path `backend/store/event_log.json` (gitignored). _Requirements: 1.4, 1.5_
  - [x] 1.3 `backend/store/log.py` — `append(event)`: validate, reject duplicate id, persist, then append in memory (all-or-nothing); `events()` oldest-first. _Requirements: 1.1, 1.6_
  - [x] 1.4 `backend/store/derive.py` — `apply_event` + `derive` fold from `(PatientRecord(),[])`, no input mutation; conflict rules (empty->unverified; same value add source dedupe utterance_id+quote; different value keep old + add source + conflicted); meds_given/vitals_timeline append; flag status stability; relay/ack/field_confirmed set status. _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 1.5 `backend/store/facts.py` — `facts_from(utt, old, new)`: diff to fact events (unique ids, UTC ms ts), drop any fact whose quote is not a substring of `utt.text`. _Requirements: 1.2_
  - [x] 1.6 `backend/store/broadcast.py` — `publish(kind,data)` + async `subscribe()` over per-subscriber `asyncio.Queue`, drop on close. _Requirements: 1.7_
  - [x] 1.7 `backend/store/__init__.py` — wire public `append`/`events`/`derive`/`facts_from`/`subscribe` (keep Phase 1 signatures); replay `event_log.json` on startup. _Requirements: 1.1, 1.2, 1.5, 1.7_

- [x] 2. Outputs
  - [x] 2.1 `backend/outputs/sbar.py` — deterministic S/B/A/R from record + open flags; label unverified/conflicted; `""` when empty. _Requirements: 4.1, 4.4, 4.5, 4.6_
  - [x] 2.2 `backend/outputs/pre_alert.py` — short ED pre-alert from key fields + critical flags; `""` when empty. _Requirements: 4.1, 4.4, 4.5, 4.6_
  - [x] 2.3 `backend/outputs/checklist.py` — condition-keyed table (STEMI: defib, crash cart, 12-lead ECG, cath lab; stroke: CT slot, last-known-well); `[]` when nothing applies. _Requirements: 4.1, 4.2, 4.3, 4.6_
  - [x] 2.4 `backend/outputs/__init__.py` — re-export the three with Phase 1 signatures. _Requirements: 4.1_

- [x] 3. main.py SCRIBE_MODE
  - [x] 3.1 Add `SCRIBE_MODE=stub|live` (default stub); stub path unchanged so stub tests pass. _Requirements: 3.1, 3.2_
  - [x] 3.2 Live mode: GET record/flags/events from `store.derive(store.events())`; `POST /api/utterance` runs validate->append utterance->process_utterance->facts_from->append facts->evaluate->append flag_raised(new ids)->broadcast; failure before append -> 500 `processing`. _Requirements: 3.3, 3.4_
  - [x] 3.3 `POST /api/scenario/{id}/play` streams `scenarios/{id}.json` through the pipeline with `asyncio.sleep` delays; unknown id -> 404; stub mode keeps no-side-effect behavior. _Requirements: 3.5, 3.6_

- [ ] 4. Scenarios
  - [ ] 4.1 Author five transcripts + gold files (stemi_hero, clean_stemi, stroke, garbled_uncertain, opioid_overdose) and `scenarios/README.md` documenting the format; synthetic only. _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 5. Eval
  - [x] 5.1 `eval/run_scenarios.py` — play every scenario, score per-field accuracy + flag precision/recall vs gold, print table, write `eval/report.md`. _Requirements: 6.1, 6.2, 6.3_

- [x] 6. Tests
  - [x] 6.1 Fix `eval/tests/test_stub_smoke.py` SSE test to read exactly 3 events then close. _Requirements: 7.1, 7.2_
  - [x] 6.2 `backend/store/tests/test_roundtrip_property.py` — Hypothesis schema JSON round-trip. **Property 1: Schema JSON round-trip** _Requirements: 8.1_
  - [x] 6.3 `backend/store/tests/test_replay_property.py` — Hypothesis replay equals live. **Property 2: Replay equals live derivation** _Requirements: 8.2_
  - [x] 6.4 `backend/store/tests/test_flag_state_machine.py` — Hypothesis flag state machine (200/409/404 + stability). **Property 3: Flag state machine** _Requirements: 8.3, 2.5_

- [x] 7. Agent hook
  - [x] 7.1 Create a Kiro agent hook in `.kiro/hooks/` that triggers on save of `shared/schema.py` or `shared/types.ts` and runs the mock typecheck (`python eval/gen_mock_typecheck.py` then `tsc -p eval/tsconfig.mock.json`); hook watches `shared/` but lives in `.kiro/hooks/` and runs eval tooling only. _Requirements: 8, contract check_

- [ ] 8. Checkpoint
  - [ ] 8.1 Run pytest on `.venv311` (stub + live), `eval/run_scenarios.py`, and confirm `SCRIBE_MODE=live` hero scenario works end to end. Ensure all tests pass, ask the user if questions arise. _Requirements: 3.3, 6.1_

## Notes

- Tasks are ordered so the Phase 1 stub keeps working at every step (stub path untouched until live mode is wired behind `SCRIBE_MODE`).
- Property-test tasks (6.2–6.4) and the SSE fix (6.1) are required, not optional.
- Each task references specific requirements for traceability.
- Scope is limited to `backend/store/`, `backend/outputs/`, `scenarios/`, `eval/`, and `backend/main.py`; `shared/`, `backend/extraction/`, and `backend/safety/` are never edited.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "2.2", "2.3", "4.1", "7.1"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.6", "2.4"] },
    { "id": 2, "tasks": ["1.5", "1.7"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["5.1", "6.1", "6.2", "6.3", "6.4"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
