# API Specification — Ambulance Scribe + Safety Check

This document is the written HTTP contract for the backend. It is the single
source of truth that frontend and backend contributors code against in
parallel. All model names refer to the Pydantic v2 models defined in
[`shared/schema.py`](./schema.py) and mirrored in [`shared/types.ts`](./types.ts):
`Sourced`, `SourceRef`, `Citation`, `Medication`, `VitalsEntry`, `PatientRecord`,
`Flag`, `ErrorBody`, `Utterance`, `UtteranceRequest`, `Event`, `ClockEntry`, and
`Clocks`, plus the enums `FieldStatus`, `FlagType`, `FlagSeverity`, and
`FlagStatus`.

- Base URL (development): `http://localhost:8000`
- Allowed CORS origins: exactly `http://localhost:5173` and
  `http://127.0.0.1:5173`; no other origin is allowed, including on preflight.
- Data is synthetic only. The API is unauthenticated.
- All request and response bodies are JSON unless noted (SSE uses `text/event-stream`).
- Timestamps are ISO 8601 strings that carry a UTC offset. `Event.ts` is
  serialized with millisecond precision.

## Safety contract (human in the loop)

- A `Flag` moves from `open` to `relayed` **only** through
  `POST /api/flags/{id}/relay`, and from `relayed` to `acknowledged` **only**
  through `POST /api/flags/{id}/ack`. (Req 11.3)
- **No endpoint delivers text, audio, or a push notification directly to a
  paramedic or to any crew-facing device or channel.** Every `say_to_crew` line
  is presented to a human operator, who decides whether and how to relay it to
  the crew. The API only exposes record, flag, clock, and output data for a
  human-operated UI to read. (Req 11.4)
- The UI shows the disclaimer "decision support, not clinical advice." This is a
  decision-support contract, not clinical advice.

## Error model

Every error response has HTTP status and a JSON body matching the `ErrorBody`
model:

```jsonc
{
  "category": "validation",   // string: the failure category (see below)
  "field": "text",            // optional string: the offending field, when applicable
  "detail": "text must be 1 to 2000 characters"  // string: human-readable reason
}
```

| HTTP status | `category` value                 | Meaning |
|-------------|----------------------------------|---------|
| 422         | `validation`                     | The request body failed validation. `field` names the offending field. |
| 404         | `not_found`                      | A referenced flag `id`, field `{path}`, or scenario `{id}` does not exist. |
| 409         | `conflict`                       | An invalid flag state transition was requested. |
| 500         | `processing`                     | The extraction and safety pipeline failed while handling the request. |
| 500         | `response_validation`            | A response body failed validation against its schema model and was not sent. |

**Failed requests change nothing.** When a request fails validation (422), is
not found (404), is a conflict (409), or fails processing (500), the
`PatientRecord`, the flags, and the Event_Log all remain unchanged. The append
to the Event_Log runs last, so a failure before it leaves state untouched.
(Req 7.11, 11.7)

## Endpoint summary

| Method | Path | Request body | Success (200) | Errors |
|---|---|---|---|---|
| POST | `/api/utterance` | `UtteranceRequest` | `PatientRecord` | 422 `validation`, 500 `processing`/`response_validation` |
| GET  | `/api/stream` | none | SSE stream of `record`, `flags`, `clocks` | — |
| GET  | `/api/record` | none | `PatientRecord` | 500 `response_validation` |
| GET  | `/api/flags` | none | `Flag[]` | 500 `response_validation` |
| GET  | `/api/events` | none | `Event[]` (oldest → newest) | 500 `response_validation` |
| GET  | `/api/sbar` | none | `string` | 500 `response_validation` |
| GET  | `/api/preAlert` | none | `string` | 500 `response_validation` |
| GET  | `/api/checklist` | none | `string[]` | 500 `response_validation` |
| POST | `/api/flags/{id}/relay` | empty | `Flag` (status `relayed`) | 404 `not_found`, 409 `conflict` |
| POST | `/api/flags/{id}/ack` | empty | `Flag` (status `acknowledged`) | 404 `not_found`, 409 `conflict` |
| POST | `/api/fields/{path}/confirm` | empty | `Sourced` (status `confirmed`) | 404 `not_found` |
| GET  | `/api/scenarios` | none | `string[]` scenario ids | 500 `response_validation` |
| POST | `/api/scenario/{id}/play` | empty | `PatientRecord` | 404 `not_found` |

Every response body is validated against its schema model before being sent. If
validation fails, the server responds 500 with `category` `response_validation`
and does not send the invalid body.

## Endpoints

### POST `/api/utterance`

Runs the extraction and safety pipeline on one submitted utterance, then returns
the resulting patient record.

- Request body: `UtteranceRequest`
  - `text`: string, 1 to 2000 characters, non-empty.
  - `ts`: ISO 8601 timestamp string with a UTC offset.
- Success: `200` with the current `PatientRecord`.
- Errors:
  - `422` `validation` if `text` or `ts` is missing, `text` is empty, `text`
    exceeds 2000 characters, or `text`/`ts` has the wrong type. The `field`
    identifies the invalid field. The record is left unchanged.
  - `500` `processing` if the extraction and safety pipeline fails. State is
    left unchanged.
  - `500` `response_validation` if the response body fails schema validation.

### GET `/api/stream`

Server-Sent Events (`text/event-stream`). The stream emits three event types,
each named with the SSE `event:` field and carrying a JSON `data:` payload.

| SSE `event` | `data` payload shape | Meaning |
|---|---|---|
| `record` | `PatientRecord` | The full current patient record. |
| `flags`  | `Flag[]` | The full current list of safety flags. |
| `clocks` | `Clocks` | The current clocks snapshot (see below). |

Cadence (Req 7.2, 7.7, 7.8, 9.3):

- On connect, the server sends, in order, an initial `record` event, then an
  initial `flags` event, then an initial `clocks` event, all within 1 second of
  connection.
- After the initial burst, the server sends a `clocks` event every 1 second
  (±100 ms) until the client disconnects.
- Whenever the record or the flags change, the corresponding `record` or `flags`
  event is emitted within 1 second of that state change.

#### The `Clocks` payload

`Clocks` carries the running timers shown in the UI clock bar. Fields:

| Field | Type | Meaning / derivation |
|---|---|---|
| `contact_ts` | timestamp or null | The patient-contact time: the timestamp of the earliest known utterance/event for this run. Null until contact is known. |
| `eta` | timestamp or null | Estimated time of arrival at the ED, derived from the record's `eta` Sourced value. Null when no ETA is known. |
| `door_to_ecg_target_ts` | timestamp or null | The target time by which a 12-lead ECG should be completed, derived from `contact_ts` plus the door-to-ECG goal. Null until it can be derived. |
| `meds` | `ClockEntry[]` | One `ClockEntry` per administered medication, i.e. one per `meds_given.N` entry in the record. |

Each `ClockEntry` (Req 7.8):

| Field | Type | Meaning / derivation |
|---|---|---|
| `med_id` | string | The medication's field path, e.g. `meds_given.0`. |
| `last_dose_ts` | timestamp | The timestamp of the medication's most recent dose. |
| `elapsed_s` | integer ≥ 0 | Whole seconds elapsed since `last_dose_ts`, as a non-negative integer. |

### GET `/api/record`

- Request body: none.
- Success: `200` with the current `PatientRecord`.

### GET `/api/flags`

- Request body: none.
- Success: `200` with a JSON array of `Flag` (`Flag[]`).

### GET `/api/events`

- Request body: none.
- Success: `200` with the complete Event_Log as a JSON array of `Event`,
  ordered from oldest to newest. Each entry includes its `ts`. (Req 7.5)

### GET `/api/sbar`

- Request body: none.
- Success: `200` with a JSON `string` (the SBAR handoff text). Returns an empty
  string `""` when no content is available. (Req 7.10)

### GET `/api/preAlert`

- Request body: none.
- Success: `200` with a JSON `string` (the ED pre-alert text). Returns an empty
  string `""` when no content is available. (Req 7.10)

### GET `/api/checklist`

- Request body: none.
- Success: `200` with a JSON array of `string` (`string[]`). Returns an empty
  list `[]` when no content is available. (Req 7.10)

### POST `/api/flags/{id}/relay`

Marks the flag relayed. The `{id}` path parameter is a flag `id`.

- Request body: empty.
- Success: `200` with the updated `Flag` whose `status` is `relayed`.
- Allowed from status `open` (→ `relayed`) and, idempotently, from `relayed`.
- Errors:
  - `404` `not_found` if no flag has that `id`. All flags are left unchanged.
  - `409` `conflict` if the flag's status is `acknowledged` (relay after ack is
    an invalid transition). The flag is left unchanged.

### POST `/api/flags/{id}/ack`

Marks the flag acknowledged. The `{id}` path parameter is a flag `id`.

- Request body: empty.
- Success: `200` with the updated `Flag` whose `status` is `acknowledged`.
- Allowed from status `relayed` (→ `acknowledged`) and, idempotently, from
  `acknowledged`.
- Errors:
  - `404` `not_found` if no flag has that `id`. All flags are left unchanged.
  - `409` `conflict` if the flag's status is `open` (ack before relay is an
    invalid transition). The flag is left unchanged.

### POST `/api/fields/{path}/confirm`

Confirms a `Sourced` field, setting its `status` to `confirmed`.

- Request body: empty.
- The `{path}` path parameter resolves to a `Sourced` field in the
  `PatientRecord` (see "The `{path}` parameter" below).
- Success: `200` with the targeted `Sourced` field whose `status` is
  `confirmed`.
- Errors:
  - `404` `not_found` if `{path}` does not resolve to a `Sourced` field. The
    record is left unchanged.

### GET `/api/scenarios`

- Request body: none.
- Success: `200` with a JSON array of scenario id strings (`string[]`), for
  example `["stemi_hero"]`. Leaves the record, flags, and Event_Log unchanged.

### POST `/api/scenario/{id}/play`

Plays a named scenario. The `{id}` path parameter is a scenario id.

- Request body: empty.
- Success: `200` with the resulting `PatientRecord` for a known scenario id.
- Errors:
  - `404` `not_found` if `{id}` does not name a known scenario. The record,
    flags, and Event_Log are left unchanged.

> Stub mode: in the Phase 1 stub, `POST /api/scenario/{id}/play` returns `200`
> with the current mock `PatientRecord` and produces no side effects; an unknown
> id still returns `404`.

## The flag state machine

A flag's `status` (`FlagStatus`) moves forward only:

```
open ──relay──▶ relayed ──ack──▶ acknowledged
```

- `relay` is valid from `open` (→ `relayed`). `ack` is valid from `relayed`
  (→ `acknowledged`).
- `relay` on a flag already `acknowledged` → `409` `conflict` (no skip/reversal).
- `ack` on a flag still `open` → `409` `conflict` (ack before relay).
- An unknown flag `id` on either endpoint → `404` `not_found`.
- Any failed transition (404 or 409) leaves the flag unchanged.

## The `{path}` parameter

`{path}` (used by `POST /api/fields/{path}/confirm`, and as a `med_id` /
`fact.path` value) is a sequence of one or more segments separated by `.`. Each
segment is either:

- a field name (for example `age`), or
- a zero-based, non-negative integer list index (for example `0`).

Examples:

- `age` — the top-level `Sourced` field `age`.
- `meds_given.0` — the first `Sourced[Medication]` entry in the `meds_given`
  list.

## Idempotent repeats

Repeating an operation when the target is already in the requested state is a
no-op success: it returns `200` and appends **no** new Event to the Event_Log.
(Req 7.12)

- `relay` on a flag already `relayed` → `200` with the flag, no new event.
- `ack` on a flag already `acknowledged` → `200` with the flag, no new event.
- `confirm` on a field already `confirmed` → `200` with the field, no new event.

## Event kinds

The Event_Log is the single source of truth; every `Event` has `id`, `ts`
(UTC, millisecond precision), `kind`, and `payload`. The permitted `kind` values
and the shape of each kind's `payload` are: (Req 6.3)

| `kind` | `payload` fields | Notes |
|---|---|---|
| `utterance` | `utterance` | `utterance`: an `Utterance` object (`id`, `text`, `ts`). |
| `fact` | `path`, `value`, `source`, `confidence` | `path`: a `{path}` string (see above). `value`: the extracted value (type depends on the field). `source`: a `SourceRef` object (`utterance_id`, `quote`, `ts`). `confidence`: finite number 0 to 1. |
| `flag_raised` | `flag` | `flag`: a `Flag` object. |
| `flag_relayed` | `flag_id` | `flag_id`: string, the id of the relayed flag. |
| `flag_acked` | `flag_id` | `flag_id`: string, the id of the acknowledged flag. |
| `field_confirmed` | `path` | `path`: a `{path}` string identifying the confirmed `Sourced` field. |

An Event whose `kind` is not listed here, or whose `payload` does not match that
kind's shape, is rejected; the Event_Log is left unchanged and the response
names the offending field and the reason. (Req 6.7)
