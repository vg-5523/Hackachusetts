# Implementation Plan: Frontend

## Overview

Build the single-screen operator UI on the existing Vite + React + TS + Tailwind scaffold under `frontend/`. Work bottom-up: wiring and shared-type access, then the typed API client, the SSE hook, and the pure replay fold, then presentation components, and finally wire everything into `App.tsx`. All edits stay inside `frontend/`; `shared/` and `backend/` are read-only.

## Tasks

- [ ] 1. Project wiring and shared-type access
  - [ ] 1.1 Wire `@shared`, test tooling, and theme into the scaffold
    - Add a `@shared` alias to `frontend/vite.config.ts` (`resolve.alias`) and `frontend/tsconfig.json` (`compilerOptions.paths`, widen `include` to `["src", "../shared"]`).
    - Add pinned dev deps to `frontend/package.json`: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `fast-check`; add `"test": "vitest --run"` script and a `test` config in `vite.config.ts` (environment `jsdom`).
    - Add dark base styles and the critical-flag entrance keyframes to `frontend/tailwind.config.js` and `frontend/src/index.css`.
    - _Requirements: 1.2, 4.10, 6.2_
    - _Design: Architecture (shared-type access, config), Error Handling, Testing Strategy_

- [ ] 2. Typed API client and errors
  - [ ] 2.1 Implement `frontend/src/api.ts`
    - One typed function per endpoint: `postUtterance`, `getRecord`, `getFlags`, `getEvents`, `getSbar`, `getPreAlert`, `getChecklist`, `relayFlag`, `ackFlag`, `confirmField`, `getScenarios`, `playScenario`, and `openStream` (returns `EventSource`).
    - API base from `import.meta.env.VITE_API_BASE`, default `http://localhost:8000`; on non-2xx parse body as `ErrorBody` and throw `ApiError { status, body }` (`body` null when unparseable). Import types from `@shared/types`.
    - _Requirements: 2.3, 2.5, 2.8, 3.5, 4.6, 4.7, 7.1, 7.4, 8.1_
    - _Design: Components and Interfaces (api.ts)_
  - [ ]* 2.2 Write unit tests for `api.ts`
    - Assert `ApiError` mapping for 422/404/409/500 and `body === null` on unparseable body.
    - _Requirements: 8.1, 8.6_

- [ ] 3. SSE stream hook
  - [ ] 3.1 Implement `frontend/src/useStream.ts`
    - Wrap `openStream`; register `record`, `flags`, `clocks` listeners; hold latest payloads in `StreamState`; reconnect on drop without operator action.
    - _Requirements: 6.1, 6.5_
    - _Design: Components and Interfaces (useStream), Data Models (StreamState)_
  - [ ]* 3.2 Write unit test for reconnect
    - Mock `EventSource`; assert handlers re-register after a drop.
    - _Requirements: 6.5_

- [ ] 4. Pure replay fold
  - [ ] 4.1 Implement `frontend/src/replay.ts`
    - `replayFold(events, upToIndex): ReplaySnapshot` folding oldest→newest over kinds `utterance`, `fact`, `flag_raised`, `flag_relayed`, `flag_acked`, `field_confirmed` from an empty record.
    - _Requirements: 7.6, 7.7_
    - _Design: Data Models (replayFold)_
  - [ ]* 4.2 Write property test for replay fold
    - **Property 4: Replay fold determinism and correctness** (fast-check, ≥100 iters)
    - **Validates: Requirements 7.6, 7.7**

- [ ] 5. Layout shell
  - [ ] 5.1 Implement `frontend/src/components/Layout.tsx`
    - CSS-grid shell: top bar slot, three columns (transcript/record/flags), fixed footer with exact text `decision support, not clinical advice. Synthetic data only.`; dark high-contrast theme fitting 1280×720 without scroll.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Design: Components and Interfaces (Layout)_
  - [ ]* 5.2 Write property test for disclaimer footer
    - **Property 1: Disclaimer footer invariant** (fast-check, ≥100 iters)
    - **Validates: Requirements 1.4, 1.5**

- [ ] 6. Top bar
  - [ ] 6.1 Implement `frontend/src/components/ClocksBar.tsx`
    - Render time-since-contact, door-to-ECG countdown, ETA, and per-med elapsed from `meds[].elapsed_s`; tick client-side via `setInterval(1s)`; null placeholders; overdue state when target is past.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
    - _Design: Components and Interfaces (ClocksBar)_
  - [ ] 6.2 Implement `frontend/src/components/WhatChanged.tsx`
    - Diff previous vs next `record`/`flags` and render one ≤140-char summary, replaced on each change.
    - _Requirements: 6.3, 6.4_
    - _Design: Components and Interfaces (WhatChanged)_
  - [ ]* 6.3 Write unit tests for ClocksBar
    - Null placeholders and overdue countdown with fake timers; ticking advances once per second.
    - _Requirements: 5.4, 5.5, 5.6_

- [ ] 7. Record panel with provenance (center)
  - [ ] 7.1 Implement `frontend/src/components/ProvenanceDrawer.tsx`
    - List every source (quote + ISO-8601 ts) for the selected field; expose active `utterance_id`.
    - _Requirements: 3.3, 3.4_
    - _Design: Components and Interfaces (ProvenanceDrawer)_
  - [ ] 7.2 Implement `frontend/src/components/SourcedField.tsx` and `frontend/src/components/RecordPanel.tsx`
    - Render each field with a status badge (never a value without a badge); click opens the drawer; Confirm control on `unverified` calls `confirmField(path)` and updates badge to `confirmed`; meds use path `meds_given.N`.
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.7, 3.8_
    - _Design: Components and Interfaces (RecordPanel + SourcedField)_
  - [ ]* 7.3 Write unit test for Confirm flow
    - Assert badge updates to `confirmed` on success and stays unchanged on not-found.
    - _Requirements: 3.6, 3.7_

- [ ] 8. Transcript and input (left)
  - [ ] 8.1 Implement `frontend/src/components/TranscriptPanel.tsx`
    - Derive utterances from `GET /api/events` kind `utterance`, ascending by `ts`; empty placeholder; highlight active source utterance while a drawer is open.
    - _Requirements: 2.1, 2.2, 2.10_
    - _Design: Components and Interfaces (TranscriptPanel)_
  - [ ] 8.2 Implement `frontend/src/components/UtteranceInput.tsx`
    - Feature-detected mic (Web Speech API) posting each result; always-present `<textarea>` fallback with 1–2000 char validation, retain-on-failure, retry; play-scenario control.
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_
    - _Design: Components and Interfaces (TranscriptPanel)_
  - [ ]* 8.3 Write unit tests for UtteranceInput
    - Textarea renders when `SpeechRecognition` undefined; 1–2000 validation; retain text on POST failure.
    - _Requirements: 2.4, 2.6, 2.7_

- [ ] 9. Flags and relay (right)
  - [ ] 9.1 Implement `frontend/src/components/FlagsPanel.tsx`, `FlagCard.tsx`, `SayToCrewBox.tsx`
    - Sort `critical`>`warn`>`info`, ties oldest-first; show `message`, `evidence`, `source_ref` link, verbatim `say_to_crew`; Relayed enabled iff `open`, Acknowledged iff `relayed`, both disabled when `acknowledged`; show returned status/transition on success, unchanged on 409; critical flag animates + sounds once per `id`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_
    - _Design: Components and Interfaces (FlagsPanel + FlagCard)_
  - [ ]* 9.2 Write property test for control enablement
    - **Property 2: Flag-control enablement matches status** (fast-check, ≥100 iters)
    - **Validates: Requirements 4.3, 4.4, 4.5**
  - [ ]* 9.3 Write property test for severity sort
    - **Property 3: Severity sort order** (fast-check, ≥100 iters)
    - **Validates: Requirements 4.1**
  - [ ]* 9.4 Write property test for critical alert
    - **Property 5: Critical alert fires once per flag id** (fast-check, ≥100 iters, mock audio)
    - **Validates: Requirements 4.10**

- [ ] 10. Outputs and replay
  - [ ] 10.1 Implement `frontend/src/components/OutputsTabs.tsx`
    - SBAR / pre-alert / checklist tabs from `getSbar`/`getPreAlert`/`getChecklist` with empty-state and per-tab error placeholders; replay scrubber over `GET /api/events` using `replayFold`, disabled when empty, set to newest on load, updates within move.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
    - _Design: Components and Interfaces (OutputsTabs)_

- [ ] 11. Error toast and app wiring
  - [ ] 11.1 Implement `frontend/src/components/ErrorToast.tsx`
    - Map `ApiError.status` 422/404/409/500 to messages (include `detail`, and `field` when non-null); generic fallback when `body` is null.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
    - _Design: Components and Interfaces (ErrorToast), Error Handling_
  - [ ] 11.2 Wire everything into `frontend/src/App.tsx`
    - Compose Layout with `useStream` state, ClocksBar, WhatChanged, TranscriptPanel/UtteranceInput, RecordPanel, FlagsPanel, OutputsTabs, ErrorToast; route API errors to the toast.
    - _Requirements: 6.1, 6.2, 8.1_
    - _Design: Architecture (data flow)_

- [ ] 12. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (test authoring) and can be skipped for a faster MVP.
- Each task references the requirements and design sections it implements for traceability.
- Property tests use fast-check at ≥100 iterations per the design Testing Strategy; unit/example tests cover edge cases.
- All file paths are under `frontend/`; `shared/` and `backend/` remain read-only.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2", "5.2", "6.1", "6.2", "7.1"] },
    { "id": 3, "tasks": ["6.3", "7.2", "8.1", "8.2", "9.1", "10.1", "11.1"] },
    { "id": 4, "tasks": ["7.3", "8.3", "9.2", "9.3", "9.4", "11.2"] }
  ]
}
```
