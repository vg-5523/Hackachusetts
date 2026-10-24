# Implementation Plan: Ambulance Scribe Contract

## Overview

Phase 1 builds the shared contract and stubs that everyone codes against, then commits and pushes it. Phase 2 splits into four owner groups that each touch only their own folder and run against the Phase 1 stub and mocks. Phase 3 wires the real pipeline in `backend/main.py`, runs the STEMI hero scenario end to end, runs eval, and polishes the demo. Backend code is Python 3.11 (FastAPI, Pydantic v2, pytest, Hypothesis); frontend code is TypeScript (React, Vite, Tailwind, vitest).

## Tasks

### Phase 1: Contract foundation (all blocking; push before Phase 2 starts)

- [x] 1. [BLOCKING] Repository skeleton and steering files
  - [x] 1.1 [BLOCKING] Create the backend, shared, scenarios, and eval skeleton
    - Create `backend/` with packages `extraction/`, `safety/`, `store/`, `outputs/`, each with an empty `__init__.py`; add `__init__.py` files where needed so `backend.*` and `shared.schema` import from the repo root
    - Create `backend/requirements.txt` pinning fastapi, uvicorn, pydantic, pytest, hypothesis, and httpx with `==` only
    - Create root `pytest.ini` with `pythonpath = .`, `testpaths = eval backend`, and `--import-mode=importlib`
    - Create placeholder `scenarios/README.md` and `eval/README.md`
    - _Requirements: 2.1, 2.2, 2.8_
  - [x] 1.2 [BLOCKING] Add `.gitignore` and `.env.example`
    - `.gitignore` excludes virtual environment folders, `node_modules`, frontend build output, `.env` and `.env.*` (keeping `!.env.example`), and `backend/store/event_log.json`
    - `.env.example` contains `LLM_API_KEY=` and no other secret values
    - _Requirements: 2.6, 2.7, 14.2_
  - [x] 1.3 [BLOCKING] Scaffold the Vite + React + TypeScript + Tailwind frontend
    - `frontend/package.json` with exact pinned versions (no `^` or `~`), including `typescript`; Vite dev server on port 5173
    - Minimal `src/App.tsx` that shows "decision support, not clinical advice." without scrolling
    - _Requirements: 2.3, 2.4, 11.5_
  - [x] 1.4 [BLOCKING] Write `.kiro/steering/product.md`
    - One heading each for purpose (1 to 3 sentences), provenance on every field, the AI never talks to paramedics, `say_to_crew` relayed by a human operator, synthetic data only, and the disclaimer with the exact text "decision support, not clinical advice"
    - At most 200 lines
    - _Requirements: 1.1, 1.2, 1.3, 1.10, 11.6, 15.2_
  - [x] 1.5 [BLOCKING] Write `.kiro/steering/tech.md`
    - Name Python 3.11, FastAPI, Pydantic, React, Vite, TypeScript, Tailwind, Server-Sent Events, the in-memory event-sourced store, `LLM_API_KEY`, the `call_llm` wrapper in `backend/llm.py`, and the Web Speech API with typed-input fallback
    - _Requirements: 1.1, 1.4, 1.10_
  - [x] 1.6 [BLOCKING] Write `.kiro/steering/structure.md`
    - List `shared`, `backend/extraction`, `backend/safety`, `backend/store`, `backend/outputs`, `frontend`, `scenarios`, `eval`, and `.kiro`, each with a 1 to 2 sentence purpose and exactly one owner
    - State the owner-folder edit rule and that shared contract changes need agreement from all contributors; reference only skeleton paths
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

- [x] 2. [BLOCKING] Shared schema, TypeScript types, and API spec
  - [x] 2.1 [BLOCKING] Define enums, `SourceRef`, `Citation`, and `Sourced[T]` in `shared/schema.py`
    - Pydantic v2 with `extra="forbid"`; `FieldStatus`, `FlagType`, `FlagSeverity`, `FlagStatus` as `str, Enum`
    - `SourceRef` (`utterance_id` 1 to 128, `quote` 1 to 1000, offset-aware `ts`); `Citation` (`name` 1 to 200, http(s) `url` up to 2048)
    - `Sourced[T]`: `value` T or None, `status` default `unknown`, finite `confidence` 0 to 1 default 0, `sources` up to 20
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 5.2_
  - [x] 2.2 [BLOCKING] Add `Medication`, `VitalsEntry`, and `PatientRecord` to `shared/schema.py`
    - Field types and ranges from the design table, `bp` pattern `^\d{2,3}/\d{2,3}$`, list limits of 100, `notes` up to 5000, `acuity_esi` integer 1 to 5
    - `PatientRecord()` with no arguments is valid and empty; `allergies` defaults to an `unknown` Sourced whose value is `[]` (Req 4.7)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.10, 4.11, 4.12_
  - [x] 2.3 [BLOCKING] Add `Flag`, `ErrorBody`, `Utterance`, `UtteranceRequest`, `Event`, `ClockEntry`, and `Clocks` to `shared/schema.py`
    - `Flag`: limits from the design table, `say_to_crew` 1 to 280 and non-blank, `source_ref: Citation`, `status` default `open`
    - `ErrorBody` (`category`, optional `field`, `detail`); `Utterance` (`id`, `text` 1 to 2000, `ts`); `UtteranceRequest` (`text`, `ts`)
    - `Event`: `id` 1 to 128, UTC `ts` serialized with millisecond precision, `kind` 1 to 64, `payload` object up to 64 KB serialized
    - `ClockEntry` (`med_id`, `last_dose_ts`, `elapsed_s` >= 0) and `Clocks` (`contact_ts`, `eta`, `door_to_ecg_target_ts`, `meds`)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 7.1, 7.8, 11.1, 11.2_
  - [ ]* 2.4 [BLOCKING] Write property test for schema round trip in `eval/tests/test_schema_roundtrip.py`
    - **Property 1: Schema round trip**
    - **Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.9, 5.1, 5.2, 5.7, 6.1, 6.6**
  - [ ]* 2.5 [BLOCKING] Write property test for whole-input rejection in `eval/tests/test_schema_rejects.py`
    - **Property 2: Invalid input rejected whole**
    - **Validates: Requirements 3.4, 3.5, 3.7, 4.10, 4.11, 4.12, 5.4, 5.5, 11.1, 11.2**
  - [x] 2.6 [BLOCKING] Write `shared/types.ts` by hand to mirror `shared/schema.py`
    - One export per model and enum with identical names, field names, enum values, and nullability; no extra exports; `Sourced<T>` generic
    - _Requirements: 3.6, 4.8, 5.6, 6.2, 12.1, 12.2, 12.4_
  - [x] 2.7 [BLOCKING] Write `shared/api.md`
    - For every endpoint in the design table: method, path, request body, success shape by schema model, and errors (422 `validation`, 404 `not_found`, 409 `conflict`, 500 `processing` or `response_validation`)
    - SSE `record`, `flags`, `clocks` payloads, 1 s cadence, and change latency; the meaning and derivation of each `Clocks` field
    - Event kinds and payload fields: `utterance`, `fact`, `flag_raised`, `flag_relayed`, `flag_acked`, `field_confirmed`
    - `{path}` syntax with examples `age` and `meds_given.0`; idempotent repeats; failed requests change nothing; the flag state machine; no endpoint delivers anything to crew devices
    - _Requirements: 6.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 11.3, 11.4, 11.7_

- [x] 3. [BLOCKING] Mock data and contract checks
  - [x] 3.1 [BLOCKING] Write `shared/mock_record.json`
    - Shape `{"record": PatientRecord, "flags": [Flag, Flag, Flag]}` with a synthetic STEMI run: "no allergies" then a penicillin bracelet (`allergies` is `conflicted`), aspirin given twice
    - At least one Sourced field per status (`confirmed`, `unverified`, `conflicted`, `unknown`); 2 to 10 vitals and 2 to 10 medications; non-empty values except `unknown` fields, which may be null
    - Three flags across at least three types and two severities; `say_to_crew` up to 200 characters; 0 to 5 evidence quotes up to 300 characters; `source_ref.url` on `example.com`, `example.org`, or `example.net`
    - No real names, identifiers, contact details, or dates of birth
    - _Requirements: 2.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8, 8.9, 15.1, 15.3_
  - [x] 3.2 [BLOCKING] Write `eval/validate_mock.py`
    - Load the mock through `PatientRecord` and `Flag`; print `OK` and exit 0, or print each validation error and exit non-zero
    - _Requirements: 8.7, 13.7_
  - [x] 3.3 [BLOCKING] Add the `tsc --noEmit` mock type check
    - `eval/gen_mock_typecheck.py` writes `eval/mock_typecheck.ts`, which assigns the mock to `PatientRecord` and `Flag[]` as typed literals (JSON imports widen string literals, so embed the JSON rather than importing it)
    - `eval/tsconfig.mock.json` (strict, `noEmit`) covering only that file; run with the TypeScript installed in `frontend/`
    - _Requirements: 12.3, 13.7_

- [x] 4. [BLOCKING] FastAPI stub server serving mocks
  - [x] 4.1 [BLOCKING] Create the app shell in `backend/main.py`
    - FastAPI app runnable as `uvicorn backend.main:app --port 8000` from the repo root
    - CORS allows exactly `http://localhost:5173` and `http://127.0.0.1:5173`
    - Load an in-memory deep copy of the mock at startup; no LLM calls anywhere in the stub
    - Helpers that return `ErrorBody` with the right status and validate every response body against its schema model (500 `response_validation` on failure)
    - _Requirements: 9.11, 9.12, 9.13, 9.14_
  - [x] 4.2 [BLOCKING] Add the GET endpoints to `backend/main.py`
    - `/api/record`, `/api/flags`, `/api/sbar`, `/api/preAlert`, `/api/checklist`, and `/api/events`, all populated from the mock
    - `/api/events` returns Events synthesized from the mock (for example one `utterance` per distinct source utterance and one `flag_raised` per flag), oldest first
    - _Requirements: 7.3, 7.5, 7.10, 9.1, 9.2_
  - [x] 4.3 [BLOCKING] Add `POST /api/utterance` and the scenario endpoints to `backend/main.py`
    - Utterance: validate `UtteranceRequest` (422 naming the field) and return the mock record unchanged
    - `GET /api/scenarios` returns a fixed id list (`["stemi_hero"]`); `POST /api/scenario/{id}/play` returns the mock record for a known id and 404 otherwise; no side effects
    - _Requirements: 7.1, 7.13, 7.14, 9.4, 9.5, 9.16, 9.17, 9.18_
  - [x] 4.4 [BLOCKING] Add relay, ack, and confirm endpoints to `backend/main.py`
    - Relay moves `open` or `relayed` to `relayed`; ack moves `relayed` or `acknowledged` to `acknowledged`; invalid transitions return 409; unknown flags return 404; failures leave flags unchanged
    - Confirm resolves `{path}` to a Sourced field, sets `confirmed`, and returns it; an unresolved path returns 404 with the record unchanged
    - _Requirements: 7.4, 7.9, 7.12, 9.6, 9.7, 9.8, 9.9, 9.10, 9.15, 11.3, 11.7_
  - [x] 4.5 [BLOCKING] Add `GET /api/stream` SSE to `backend/main.py`
    - On connect send `record`, `flags`, then `clocks` within 1 s; then `clocks` every 1 s until disconnect
    - Build `Clocks` from the mock per `shared/api.md`, with one `ClockEntry` per `meds_given.N`
    - _Requirements: 7.2, 7.7, 7.8, 9.3_
  - [x] 4.6 [BLOCKING] Write a stub smoke test in `eval/tests/test_stub_smoke.py`
    - With FastAPI `TestClient`, call every endpoint in `shared/api.md` once and assert status and a schema-valid body; later checkpoints rely on this test
    - _Requirements: 9.1, 9.2_
  - [ ]* 4.7 [BLOCKING] Write property test for the flag state machine in `eval/tests/test_stub_flag_states.py`
    - **Property 7: Flag state machine**
    - **Validates: Requirements 7.12, 9.6, 9.7, 9.8, 9.15, 11.3, 11.7**
  - [ ]* 4.8 [BLOCKING] Write property test for endpoint input validation in `eval/tests/test_stub_inputs.py`
    - **Property 8: Endpoint input validation**
    - **Validates: Requirements 7.9, 9.5, 9.9, 9.10**
  - [ ]* 4.9 [BLOCKING] Write stub behaviour tests in `eval/tests/test_stub_behaviour.py`
    - SSE order and 1 s cadence, CORS allowed and rejected origins (including preflight), a forced response-validation 500, and startup and requests with `LLM_API_KEY` unset
    - _Requirements: 9.3, 9.11, 9.13, 9.14_

- [x] 5. [BLOCKING] Module interface stubs
  - [x] 5.1 [BLOCKING] Write `call_llm(prompt: str) -> str` in `backend/llm.py`
    - Read `LLM_API_KEY` at call time; if unset or empty, raise `RuntimeError("LLM_API_KEY not set")` before any network work
    - With a key, send the prompt to the team's LLM provider and return the text; this is the only LLM call site
    - _Requirements: 10.6, 10.10, 10.12_
  - [x] 5.2 [BLOCKING] Stub `process_utterance` in `backend/extraction/__init__.py`
    - `process_utterance(utterance: Utterance, record: PatientRecord) -> PatientRecord`, models imported from `shared.schema`; returns the received record unchanged
    - _Requirements: 10.1, 10.7, 10.11, 10.14_
  - [x] 5.3 [BLOCKING] Stub `evaluate` in `backend/safety/__init__.py`
    - `evaluate(record: PatientRecord) -> list[Flag]` returns `[]`
    - _Requirements: 10.2, 10.8, 10.11, 10.14_
  - [x] 5.4 [BLOCKING] Stub `make_sbar`, `make_pre_alert`, and `make_checklist` in `backend/outputs/__init__.py`
    - Non-empty placeholder strings for SBAR and pre-alert; `["Prepare bed"]` for the checklist
    - _Requirements: 10.3, 10.4, 10.5, 10.9, 10.11, 10.13, 10.14_
  - [x] 5.5 [BLOCKING] Stub `append`, `events`, `derive`, `facts_from`, and `subscribe` in `backend/store/__init__.py`
    - Signatures exactly as in the design; minimal bodies (in-memory append, oldest-first copy, `(PatientRecord(), [])`, `[]`, and an async iterator that yields nothing)
    - _Design: Components and Interfaces (store)_
  - [ ]* 5.6 [BLOCKING] Write unit tests for the module stubs and `call_llm` in `eval/tests/test_module_stubs.py`
    - Stub return values, imports with `LLM_API_KEY` unset, `call_llm` raising with `LLM_API_KEY` in the message and no network call, key read at call time
    - _Requirements: 10.7, 10.8, 10.9, 10.10, 10.12, 10.13, 10.14_

- [ ] 6. [BLOCKING] README
  - [x] 6.1 [BLOCKING] Rewrite `README.md` with run instructions
    - First section: the product in up to 5 sentences, "decision support, not clinical advice.", and a synthetic-data-only statement
    - Runtime versions (Python 3.11 and the Node toolchain) before the first install; fenced commands in order for venv create, activate (PowerShell and POSIX), `pip install -r backend/requirements.txt`, `uvicorn backend.main:app --port 8000`, `npm install`, and `npm run dev`
    - Local URLs `http://localhost:8000` and `http://localhost:5173`; `LLM_API_KEY` purpose and that the stub starts without it; copy `.env.example` to `.env` and never commit real keys
    - Links to the three steering files and `shared/api.md`; top-level folders with a one-line description and owner; the owner-folder rule
    - Commands for `eval/validate_mock.py` and the `tsc --noEmit` mock check, each with its pass and fail output
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 15.2_

- [ ] 7. [BLOCKING] Checkpoint: Phase 1 contract complete
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest`, `python eval/validate_mock.py` (prints `OK`), and the `tsc --noEmit` mock check; confirm every path named in the steering files and README exists.

- [ ] 8. [BLOCKING] Commit and push the Phase 1 baseline
  - [ ] 8.1 [BLOCKING] Commit the Phase 1 baseline on the default branch
    - Stage the skeleton, shared contract, steering files, README, and tests by name; confirm no `.env` file or variant is staged and all tracked data is synthetic
    - Commit, then confirm `git status` shows no uncommitted changes to those files
    - _Requirements: 14.1, 14.2, 15.1, 15.4_
  - [ ] 8.2 [BLOCKING] Push the Phase 1 baseline to GitHub
    - Confirm the remote and the target branch with the user before pushing; push with `-u`
    - Never commit `.env` files; recheck `git status` before pushing
    - _Requirements: 14.2_

### Phase 2: Parallel work by owner (each group runs against the Phase 1 stub and mocks)

- [ ] 9. Account A: extraction (`backend/extraction/` only)
  - [ ] 9.1 Write the extraction prompt builder in `backend/extraction/prompt.py`
    - `build_prompt(utterance, record) -> str` asks for JSON proposals `{path, value, quote, confidence}` where `quote` is copied verbatim from the utterance
    - _Design: Overview (facts carry provenance; quotes are utterance substrings)_
  - [ ] 9.2 Write the proposal parser in `backend/extraction/parse.py`
    - `parse_proposals(text) -> list[Proposal]`; malformed JSON yields `[]`; drop entries with missing keys or `confidence` outside 0 to 1
    - _Requirements: 3.3, 3.4_
  - [ ] 9.3 Write quote verification in `backend/extraction/verify.py`
    - Keep a proposal only if its `quote` is a substring of `utterance.text`, its `path` resolves to a `PatientRecord` field, and its value validates for that field
    - _Design: Overview (quotes are utterance substrings)_
  - [ ]* 9.4 Write property test for quote verification in `backend/extraction/tests/test_quote_property.py`
    - **Property 5: Quotes are substrings** (extraction side: no kept proposal has a non-substring quote)
    - **Validates: Requirements 6.4**
  - [ ] 9.5 Write proposal application in `backend/extraction/apply.py`
    - Return a new `PatientRecord` (input untouched) with each value and a `SourceRef` `{utterance_id, quote, ts}`; `meds_given` and `vitals_timeline` items append
    - Leave conflict handling to the store's `derive`
    - _Requirements: 4.4, 4.5_
  - [ ] 9.6 Wire `process_utterance` in `backend/extraction/__init__.py`
    - Prompt, then `backend.llm.call_llm` (called through the module so tests can patch it), then parse, verify, apply; keep the Phase 1 signature
    - Let `call_llm` errors propagate so the API reports a 500 `processing` error
    - _Requirements: 10.1, 10.11_
  - [ ]* 9.7 Write unit tests for `process_utterance` in `backend/extraction/tests/test_process_utterance.py`
    - Patched `call_llm` with hero-style utterances ("no allergies", penicillin allergy bracelet, aspirin given); non-substring quotes dropped; input record not mutated; `call_llm` errors propagate
    - _Requirements: 10.1_

- [ ] 10. Checkpoint: Account A extraction
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/extraction eval/tests/test_stub_smoke.py` to confirm the stub still serves every endpoint.

- [ ] 11. Account B: safety (`backend/safety/` only)
  - [ ] 11.1 Write the flag id function in `backend/safety/ids.py`
    - `flag_id(type, rule_key, evidence) -> str` returns `f"{type}:{sha1(type + rule_key + sorted evidence)[:12]}"` with a fixed join for the evidence list
    - _Requirements: 5.2, 5.8_
  - [ ]* 11.2 Write unit tests for flag ids in `backend/safety/tests/test_ids.py`
    - Deterministic; evidence order does not matter; different `rule_key` values with empty evidence give different ids; length within 64
    - _Requirements: 5.8_
  - [ ] 11.3 Write the read-through lookup cache in `backend/safety/cache.py`
    - `cached(kind, key, fetch)` returns the JSON entry under `backend/safety/cache/` when present without calling `fetch`; on a miss it calls `fetch` and writes the result
    - Each entry carries the `Citation` used as a flag's `source_ref`; seed tracked entries for aspirin and penicillin
    - _Requirements: 5.2_
  - [ ] 11.4 Write medication rules in `backend/safety/rules_meds.py`
    - Pure, deterministic `duplicate_dose` (same drug given more than once), `allergy_conflict` (a given drug matches a listed allergy), and `interaction` (a cached interacting pair)
    - Each hit returns type, severity, `rule_key`, message, evidence quotes from the record's sources, and a cached citation
    - _Requirements: 5.1, 5.2_
  - [ ] 11.5 Write record rules in `backend/safety/rules_record.py`
    - `contradiction`: one hit per `conflicted` Sourced field, with all its source quotes as evidence
    - `missing_info`: one hit per required field still `unknown`, using a required-field list defined in this module
    - _Requirements: 5.1, 5.2_
  - [ ] 11.6 Write `say_to_crew` phrasing in `backend/safety/phrasing.py`
    - Ask `backend.llm.call_llm` to phrase the line from the hit's message and evidence; accept 1 to 280 non-blank characters, otherwise use the per-type template
    - Any exception (including a missing key) falls back to the template; the LLM never changes type, severity, or evidence
    - _Requirements: 11.1_
  - [ ] 11.7 Wire `evaluate` in `backend/safety/__init__.py`
    - Run all rules, build each `Flag` with `flag_id`, the phrased `say_to_crew`, and the default status, validate through the schema, and return in a stable order; keep the Phase 1 signature
    - _Requirements: 5.3, 5.8, 10.2, 10.11_
  - [ ]* 11.8 Write unit tests for rules and `evaluate` in `backend/safety/tests/test_evaluate.py`
    - A hero-style record gives `duplicate_dose` for aspirin and `contradiction` for `allergies`; repeated calls give identical ids; `LLM_API_KEY` unset uses the template; cache hits never call `fetch`
    - _Requirements: 5.8, 11.1_

- [ ] 12. Checkpoint: Account B safety
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/safety eval/tests/test_stub_smoke.py` to confirm the stub still serves every endpoint.

- [ ] 13. Account C: frontend (`frontend/` only)
  - [ ] 13.1 Add vitest and Testing Library to the frontend
    - Exact pinned dev dependencies, jsdom test environment, and `npm run test` running `vitest --run`
    - _Design: Testing Strategy_
  - [ ] 13.2 Write the typed API client in `frontend/src/api.ts`
    - One function per endpoint in `shared/api.md`, base URL `http://localhost:8000`, types via `import type` from `shared/types.ts`, and `ErrorBody` parsed on non-2xx responses
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.13, 7.14_
  - [ ] 13.3 Write the stream hook in `frontend/src/useStream.ts`
    - `EventSource` on `/api/stream`; keep the latest `record`, `flags`, and `clocks`; reconnect on drop
    - _Requirements: 7.2, 7.7, 7.8_
  - [ ] 13.4 Write the layout with the disclaimer in `frontend/src/components/Layout.tsx`
    - Fixed footer "decision support, not clinical advice." visible without scrolling on every screen
    - _Requirements: 11.5_
  - [ ] 13.5 Write `frontend/src/components/SourcedField.tsx`
    - Value, a distinct badge per status, each source quote and timestamp (all sources when `conflicted`), and a Confirm button that calls the confirm endpoint with the field path
    - _Requirements: 3.1, 3.2, 7.4, 7.9_
  - [ ] 13.6 Write `frontend/src/components/RecordPanel.tsx`
    - Every `PatientRecord` field through `SourcedField`; medications with paths `meds_given.N`; the vitals timeline as a table; notes
    - _Requirements: 4.3, 4.4, 4.5_
  - [ ] 13.7 Write `frontend/src/components/FlagsPanel.tsx`
    - Severity, type, message, evidence quotes, `source_ref` link, and `say_to_crew` labelled for the operator to relay; Relay when `open`, Ack when `relayed`; show 404 and 409 errors
    - _Requirements: 5.1, 11.3, 11.4, 11.7_
  - [ ] 13.8 Write `frontend/src/components/UtteranceInput.tsx`
    - Web Speech API when available, with a typed textarea always available as fallback; posts `{text, ts}` with 1 to 2000 characters; shows 422 errors
    - _Requirements: 1.4, 7.1, 9.5_
  - [ ] 13.9 Write `frontend/src/components/ClocksBar.tsx`
    - Contact time, ETA, door-to-ECG target, and elapsed time since each medication's last dose
    - _Requirements: 7.8_
  - [ ] 13.10 Write `frontend/src/components/OutputsPanel.tsx`
    - SBAR, pre-alert, and checklist, refetched when the record or flags change; empty states for empty responses
    - _Requirements: 7.3, 7.10_
  - [ ] 13.11 Write `frontend/src/components/ScenarioPicker.tsx`
    - List ids from `GET /api/scenarios`; play via `POST /api/scenario/{id}/play`; show 404 errors
    - _Requirements: 7.13, 7.14_
  - [ ] 13.12 Wire `frontend/src/App.tsx`
    - Compose `Layout`, the stream hook, and all panels into one screen
    - _Requirements: 11.5_
  - [ ]* 13.13 Write component tests in `frontend/src/components/__tests__/panels.test.tsx`
    - `SourcedField` badges for all four statuses, all sources shown when conflicted, and the confirm call; `FlagsPanel` buttons per status and the 409 message
    - _Requirements: 3.1, 11.3, 11.7_
  - [ ]* 13.14 Write app tests in `frontend/src/__tests__/App.test.tsx`
    - Disclaimer visible on every rendered screen; typed input works when `SpeechRecognition` is undefined
    - _Requirements: 11.5_

- [ ] 14. Checkpoint: Account C frontend
  - Ensure all tests pass, ask the user if questions arise.
  - Run `npm run test` and `npx tsc --noEmit` in `frontend/`, and `pytest eval/tests/test_stub_smoke.py` to confirm the stub still serves every endpoint.

- [ ] 15. Account D: store, outputs, scenarios, eval (`backend/store/`, `backend/outputs/`, `scenarios/`, `eval/` only)
  - [ ] 15.1 Write event validation in `backend/store/validate.py`
    - `validate_event(event)` checks `kind` against the kinds in `shared/api.md` and the payload against that kind's shape; errors name the field and the reason
    - _Requirements: 6.3, 6.7_
  - [ ] 15.2 Write persistence in `backend/store/persist.py`
    - `save(events)` writes `backend/store/event_log.json` atomically (path overridable for tests); `load()` returns the events; a corrupt file raises so startup fails
    - _Design: Components and Interfaces (store), Error Handling_
  - [ ] 15.3 Write the append-only log in `backend/store/log.py`
    - `append(event)` validates, rejects a duplicate `id`, persists, then adds to memory; any failure leaves memory and file unchanged; `events()` returns oldest first
    - _Requirements: 6.7, 6.8, 6.9, 7.5_
  - [ ]* 15.4 Write property test for append in `backend/store/tests/test_append_property.py`
    - **Property 3: Append is all-or-nothing**
    - **Validates: Requirements 6.7, 6.8, 6.9**
  - [ ] 15.5 Write the fold in `backend/store/derive.py`
    - `apply_event(state, event)` and `derive(events)` as its fold from `(PatientRecord(), [])`, never mutating inputs
    - `fact`: a field with no sources takes the value as `unverified` (this covers `allergies`, which defaults to `[]`); the same value adds the source (dedupe on `utterance_id` + `quote`); a different value keeps the old value, adds the source, and sets `conflicted`; `meds_given` and `vitals_timeline` append
    - `flag_raised` adds a flag and keeps the existing status for a known id; `flag_relayed`, `flag_acked`, and `field_confirmed` set status
    - _Requirements: 6.4, 6.5_
  - [ ]* 15.6 Write property test for contradictions in `backend/store/tests/test_conflict_property.py`
    - **Property 6: Contradiction never overwrites**
    - **Validates: Requirements 6.4**
  - [ ] 15.7 Write `facts_from` in `backend/store/facts.py`
    - Diff the old and new records into `fact` events (unique ids, UTC millisecond `ts`), one per new value and source; drop any fact whose quote is not a substring of `utt.text`
    - _Requirements: 6.1, 6.4_
  - [ ]* 15.8 Write property test for `facts_from` quotes in `backend/store/tests/test_facts_property.py`
    - **Property 5: Quotes are substrings** (store side: non-substring quotes yield no `fact`)
    - **Validates: Requirements 6.4**
  - [ ] 15.9 Write the broadcaster in `backend/store/broadcast.py`
    - `publish(kind, data)` and a `subscribe()` async iterator of `(kind, data)`, with one queue per subscriber, removed on close
    - _Requirements: 7.2_
  - [ ] 15.10 Wire `backend/store/__init__.py`
    - Public `append` (log append, then `apply_event` on the live state, then publish `record` and `flags`), `events`, `derive`, `facts_from`, and `subscribe` with the Phase 1 signatures; load and replay `event_log.json` on startup
    - _Requirements: 6.4, 6.5, 6.9, 7.2_
  - [ ]* 15.11 Write property test for replay in `backend/store/tests/test_replay_property.py`
    - **Property 4: Replay equals live**
    - **Validates: Requirements 6.4, 6.5**
  - [ ] 15.12 Write `make_sbar` in `backend/outputs/sbar.py`
    - Deterministic Situation, Background, Assessment, Recommendation text from the record (marking `unverified` and `conflicted` values) and open flags; `""` when nothing is known
    - _Requirements: 7.10, 10.3_
  - [ ] 15.13 Write `make_pre_alert` in `backend/outputs/pre_alert.py`
    - Short ED pre-alert from age, sex, chief complaint, suspected condition, ESI, ETA, and critical flags; `""` when nothing is known
    - _Requirements: 7.10, 10.5_
  - [ ] 15.14 Write `make_checklist` in `backend/outputs/checklist.py`
    - Bed and resus items from a rule table keyed on `suspected_condition`, `acuity_esi`, and open flags; `[]` when nothing applies
    - _Requirements: 7.10, 10.4_
  - [ ] 15.15 Wire `backend/outputs/__init__.py`
    - Re-export the three functions with the Phase 1 signatures
    - _Requirements: 10.3, 10.4, 10.5, 10.11_
  - [ ]* 15.16 Write unit tests for outputs in `backend/outputs/tests/test_outputs.py`
    - An empty record gives `""` and `[]`; a hero-style record mentions the allergy conflict and the duplicate aspirin; output is deterministic
    - _Requirements: 7.10_
  - [ ] 15.17 Author `scenarios/stemi_hero.json` and document the format in `scenarios/README.md`
    - Format `{id, utterances: [{text, ts}]}`, where each utterance validates as `UtteranceRequest`
    - Synthetic STEMI run: chest pain and ST elevation, "no allergies", aspirin given, vitals, a penicillin allergy bracelet found, aspirin given again, ETA; no real names or identifiers
    - _Requirements: 15.1_
  - [ ] 15.18 Write the contract smoke check in `eval/check_contract.py`
    - Every endpoint in `shared/api.md` is a route on `backend.main:app`; every path linked from the README and steering files exists; every `scenarios/*.json` validates
    - Print `OK` and exit 0, or list failures and exit non-zero
    - _Requirements: 1.8, 9.1, 13.5_
  - [ ] 15.19 Write the eval runner in `eval/run_all.py`
    - Run `pytest` (including Hypothesis), `eval/validate_mock.py`, the `tsc --noEmit` mock check, `eval/check_contract.py`, and frontend `vitest --run`; print a pass/fail summary and exit non-zero on any failure
    - _Requirements: 8.7, 12.3, 13.7_

- [ ] 16. Checkpoint: Account D store, outputs, scenarios, eval
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/store backend/outputs eval` and `python eval/check_contract.py` to confirm the stub still serves every endpoint.

### Phase 3: Integration, eval, and demo polish

- [ ] 17. Hero scenario end to end through the real pipeline
  - [ ] 17.1 Switch `backend/main.py` state to the store
    - Keep the Phase 1 mock behaviour as a selectable stub mode (for example `SCRIBE_MODE=stub`) and point the Phase 1 stub tests at it
    - Real mode replays `event_log.json` on startup; `GET /api/record`, `/api/flags`, and `/api/events` read from the store
    - _Requirements: 6.4, 6.5, 9.1_
  - [ ] 17.2 Wire `POST /api/utterance` to the pipeline in `backend/main.py`
    - Build an `Utterance`, then run `process_utterance`, `facts_from`, `derive` over existing plus new events, `evaluate`, and create `flag_raised` events for new flag ids
    - Validate every new event before appending any; on any exception return 500 `processing` and append nothing; respond with the derived record
    - _Requirements: 6.7, 6.9, 7.1, 7.11_
  - [ ] 17.3 Route relay, ack, and confirm through store events in `backend/main.py`
    - Append `flag_relayed`, `flag_acked`, and `field_confirmed`; same 200, 409, and 404 rules as the stub; repeats return 200 without a new event
    - _Requirements: 7.4, 7.9, 7.12, 11.3, 11.7_
  - [ ] 17.4 Wire outputs and the live stream in `backend/main.py`
    - `/api/sbar`, `/api/preAlert`, and `/api/checklist` call the outputs module
    - `/api/stream` sends the initial three events, forwards store `subscribe` updates within 1 s, and sends `clocks` every 1 s computed per `shared/api.md` (contact from the first `utterance` event, one `ClockEntry` per `meds_given.N`)
    - _Requirements: 7.2, 7.3, 7.8, 7.10_
  - [ ] 17.5 Wire the scenario endpoints in `backend/main.py`
    - `GET /api/scenarios` lists `scenarios/*.json` ids; `POST /api/scenario/{id}/play` feeds each utterance in order through the 17.2 pipeline and returns the final record; an unknown id returns 404
    - _Requirements: 7.13, 7.14_
  - [ ] 17.6 Write and run the hero end-to-end test in `eval/tests/test_hero_e2e.py`
    - Play `stemi_hero` with `TestClient`; assert `allergies` is `conflicted` with both the "no allergies" and the bracelet sources kept, a `contradiction` flag for allergies, a `duplicate_dose` flag for aspirin, every quote a substring of a scenario utterance, and `derive(events())` equal to the live record
    - Uses the real `call_llm`; skip with a clear message when `LLM_API_KEY` is unset
    - _Requirements: 5.8, 6.4, 6.5, 11.1_

- [ ] 18. Checkpoint: hero scenario passes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Eval
  - [ ] 19.1 Run `python eval/run_all.py` and fix each failure in its owning folder
    - Covers all property tests, `eval/validate_mock.py`, the `tsc --noEmit` mock check, and `eval/check_contract.py`; any `shared/` fix needs agreement from all contributors first
    - _Requirements: 1.7, 8.7, 12.3_

- [ ] 20. Demo polish
  - [ ] 20.1 Polish the hero run in the frontend (`frontend/` only)
    - Conflicted `allergies` shows both sources side by side; `contradiction` and `duplicate_dose` flags show `say_to_crew` with Relay and Ack; readable messages for 404, 409, and 422; disclaimer still visible; no new features
    - _Requirements: 11.3, 11.5_
  - [ ] 20.2 Keep the hero safety cache entries tracked under `backend/safety/cache/`
    - Add any entries the hero run fetched so `evaluate` needs no network; confirm they are not gitignored
    - _Design: Components and Interfaces (safety cache)_
  - [ ]* 20.3 Write the offline safety test in `backend/safety/tests/test_offline_demo.py`
    - With `LLM_API_KEY` unset and `fetch` failing, `evaluate` on the hero record returns the same flag ids with template `say_to_crew`
    - _Requirements: 5.8, 11.1_

- [ ] 21. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `[BLOCKING]` marks Phase 1 work that must land and be pushed before Phase 2 starts. Optional `*` Phase 1 tests may be skipped, but if you do them, finish them before the push.
- Tasks marked `*` are optional and can be skipped for a faster MVP.
- Phase 2 groups touch only their own folder and run against the Phase 1 stub and mocks. No group depends on another. A group that needs a `shared/` change waits for agreement from all contributors.
- Phase 3 edits `backend/main.py`, which sits outside every owner folder. Agree on one person to make those edits.
- Property tests use Hypothesis with at least 100 examples each and the tag `# Feature: ambulance-scribe-contract, Property N: <title>`.
- The hero end-to-end test calls the real LLM through `call_llm`, so it needs `LLM_API_KEY` set.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "5.1"] },
    { "id": 1, "tasks": ["1.4", "1.5", "1.6", "2.2", "2.7"] },
    { "id": 2, "tasks": ["2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6", "3.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 4, "tasks": ["3.2", "3.3", "4.1", "5.6"] },
    { "id": 5, "tasks": ["4.2", "6.1"] },
    { "id": 6, "tasks": ["4.3"] },
    { "id": 7, "tasks": ["4.4"] },
    { "id": 8, "tasks": ["4.5"] },
    { "id": 9, "tasks": ["4.6", "4.7", "4.8", "4.9"] },
    { "id": 10, "tasks": ["8.1"] },
    { "id": 11, "tasks": ["8.2"] },
    { "id": 12, "tasks": ["9.1", "9.2", "11.1", "11.3", "11.6", "13.1", "13.2", "13.3", "13.4", "15.1", "15.2", "15.5", "15.7", "15.9", "15.12", "15.13", "15.14", "15.17", "15.18"] },
    { "id": 13, "tasks": ["9.3", "9.5", "11.2", "11.4", "11.5", "13.5", "13.7", "13.8", "13.9", "13.10", "13.11", "15.3", "15.6", "15.8", "15.15", "15.19"] },
    { "id": 14, "tasks": ["9.4", "9.6", "11.7", "13.6", "15.10", "15.16"] },
    { "id": 15, "tasks": ["9.7", "11.8", "13.12", "15.4", "15.11"] },
    { "id": 16, "tasks": ["13.13", "13.14"] },
    { "id": 17, "tasks": ["17.1"] },
    { "id": 18, "tasks": ["17.2"] },
    { "id": 19, "tasks": ["17.3"] },
    { "id": 20, "tasks": ["17.4"] },
    { "id": 21, "tasks": ["17.5"] },
    { "id": 22, "tasks": ["17.6"] },
    { "id": 23, "tasks": ["19.1"] },
    { "id": 24, "tasks": ["20.1", "20.2"] },
    { "id": 25, "tasks": ["20.3"] }
  ]
}
```
