# Design Document

## Overview

- The append-only Event_Log is the single source of truth; `derive(events) -> (PatientRecord, list[Flag])` is the one pure fold, so replay and live derivation are identical.
- `SCRIBE_MODE` selects behavior: `stub` keeps today's mock `ServerState`, `live` runs the real pipeline.
- Outputs are deterministic and traceable: every sentence cites the `PatientRecord` field it came from, no LLM.
- Five scenario transcripts plus gold files feed an eval harness that scores extraction and flags.
- No changes to `shared/`, `backend/extraction/`, or `backend/safety/`; their stub signatures are reused as-is.

## Architecture

```mermaid
flowchart LR
  U[POST /api/utterance] --> M[main.py live]
  M --> A1[store.append utterance]
  A1 --> EX[extraction.process_utterance]
  EX --> F[store.facts_from]
  F --> A2[store.append fact...]
  A2 --> SF[safety.evaluate]
  SF --> A3[store.append flag_raised]
  A3 --> B[broadcast]
  B --> SSE[GET /api/stream]
```

File layout:

```
backend/store/   validate.py persist.py log.py derive.py facts.py broadcast.py __init__.py
backend/outputs/ sbar.py pre_alert.py checklist.py __init__.py
scenarios/       {stemi_hero,clean_stemi,stroke,garbled_uncertain,opioid_overdose}.json + *.gold.json + README.md
eval/            run_scenarios.py report.md
```

## Components and Interfaces

- `backend/store/__init__.py` (unchanged signatures): `append(event)->Event`, `events()->list[Event]`, `derive(events)->(PatientRecord,list[Flag])`, `facts_from(utt,old,new)->list[Event]`, async `subscribe()->AsyncIterator[tuple[str,dict]]`.
- `backend/outputs/__init__.py` (unchanged): `make_sbar(record,flags)->str`, `make_pre_alert(record,flags)->str`, `make_checklist(record)->list[str]`.
- `main.py`: mode-aware endpoints reusing existing helpers (`error_response`, `validate_response`, `_build_clocks`); calls `extraction.process_utterance` and `safety.evaluate` only via their stub signatures.
- `eval/run_scenarios.py`: CLI entry that plays scenarios and writes the report.

## Data Models

Reused unchanged from `shared/schema.py`: `Sourced[T]`, `SourceRef`, `Citation`, `Medication`, `VitalsEntry`, `PatientRecord`, `Flag`, `Utterance`, `UtteranceRequest`, `Event`, `ClockEntry`, `Clocks`, `ErrorBody`. New shapes are JSON payloads only (not new Pydantic models):

- `Event.payload` by kind: `utterance {utterance}`, `fact {path,value,source,confidence}`, `flag_raised {flag}`, `flag_relayed {flag_id}`, `flag_acked {flag_id}`, `field_confirmed {path}`.
- Scenario file `{id, utterances:[{text, ts}]}`; gold file `{id, fields:{path: expected_value}, flags:[{type}]}`.

## Store design

- Event kinds `derive` handles: `utterance` (no record change), `fact {path,value,source,confidence}`, `flag_raised {flag}`, `flag_relayed {flag_id}`, `flag_acked {flag_id}`, `field_confirmed {path}`.
- `derive` folds from `(PatientRecord(), [])`; `apply_event(state, event)` never mutates inputs (copies via `model_copy(deep=True)`).
- Conflict rules on a scalar `Sourced` target: no sources -> set value, status `unverified`; same value -> add source, dedupe on `utterance_id`+`quote`; different value -> keep old value, add source, status `conflicted`. `meds_given`/`vitals_timeline` facts append a new entry.
- Flag stability: fold keeps a `dict[flag_id,status]`; a re-raised id keeps its prior status. `flag_relayed` sets `open->relayed`; `flag_acked` sets `relayed->acknowledged`; `field_confirmed` sets the Sourced status `confirmed`.
- Persistence (`persist.py`): `save(events, path=event_log.json)` writes atomically (tmp + `os.replace`); `load(path)` returns `list[Event]`; a corrupt file raises.
- `append` (`log.py`): validate kind/payload (`validate.py`), reject a duplicate id, persist, then append in memory — all-or-nothing, file and memory stay in sync.
- Broadcast (`broadcast.py`): holds a `set[asyncio.Queue]`; `publish(kind,data)` puts to each; `subscribe()` yields `(kind,data)` and drops its queue on cancel/close.
- `__init__.py` wires public `append`/`events`/`derive`/`facts_from`/`subscribe`; the live `events` list is replayed from disk on first import/startup.

## main.py SCRIBE_MODE

- Read `os.environ.get("SCRIBE_MODE","stub")`. Stub mode is today's `ServerState` mock path, unchanged, so existing stub tests pass untouched.
- Live mode: `GET /api/record|flags|events` read from `store.derive(store.events())`. `POST /api/utterance` runs the pipeline: validate `UtteranceRequest` -> build `Utterance` -> append `utterance` event -> `process_utterance(utt, current_record)` -> `facts_from(utt, old, new)` -> append each `fact` -> `evaluate(new_record)` -> append `flag_raised` for flag ids not already in the log -> broadcast `record`+`flags`.
- Append-last ordering: any exception before the first append returns 500 `processing` with state unchanged.
- `POST /api/scenario/{id}/play`: load `scenarios/{id}.json`; for each utterance run the live pipeline with an `asyncio.sleep` delay between utterances (streaming). Unknown id -> 404 `not_found`. In stub mode it keeps the Phase 1 no-side-effect behavior.
- Door-to-ECG target and `eta` clocks reuse the existing `main.py` helpers (`_build_clocks`, `_earliest_contact_ts`).

## Outputs design

- Condition table keyed on `suspected_condition.value`: STEMI -> [defib, crash cart, 12-lead ECG, cath lab notification]; stroke -> [CT slot, last-known-well].
- Each generated sentence traces to the specific `PatientRecord` field it was built from.
- `unverified`/`conflicted` values render with an explicit `(unverified)` / `(conflicted)` tag.
- Empty record -> `""` for `make_sbar`/`make_pre_alert`, `[]` for `make_checklist`. Fully deterministic, no LLM.

## Scenarios & gold

- Shapes per Data Models; each utterance validates as `UtteranceRequest`. Synthetic data only, no real identifiers.
- Five scenarios: `stemi_hero`, `clean_stemi`, `stroke`, `garbled_uncertain`, `opioid_overdose`, each paired with a gold file.

## Eval design

- Play each scenario in live mode (via `TestClient` or the pipeline directly).
- Compare derived record fields to gold (per-field exact-match accuracy) and flags to gold (precision/recall by flag type).
- Print a results table and write `eval/report.md`.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Schema JSON round-trip

*For any* valid shared model instance, `model_validate(json.loads(m.model_dump_json()))` equals the original.
**Validates: Requirements 8.1**

### Property 2: Replay equals live derivation

*For any* valid Event_Log, deriving live equals deriving from the persisted-then-reloaded log, and the conflict/append/stability rules hold throughout.
**Validates: Requirements 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 8.2**

### Property 3: Flag state machine

*For any* (status, action) pair, transitions follow `open->relayed->acknowledged`: idempotent repeats return 200, illegal transitions 409, unknown ids 404, and a re-raised id keeps its status.
**Validates: Requirements 8.3, 2.5**

## Error Handling

- `append` is all-or-nothing: duplicate id or invalid kind/payload is rejected, leaving the Event_Log and `event_log.json` unchanged.
- A corrupt `event_log.json` on load raises rather than silently starting empty.
- Live pipeline failure before the first append -> 500 `processing`, state unchanged (append-last ordering).
- Unknown scenario id -> 404 `not_found`; all errors serialize as `ErrorBody` through the existing `error_response` path.

## Testing Strategy

- `pytest` + `hypothesis` on the 3.11 venv (`.venv311`). Property tests (>=100 iterations each) implement the three properties above, tagged `Feature: store-outputs, Property {n}: {text}`.
- Unit/example tests cover Outputs condition keying and the empty-record case, plus scenario validation; eval runs as an integration check.
- Fix the SSE smoke test to read exactly three events (`record`, `flags`, `clocks`) then close the stream so pytest never hangs.
