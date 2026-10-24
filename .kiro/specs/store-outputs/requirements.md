# Requirements Document

## Introduction

Account D of the Ambulance Scribe + Safety Check project: the event-sourced Store, the Outputs generators, the scenario corpus, the eval harness, and the `backend/main.py` wiring. It reuses the models in `shared/schema.py` and the Phase 1 stub signatures of `backend.extraction.process_utterance` and `backend.safety.evaluate` without changing them.

## Glossary

- **Event_Log**: Append-only list of `Event` records; the single source of truth.
- **derive**: Pure fold `derive(events) -> (PatientRecord, list[Flag])`.
- **Store**: `backend/store/` module owning the Event_Log, `append`, `derive`, persistence, and SSE broadcast.
- **Outputs**: `backend/outputs/` generators `make_sbar`, `make_pre_alert`, `make_checklist`.
- **Gold file**: Expected extracted fields and flags for a scenario.
- **SCRIBE_MODE**: Env var selecting `stub` or `live` pipeline behavior, default `stub`.

## Requirements

### Requirement 1: Event-sourced store

**User Story:** As a backend owner, I want an append-only Event_Log with a single fold, so that state is reproducible and persistent.

#### Acceptance Criteria

1. THE Store SHALL expose an append-only Event_Log as the single source of truth.
2. THE Store SHALL expose one fold `derive` producing a `PatientRecord` and a `list[Flag]` from the Event_Log.
3. THE Store SHALL produce identical results when replaying the Event_Log as when deriving live.
4. THE Store SHALL persist the Event_Log to the gitignored file `backend/store/event_log.json`.
5. WHEN the Store starts, THE Store SHALL replay `backend/store/event_log.json` into the Event_Log.
6. IF an `append` supplies a duplicate id or an invalid kind or payload, THEN THE Store SHALL reject it and leave the Event_Log and file unchanged.
7. WHEN the Event_Log changes, THE Store SHALL broadcast `record`, `flags`, and `clocks` to SSE subscribers.

### Requirement 2: Conflict rules and flag stability in derive

**User Story:** As a safety reviewer, I want deterministic conflict handling and stable flag status, so that derived state is trustworthy.

#### Acceptance Criteria

1. WHEN a `fact` event targets a field with no sources, THE derive SHALL set the value with status `unverified`.
2. WHEN a `fact` event repeats the current value, THE derive SHALL add its source and dedupe on `utterance_id` plus `quote`.
3. WHEN a `fact` event supplies a different value, THE derive SHALL keep the old value, add the new source, and set status `conflicted`.
4. WHEN a `fact` event targets `meds_given` or `vitals_timeline`, THE derive SHALL append a new entry.
5. WHEN a flag id is re-raised, THE derive SHALL preserve that flag's existing status.

### Requirement 3: main.py pipeline wiring

**User Story:** As an operator, I want selectable stub and live modes, so that demos and real extraction share one endpoint.

#### Acceptance Criteria

1. THE Backend SHALL read `SCRIBE_MODE` as `stub` or `live`, defaulting to `stub`.
2. WHILE `SCRIBE_MODE` is `stub`, THE Backend SHALL preserve the exact Phase 1 mock behavior so existing stub tests pass.
3. WHILE `SCRIBE_MODE` is `live`, WHEN `POST /api/utterance` is received, THE Backend SHALL validate, append the utterance event, run `extraction.process_utterance`, derive facts, append fact events, run `safety.evaluate`, append `flag_raised` for new flag ids, and broadcast.
4. IF the live pipeline fails before any append, THEN THE Backend SHALL return 500 `processing` and leave state unchanged.
5. WHEN `POST /api/scenario/{id}/play` names a known scenario, THE Backend SHALL stream `scenarios/{id}.json` utterances through the pipeline with delays.
6. IF `POST /api/scenario/{id}/play` names an unknown id, THEN THE Backend SHALL return 404 `not_found`.

### Requirement 4: Outputs generators

**User Story:** As an operator, I want condition-keyed, traceable outputs, so that handoffs are accurate and honest about uncertainty.

#### Acceptance Criteria

1. THE Outputs SHALL provide `make_sbar`, `make_pre_alert`, and `make_checklist`.
2. WHERE `suspected_condition` is STEMI, THE Outputs SHALL key content on defib, crash cart, 12-lead ECG, and cath lab notification.
3. WHERE `suspected_condition` is stroke, THE Outputs SHALL key content on CT slot and last-known-well.
4. THE Outputs SHALL trace every generated sentence to specific `PatientRecord` fields.
5. WHEN a value is `unverified` or `conflicted`, THE Outputs SHALL label it as such.
6. WHEN the record is empty, THE Outputs SHALL return `""` for text outputs and `[]` for the checklist.

### Requirement 5: Scenario corpus

**User Story:** As a tester, I want five synthetic transcripts with gold files, so that extraction and flags can be measured.

#### Acceptance Criteria

1. THE Scenarios SHALL provide five JSON transcripts each shaped `{id, utterances:[{text, ts}]}`.
2. THE Scenarios SHALL make each utterance validate as `UtteranceRequest`.
3. THE Scenarios SHALL cover `stemi_hero`, `clean_stemi`, `stroke`, `garbled_uncertain`, and `opioid_overdose`.
4. THE Scenarios SHALL pair each transcript with a gold file of expected extracted fields and expected flags.
5. THE Scenarios SHALL contain synthetic data only with no real identifiers.

### Requirement 6: Eval harness

**User Story:** As a tester, I want an automated eval report, so that pipeline quality is visible.

#### Acceptance Criteria

1. THE Eval SHALL play every scenario through the pipeline.
2. THE Eval SHALL print a table of per-field extraction accuracy and flag precision and recall versus the gold files.
3. THE Eval SHALL write `eval/report.md`.

### Requirement 7: SSE smoke test fix

**User Story:** As a developer, I want the SSE smoke test to terminate, so that pytest does not hang.

#### Acceptance Criteria

1. THE Smoke_Test SHALL read exactly three events (`record`, `flags`, `clocks`) then close the stream.
2. THE Smoke_Test SHALL complete without hanging pytest.

### Requirement 8: Property tests

**User Story:** As a developer, I want property tests, so that core invariants hold across inputs.

#### Acceptance Criteria

1. THE Property_Tests SHALL verify schema JSON round-trip for shared models.
2. THE Property_Tests SHALL verify replay equals live derivation.
3. THE Property_Tests SHALL verify the flag state machine: `open` to `relayed` to `acknowledged`, 200 on idempotent repeats, 409 on illegal transition, and 404 on unknown id.

### Requirement 9: Ownership boundary

**User Story:** As a contributor, I want a clear ownership boundary, so that shared and other owners' code stays intact.

#### Acceptance Criteria

1. THE Account_D_Work SHALL NOT modify `shared/`, `backend/extraction/`, or `backend/safety/`.
2. IF a contract change is needed, THEN THE Account_D_Work SHALL propose it for the Contract owner to apply rather than editing `shared/` directly.

> Note: The Account D contract tasks (contract spec `tasks.md` task 15) are the authoritative cross-reference; this spec restates them as standalone requirements.
