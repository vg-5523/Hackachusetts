# Requirements Document

## Introduction

Ambulance Scribe + Safety Check is a hackathon project built in 12 hours using synthetic data only. A paramedic speaks or types during an ambulance run. The system builds a structured patient record in which every field carries provenance (source quote, timestamp, status). A safety engine flags duplicate doses, allergy conflicts, interactions, and contradictions, each with a cited source. The system also generates an SBAR handoff, an ED pre-alert, and a bed/resus checklist.

This spec covers the foundation only: the repository skeleton, steering files, the shared contract (Pydantic schema, matching TypeScript types, API definition), mock data, a FastAPI stub serving all endpoints from mocks, stubbed Python module interfaces, and the README. It does not cover real extraction, safety logic, output generation, or the real UI. Those are built later by parallel contributors against this contract.

Safety principle: the AI never talks to paramedics directly. Each alert carries a `say_to_crew` line that a human relays. The UI shows the disclaimer "decision support, not clinical advice."

## Glossary

- **Repository**: The git repository containing the whole project.
- **System**: The Ambulance Scribe + Safety Check application as a whole (backend and frontend).
- **Backend**: The Python 3.11 FastAPI application located in the `backend` folder.
- **Frontend**: The React + Vite + TypeScript + Tailwind application located in the `frontend` folder.
- **Shared_Contract**: The files in the `shared` folder: `schema.py`, `types.ts`, `api.md`, and `mock_record.json`.
- **Schema_Module**: The file `shared/schema.py` containing the Pydantic models.
- **Types_Module**: The file `shared/types.ts` containing the TypeScript types that mirror the Schema_Module.
- **API_Spec**: The file `shared/api.md` defining all HTTP endpoints.
- **Mock_Data**: The file `shared/mock_record.json` containing one mock PatientRecord and three mock Flags.
- **API_Stub**: The FastAPI application that serves every endpoint in the API_Spec from the Mock_Data.
- **Steering_Files**: The files `.kiro/steering/product.md`, `.kiro/steering/tech.md`, and `.kiro/steering/structure.md`.
- **Sourced**: The generic Pydantic model `Sourced[T]` (and matching TypeScript type) that wraps a value with provenance.
- **Source_Ref**: An object `{utterance_id, quote, ts}` pointing to the utterance that supports a Sourced value.
- **Field_Status**: One of `confirmed`, `unverified`, `conflicted`, `unknown`.
- **Medication**: An object `{drug, dose, route, time, given_by}` describing one administered drug.
- **Vitals_Entry**: An object `{ts, hr, bp, spo2, rr, source}` describing one vitals measurement.
- **PatientRecord**: The structured patient record with the fields defined in Requirement 4.
- **Flag**: A safety alert with the fields defined in Requirement 5.
- **Flag_Type**: One of `duplicate_dose`, `allergy_conflict`, `interaction`, `contradiction`, `missing_info`.
- **Flag_Severity**: One of `critical`, `warn`, `info`.
- **Flag_Status**: One of `open`, `relayed`, `acknowledged`.
- **Event**: An object `{id, ts, kind, payload}` appended to the Event_Log.
- **Event_Log**: The append-only in-memory list of Events that is the single source of truth. The PatientRecord is derived from the Event_Log.
- **Utterance**: A unit of paramedic speech or typed text with `id`, `text`, and `ts`, defined as a model in the Schema_Module.
- **Extraction_Module**: The Python package `backend/extraction/`, whose public functions are exposed in `backend/extraction/__init__.py`.
- **Safety_Module**: The Python package `backend/safety/`, whose public functions are exposed in `backend/safety/__init__.py`.
- **Outputs_Module**: The Python package `backend/outputs/`, whose public functions are exposed in `backend/outputs/__init__.py`.
- **Store_Module**: The Python package `backend/store/`, whose public functions are exposed in `backend/store/__init__.py`.
- **LLM_Wrapper**: The single function in `backend/llm.py` through which all LLM calls pass.
- **SBAR**: A Situation-Background-Assessment-Recommendation handoff text.
- **Pre_Alert**: The ED pre-alert message generated from the PatientRecord.
- **Checklist**: The bed/resus preparation checklist generated from the PatientRecord.
- **Owner_Folder**: A folder assigned to one owner per the Steering_Files: `shared` (Contract), `backend/extraction` (Account A), `backend/safety` (Account B), `frontend` (Account C), and `backend/store`, `backend/outputs`, `scenarios`, and `eval` (Account D).
- **Synthetic_Data**: Fabricated data containing no real patient information.

## Requirements

### Requirement 1: Steering Files

**User Story:** As a contributor, I want steering files that describe the product, stack, and folder ownership, so that every contributor and every AI agent works from the same rules.

#### Acceptance Criteria

1. THE Repository SHALL contain the Steering_Files `.kiro/steering/product.md`, `.kiro/steering/tech.md`, and `.kiro/steering/structure.md`, each as a non-empty Markdown file.
2. THE `product.md` file SHALL contain a separate heading for each of the following topics: the product purpose (stated in 1 to 3 sentences), the provenance-on-every-field principle, the safety principle that the AI never talks to paramedics directly, the `say_to_crew` relay mechanism, the Synthetic_Data-only constraint, and the disclaimer.
3. THE `product.md` file SHALL contain the exact text "decision support, not clinical advice".
4. THE `tech.md` file SHALL name each of the following items at least once: Python 3.11, FastAPI, Pydantic, React, Vite, TypeScript, Tailwind, Server-Sent Events, the in-memory event-sourced store, the `LLM_API_KEY` environment variable, the LLM_Wrapper located at `backend/llm.py`, and the browser Web Speech API with typed-input fallback.
5. THE `structure.md` file SHALL list each of the folders `shared` (Owner: Contract), `backend/extraction` (Owner: Account A), `backend/safety` (Owner: Account B), `backend/store` (Owner: Account D), `backend/outputs` (Owner: Account D), `frontend` (Owner: Account C), `scenarios` (Owner: Account D), `eval` (Owner: Account D), and `.kiro` (Owner: Contract) with exactly one purpose statement of 1 to 2 sentences and exactly one named Owner.
6. THE `structure.md` file SHALL state the rule that each contributor edits only files inside the contributor's Owner_Folder.
7. THE `structure.md` file SHALL state that a change to the Shared_Contract requires agreement from all contributors before the change is made.
8. THE Steering_Files SHALL reference only paths that exist in the repository skeleton.
9. IF a Steering_File references a path that does not exist in the repository skeleton, THEN THE Repository SHALL be treated as non-conforming to this requirement, and the reviewer SHALL correct either the reference or the skeleton before the Steering_File is accepted.
10. THE Steering_Files SHALL each be no longer than 200 lines.

### Requirement 2: Repository Skeleton

**User Story:** As a contributor, I want a predefined folder layout with placeholder files, so that each person can start in a separate folder without merge conflicts.

#### Acceptance Criteria

1. THE Repository SHALL contain the top-level folders `backend`, `frontend`, `shared`, `scenarios`, and `eval`, and each of the files named in criteria 2, 3, 5, and 8 SHALL reside only within its named folder.
2. THE `backend` folder SHALL contain, at the folder root, `main.py`, `llm.py`, and a `requirements.txt`, and SHALL contain the packages `extraction/`, `safety/`, `store/`, and `outputs/`, each with an `__init__.py`, where the `requirements.txt` is one in which every listed dependency is pinned to an exact version using the `==` operator and no entry uses a range operator (`>=`, `<=`, `~=`, `^`, `*`).
3. THE `frontend` folder SHALL contain a Vite + React + TypeScript + Tailwind project that includes a `package.json` and installs without errors using the package manager's standard install command.
4. WHEN a contributor runs the frontend install command followed by the frontend development server start command from the `frontend` folder, THE `frontend` project SHALL start without errors and serve a page that displays the exact text "decision support, not clinical advice." within 30 seconds of the start command.
5. THE `shared` folder SHALL contain `schema.py`, `types.ts`, `api.md`, and `mock_record.json`, where `mock_record.json` is syntactically valid JSON that parses without errors.
6. THE Repository SHALL contain a `.gitignore` at the repository root that excludes Python virtual environment folders, `node_modules`, frontend build output, and `.env` files, and does not exclude `.env.example`.
7. THE Repository SHALL contain a `.env.example` file at the repository root that contains the line `LLM_API_KEY=` with an empty value and contains no other non-empty secret values.
8. THE `scenarios` folder and the `eval` folder SHALL each contain a placeholder `README.md`.

### Requirement 3: Sourced Provenance Model

**User Story:** As a receiving clinician, I want every record field to carry its source quote, timestamp, and status, so that I can verify where each value came from.

#### Acceptance Criteria

1. THE Schema_Module SHALL define Sourced as a generic model with the required fields `value` (type T or null), `status` (Field_Status), `confidence` (finite number), and `sources` (list of 0 to 20 Source_Ref entries).
2. THE Schema_Module SHALL define Source_Ref with the required fields `utterance_id` (string of 1 to 128 characters), `quote` (string of 1 to 1000 characters), and `ts` (ISO 8601 timestamp that includes a UTC offset).
3. THE Schema_Module SHALL constrain `confidence` to the inclusive range 0 to 1.
4. IF a Sourced `confidence` value is less than 0, greater than 1, not a finite number (NaN or infinite), or not a number type, THEN THE Schema_Module SHALL reject the value with a validation error identifying the `confidence` field and SHALL NOT create a Sourced instance.
5. IF a Sourced `status` value is not a member of the Field_Status set, THEN THE Schema_Module SHALL reject the value with a validation error identifying the `status` field and SHALL NOT create a Sourced instance.
6. THE Types_Module SHALL define a Sourced type and a Source_Ref type with the same field names, the same required or nullable designation for each field, and a value type for each field that accepts the same set of values as the Schema_Module.
7. IF a Sourced or Source_Ref input is missing a required field, has a `sources` list with more than 20 entries, has a `utterance_id` or `quote` that is empty or exceeds its maximum length, or has a `ts` that is not a valid ISO 8601 timestamp with a UTC offset, THEN THE Schema_Module SHALL reject the input with a validation error identifying each offending field and SHALL NOT create a partial instance.

### Requirement 4: Patient Record Model

**User Story:** As a developer, I want a single typed PatientRecord shape, so that extraction, safety, outputs, and UI all agree on the data.

#### Acceptance Criteria

1. THE Schema_Module SHALL define Medication with the fields `drug`, `dose`, `route`, `time`, and `given_by`, where each field is a string of 0 to 200 characters or null.
2. THE Schema_Module SHALL define Vitals_Entry with the fields `ts` (a timestamp), `hr` (integer, 0 to 300 beats per minute or null), `bp` (a systolic/diastolic string or null), `spo2` (integer, 0 to 100 percent or null), `rr` (integer, 0 to 100 breaths per minute or null), and `source` (a string of 0 to 200 characters).
3. THE Schema_Module SHALL define PatientRecord with the fields `age`, `sex`, `chief_complaint`, `suspected_condition`, `acuity_esi`, `allergies`, `meds_given`, `vitals_timeline`, `eta`, and `notes`, where `notes` is a string of 0 to 5,000 characters.
4. THE Schema_Module SHALL type `allergies` as Sourced of list of string, `meds_given` as a list of Sourced of Medication, and `vitals_timeline` as a list of Vitals_Entry, with each list holding 0 to 100 items.
5. THE Schema_Module SHALL type `age`, `sex`, `chief_complaint`, `suspected_condition`, `acuity_esi`, and `eta` as Sourced values so that each carries provenance.
6. THE Schema_Module SHALL constrain `acuity_esi` values to integers from 1 to 5 inclusive.
7. WHEN a PatientRecord is created with no arguments, THE Schema_Module SHALL produce a valid empty PatientRecord in which every Sourced field has `value` null, `status` `unknown`, `confidence` 0, and an empty `sources` list, `allergies`, `meds_given`, and `vitals_timeline` are empty lists, and `notes` is an empty string.
8. THE Types_Module SHALL define Medication, Vitals_Entry, and PatientRecord with field names and value types equivalent to the Schema_Module.
9. FOR ALL valid PatientRecord objects, including the empty PatientRecord and records with up to 100 items in each list, serializing to JSON then parsing then serializing SHALL produce an equivalent object in which every field value is equal to the original (round-trip property).
10. IF an `acuity_esi` value is not an integer from 1 to 5 inclusive, THEN THE Schema_Module SHALL reject the input with a validation error that identifies `acuity_esi` as the invalid field and SHALL leave any existing PatientRecord unchanged.
11. IF a Sourced `confidence` value is not a number from 0 to 1 inclusive, THEN THE Schema_Module SHALL reject the input with a validation error that identifies `confidence` as the invalid field and SHALL leave any existing PatientRecord unchanged.
12. IF JSON input to the Schema_Module is missing a required field, contains a field of the wrong type, or exceeds a stated length or item limit, THEN THE Schema_Module SHALL reject the input with a validation error that identifies the offending field and SHALL NOT produce a PatientRecord.

### Requirement 5: Flag Model

**User Story:** As a paramedic crew member relaying alerts, I want each flag to include a message, a line to say, and a cited source, so that I can act on it and trust it.

#### Acceptance Criteria

1. THE Schema_Module SHALL define Flag with the fields `id`, `type`, `severity`, `message`, `say_to_crew`, `evidence`, `source_ref`, and `status`, where `id`, `type`, `severity`, `message`, `say_to_crew`, `evidence`, and `source_ref` are required and `status` is optional.
2. THE Schema_Module SHALL type `type` as Flag_Type, `severity` as Flag_Severity, `status` as Flag_Status, `id` as a string of 1 to 64 characters, `message` as a string of 1 to 500 characters, `say_to_crew` as a string of 1 to 280 characters, `evidence` as a list of 0 to 10 quote strings of 1 to 500 characters each, and `source_ref` as an object `{name, url}` where `name` is a string of 1 to 200 characters and `url` is an absolute http or https URL of at most 2048 characters.
3. WHEN a Flag is created without a `status` value, THE Schema_Module SHALL set `status` to `open`.
4. IF a Flag is supplied with a `type`, `severity`, or `status` outside the defined sets, THEN THE Schema_Module SHALL reject the Flag with a validation error that identifies the offending field and SHALL NOT create or store the Flag.
5. IF a Flag is supplied with a required field missing, or with a field value that violates the type or length limits in criterion 2, THEN THE Schema_Module SHALL reject the Flag with a validation error that identifies each offending field and SHALL NOT create or store the Flag.
6. THE Types_Module SHALL define Flag, Flag_Type, Flag_Severity, and Flag_Status with the same field names, field optionality, and enumerated string values as the Schema_Module.
7. FOR ALL valid Flag objects, serializing to JSON, parsing the result, and serializing again SHALL produce a parsed object with all field values equal to the original and a second JSON output identical to the first (round-trip property).
8. WHEN the Safety_Module creates a Flag, THE Safety_Module SHALL set the Flag `id` to `f"{type}:{sha1(type + rule_key + sorted evidence)[:12]}"`, where `rule_key` identifies the safety rule that raised the Flag, so that Flags with empty `evidence` from different rules receive different `id` values and every `id` remains within the 64-character limit of criterion 2.

### Requirement 6: Event Model

**User Story:** As a developer, I want an event log as the single source of truth, so that the record can be derived and replayed.

#### Acceptance Criteria

1. THE Schema_Module SHALL define Event with the required fields `id` (string, 1 to 128 characters), `ts` (UTC timestamp with millisecond precision), `kind` (string, 1 to 64 characters), and `payload` (object, empty object permitted, serialized size at most 64 KB).
2. THE Types_Module SHALL define Event with the same field names, the same required status for each field, and value types that map one-to-one to those of the Schema_Module.
3. THE `shared/api.md` file SHALL list every permitted Event `kind` value and, for each kind, the name, value type, and required or optional status of every payload field.
4. THE Backend SHALL derive every PatientRecord field value solely from Events in the Event_Log, with no PatientRecord field value that cannot be traced to at least one Event.
5. WHEN the Event_Log is replayed from the first Event in append order, THE Backend SHALL produce a PatientRecord whose every field is deeply equal to the corresponding field of the PatientRecord produced by live processing of the same Events.
6. FOR ALL valid Event objects, serializing to JSON, parsing, and serializing again SHALL produce output deeply equal, field by field, to the first serialization (round-trip property).
7. IF an Event is missing a required field, has a field of the wrong value type, has a `kind` not listed in `shared/api.md`, or has a `payload` that does not match the payload shape of its `kind`, THEN THE Backend SHALL reject the Event, leave the Event_Log unchanged, and return an error identifying the offending field and the reason for rejection.
8. IF an Event is submitted with an `id` equal to the `id` of an Event already in the Event_Log, THEN THE Backend SHALL reject the Event as a duplicate, leave the Event_Log unchanged, and return an error indicating a duplicate `id`.
9. WHEN a valid Event is accepted, THE Backend SHALL append it to the end of the Event_Log without modifying or deleting any existing Event.

### Requirement 7: API Specification

**User Story:** As a frontend or backend contributor, I want a written API contract, so that modules can be built in parallel.

#### Acceptance Criteria

1. THE API_Spec SHALL define `POST /api/utterance` with request body `{text, ts}`, where `text` is a non-empty string of 1 to 2,000 characters and `ts` is an ISO 8601 UTC timestamp string, and a description that the endpoint runs the extraction and safety pipeline on the submitted utterance.
2. THE API_Spec SHALL define `GET /api/stream` as an SSE endpoint that emits the event types `record`, `flags`, and `clocks`, and SHALL specify that a `record` or `flags` event is emitted within 1 second of the corresponding state change.
3. THE API_Spec SHALL define `GET /api/record` and `GET /api/flags` with success response shapes that reference Schema_Module models, and SHALL define `GET /api/sbar`, `GET /api/preAlert`, and `GET /api/checklist`.
4. THE API_Spec SHALL define `POST /api/flags/{id}/relay`, `POST /api/flags/{id}/ack`, and `POST /api/fields/{path}/confirm`, each with an empty request body and a success response that reflects the updated flag or field.
5. THE API_Spec SHALL define `GET /api/events` returning the complete Event_Log for replay as a list ordered from oldest to newest, where each entry includes a timestamp.
6. THE API_Spec SHALL state for each endpoint the HTTP method, path, request body shape, success response shape, and error responses.
7. THE API_Spec SHALL define the JSON payload of each SSE event type by reference to Schema_Module models.
8. WHILE a client is connected to `GET /api/stream`, THE API_Spec SHALL define that a `clocks` event is emitted every 1 second, and that its payload contains `contact_ts`, `eta`, and `door_to_ecg_target_ts`, and, for each medication, a `med_id` equal to the medication's field path (for example `meds_given.0`), the timestamp of the last dose, and the elapsed seconds since the last dose as a non-negative integer.
9. THE API_Spec SHALL define the `{path}` parameter in `POST /api/fields/{path}/confirm` as a sequence of one or more segments separated by `.`, where a segment is either a field name or a zero-based non-negative integer list index, with at least two examples (for example `age` and `meds_given.0`).
10. THE API_Spec SHALL define the response shapes of `GET /api/sbar` (string), `GET /api/preAlert` (string), and `GET /api/checklist` (list of string), and SHALL specify that each returns an empty string or an empty list, respectively, when no content is available.
11. IF a request body fails validation, a referenced flag `id` or field `{path}` does not exist, or the extraction and safety pipeline fails, THEN THE API_Spec SHALL define an error response that indicates the failure category (validation, not found, or processing) and SHALL specify that the Record, flags, and Event_Log remain unchanged by the failed request.
12. WHEN a client repeats `POST /api/flags/{id}/relay`, `POST /api/flags/{id}/ack`, or `POST /api/fields/{path}/confirm` for a flag or field already in the target state, THE API_Spec SHALL define that the endpoint returns the success response without adding a duplicate entry to the Event_Log.
13. THE API_Spec SHALL define `GET /api/scenarios` with no request body and a success response that is a list of scenario id strings.
14. THE API_Spec SHALL define `POST /api/scenario/{id}/play` with an empty request body, a success response of PatientRecord, and an HTTP 404 not found error response when `{id}` does not name a known scenario.

### Requirement 8: Mock Data

**User Story:** As a frontend contributor, I want a realistic mock record and mock flags, so that I can build the UI immediately.

#### Acceptance Criteria

1. THE Mock_Data SHALL contain exactly one PatientRecord in which every field holds a non-empty Synthetic_Data value, except that the value of a Sourced field with Field_Status `unknown` MAY be null.
2. THE Mock_Data SHALL contain exactly three Flags.
3. THE Mock_Data SHALL include Flags covering at least three different Flag_Types and at least two different Flag_Severities.
4. THE Mock_Data SHALL include, within the PatientRecord, at least one Sourced field for each Field_Status value: `confirmed`, `unverified`, `conflicted`, and `unknown`.
5. THE Mock_Data SHALL include between two and ten Vitals_Entry items and between two and ten Medication entries, inclusive.
6. THE Mock_Data SHALL include for each Flag a `say_to_crew` of 1 to 200 characters and between zero and five `evidence` quotes, each of 1 to 300 characters.
7. WHEN the Mock_Data is loaded through the Schema_Module, THE Schema_Module SHALL validate the PatientRecord and all three Flags with zero validation errors.
8. THE Mock_Data SHALL contain Synthetic_Data only, with no real patient, person, or institution names, identifiers, contact details, or dates of birth.
9. THE Mock_Data SHALL include for each Flag a `source_ref` with a non-empty `name` and a `url` that is a well-formed absolute URL using a reserved example domain (`example.com`, `example.org`, or `example.net`).

### Requirement 9: FastAPI Stub

**User Story:** As a contributor, I want a running backend stub that serves every endpoint from mocks, so that I can integrate before real logic exists.

#### Acceptance Criteria

1. THE API_Stub SHALL implement every endpoint defined in the API_Spec, including each endpoint's HTTP method, path, and response shape.
2. WHEN a GET request is sent to `/api/record`, `/api/flags`, `/api/sbar`, `/api/preAlert`, `/api/checklist`, or `/api/events`, THE API_Stub SHALL respond within 500 milliseconds with HTTP 200 and a JSON body matching the API_Spec response shape, populated from the Mock_Data.
3. WHEN a client connects to `GET /api/stream`, THE API_Stub SHALL send, in this order, an initial `record` event, an initial `flags` event, and an initial `clocks` event within 1 second of connection, and THEN SHALL send one `clocks` event every 1 second (±100 milliseconds) until the client disconnects.
4. WHEN a body `{text, ts}` is sent to `POST /api/utterance`, where `text` is a string of 1 to 2,000 characters and `ts` conforms to the type defined in the API_Spec, THE API_Stub SHALL respond within 500 milliseconds with HTTP 200 and the current mock PatientRecord.
5. IF the body sent to `POST /api/utterance` lacks `text` or `ts`, has an empty `text`, has a `text` longer than 2,000 characters, or has a `text` or `ts` of a type that does not match the API_Spec, THEN THE API_Stub SHALL respond with HTTP 422 and an error body identifying the invalid field, and SHALL leave the mock PatientRecord unchanged.
6. WHEN `POST /api/flags/{id}/relay` is sent with the id of an existing Flag whose status is `open` or `relayed`, THE API_Stub SHALL respond with HTTP 200 and the Flag with `status` set to `relayed`.
7. WHEN `POST /api/flags/{id}/ack` is sent with the id of an existing Flag whose status is `relayed` or `acknowledged`, THE API_Stub SHALL respond with HTTP 200 and the Flag with `status` set to `acknowledged`.
8. IF a request to `/api/flags/{id}/relay` or `/api/flags/{id}/ack` names a Flag id that does not exist, THEN THE API_Stub SHALL respond with HTTP 404 and an error body indicating that the Flag was not found, and SHALL leave all Flags unchanged.
9. WHEN `POST /api/fields/{path}/confirm` is sent with a path that resolves to a Sourced field in the mock PatientRecord, THE API_Stub SHALL respond with HTTP 200 and the targeted Sourced field with `status` set to `confirmed`.
10. IF `POST /api/fields/{path}/confirm` is sent with a path that does not resolve to a Sourced field in the mock PatientRecord, THEN THE API_Stub SHALL respond with HTTP 404 and an error body indicating that the field was not found, and SHALL leave the mock PatientRecord unchanged.
11. THE API_Stub SHALL set the allowed origins of its cross-origin responses, including responses to preflight requests, to exactly the Frontend development server origins `http://localhost:5173` and `http://127.0.0.1:5173`, and SHALL NOT allow any other origin.
12. WHEN the API_Stub builds a response body, THE API_Stub SHALL validate the body against the Schema_Module models before sending it.
13. IF a response body fails validation against the Schema_Module models, THEN THE API_Stub SHALL respond with HTTP 500 and an error body indicating a response validation failure, and SHALL NOT send the invalid body.
14. WHILE `LLM_API_KEY` is unset or empty, THE API_Stub SHALL start and respond to every request defined in the API_Spec as specified in all other criteria in this requirement, without making outbound network calls to any LLM service.
15. IF a request to `/api/flags/{id}/relay` names a Flag whose status is `acknowledged`, or a request to `/api/flags/{id}/ack` names a Flag whose status is `open`, THEN THE API_Stub SHALL respond with HTTP 409 and an error body indicating an invalid state transition, and SHALL leave the Flag unchanged.
16. WHEN a GET request is sent to `/api/scenarios`, THE API_Stub SHALL respond with HTTP 200 and a list of scenario id strings, leaving the mock PatientRecord, the Flags, and the Event_Log unchanged.
17. WHEN `POST /api/scenario/{id}/play` is sent with a known scenario id, THE API_Stub SHALL respond with HTTP 200 and the current mock PatientRecord, leaving the mock PatientRecord, the Flags, and the Event_Log unchanged.
18. IF `POST /api/scenario/{id}/play` is sent with an unknown scenario id, THEN THE API_Stub SHALL respond with HTTP 404 and an error body indicating that the scenario was not found, and SHALL leave the mock PatientRecord, the Flags, and the Event_Log unchanged.

### Requirement 10: Python Module Interfaces

**User Story:** As a backend contributor, I want stubbed function signatures for extraction, safety, and outputs, so that each module can be implemented independently against a fixed interface.

#### Acceptance Criteria

1. THE Extraction_Module SHALL define `process_utterance(utterance, record)` with type annotations on both parameters and the return value, taking an Utterance and a PatientRecord and returning a PatientRecord.
2. THE Safety_Module SHALL define `evaluate(record)` with type annotations on the parameter and the return value, taking a PatientRecord and returning a list of Flag.
3. THE Outputs_Module SHALL define `make_sbar(record, flags)` with type annotations on both parameters and the return value, taking a PatientRecord and a list of Flag and returning a string.
4. THE Outputs_Module SHALL define `make_checklist(record)` with type annotations on the parameter and the return value, taking a PatientRecord and returning a list of string.
5. THE Outputs_Module SHALL define `make_pre_alert(record, flags)` with type annotations on both parameters and the return value, taking a PatientRecord and a list of Flag and returning a string.
6. THE LLM_Wrapper SHALL be defined as exactly one function named `call_llm` in `backend/llm.py`, with type annotations, taking a prompt string and returning a string.
7. WHEN `process_utterance` is called, THE Extraction_Module stub SHALL return the same PatientRecord object it received, with no field modified.
8. WHEN `evaluate` is called, THE Safety_Module stub SHALL return an empty list.
9. WHEN `make_sbar` or `make_pre_alert` is called, THE Outputs_Module stub SHALL return a non-empty string.
10. IF `call_llm` is called while `LLM_API_KEY` is unset or set to an empty string, THEN THE LLM_Wrapper SHALL raise an exception whose message contains the text `LLM_API_KEY` before making any network request.
11. THE Extraction_Module, Safety_Module, and Outputs_Module SHALL import the Utterance, PatientRecord, and Flag data models from `shared/schema.py`.
12. WHEN `call_llm` is called, THE LLM_Wrapper SHALL read the API key from the `LLM_API_KEY` environment variable at call time.
13. WHEN `make_checklist` is called, THE Outputs_Module stub SHALL return a list containing at least one item, where every item is a string.
14. WHILE `LLM_API_KEY` is unset, THE Extraction_Module, Safety_Module, and Outputs_Module stubs SHALL import and execute without raising an exception.

### Requirement 11: Human-in-the-Loop Safety Contract

**User Story:** As a clinical stakeholder, I want the contract to enforce that alerts reach crew only through a human, so that the AI never instructs paramedics directly.

#### Acceptance Criteria

1. THE Flag model SHALL require a `say_to_crew` string of 1 to 280 characters that contains at least one non-whitespace character.
2. IF a Flag is supplied with a `say_to_crew` that is missing, empty, whitespace-only, or longer than 280 characters, THEN THE Schema_Module SHALL reject the Flag with a validation error that identifies `say_to_crew` as the invalid field, and THE Schema_Module SHALL NOT create or store the Flag.
3. THE API_Spec SHALL state that a Flag moves from `open` to `relayed` only through `POST /api/flags/{id}/relay` and from `relayed` to `acknowledged` only through `POST /api/flags/{id}/ack`.
4. THE API_Spec SHALL state that no endpoint delivers text, audio, or push notification directly to a paramedic or to any crew-facing device or channel.
5. THE Frontend SHALL display the disclaimer "decision support, not clinical advice." on every screen, visible without scrolling or user interaction.
6. THE `product.md` file SHALL state that the Frontend presents each `say_to_crew` line to a human operator, who decides whether and how to relay the line to the crew.
7. IF a request calls `POST /api/flags/{id}/relay` on a Flag whose status is `acknowledged`, or calls `POST /api/flags/{id}/ack` on a Flag whose status is `open`, THEN THE API_Spec SHALL state that the request is rejected with an error indicating the invalid state transition and that the Flag's status remains unchanged.

### Requirement 12: Type Parity Between Python and TypeScript

**User Story:** As a developer, I want the TypeScript types to match the Pydantic models exactly, so that the frontend and backend never disagree on shape.

#### Acceptance Criteria

1. THE Types_Module SHALL export exactly one TypeScript type for each Pydantic model and each enumeration defined in the Schema_Module, using the same type name as in the Schema_Module, and SHALL export no additional types that have no counterpart in the Schema_Module.
2. THE Types_Module SHALL use, for every Pydantic model, field names identical (case-sensitive) to the Schema_Module, SHALL use enumeration string values identical (case-sensitive) to the Schema_Module, and SHALL declare a field as nullable if and only if the corresponding Schema_Module field accepts None.
3. WHEN `tsc --noEmit` is run on a file that assigns the Mock_Data JSON to the TypeScript types `PatientRecord` and `Flag[]`, THE TypeScript compiler SHALL exit with status 0 and report zero type errors.
4. THE Types_Module SHALL be hand-written to match the Schema_Module.

### Requirement 13: README and Run Instructions

**User Story:** As a hackathon teammate, I want clear run instructions, so that I can start the backend stub and the frontend within minutes.

#### Acceptance Criteria

1. THE README SHALL describe the product in no more than 5 sentences in its first section, and THE README SHALL include the exact disclaimer text "decision support, not clinical advice." in that section.
2. THE README SHALL list, in execution order and in fenced code blocks, the commands to create a Python 3.11 virtual environment, activate it, install backend dependencies, and start the API_Stub with uvicorn, with activation commands given for both PowerShell and a POSIX shell.
3. THE README SHALL list, in execution order and in fenced code blocks, the commands to install frontend dependencies and start the Vite development server.
4. THE README SHALL document the `LLM_API_KEY` environment variable by stating its purpose and whether it is required for the API_Stub to start. THE README SHALL also document the `.env.example` file by stating that it is copied to create the local environment file and that real key values are never committed.
5. THE README SHALL link to each Steering_File and to the API_Spec, and each link SHALL resolve to an existing file in the repository.
6. THE README SHALL state the Owner_Folder rule and SHALL list the top-level folders of the repository, each with a one-line description and its owner.
7. THE README SHALL list the commands to run the Schema_Module validation of the Mock_Data and the `tsc --noEmit` type check of the Mock_Data, and SHALL state the observable result that indicates a pass and the observable result that indicates a failure for each.
8. WHEN the API_Stub and the Vite development server are started per the README, THE README SHALL state the local URL, including the port, where each is reachable.
9. THE README SHALL state the required runtime versions for the backend (Python 3.11) and for the frontend toolchain before the first install command.

### Requirement 14: Version Control

**User Story:** As a team, I want the skeleton committed to git, so that all contributors start from the same baseline.

#### Acceptance Criteria

1. WHEN the skeleton, Shared_Contract, Steering_Files, and README are complete, THE Repository SHALL contain a git commit on the default branch that includes every file of the skeleton, Shared_Contract, Steering_Files, and README, and a `git status` run immediately afterward SHALL report zero uncommitted changes to those files.
2. THE Repository SHALL exclude all `.env` files (including variants such as `.env.local` and `.env.production`) and files containing secrets from the commit, and THE Repository SHALL list these patterns in a `.gitignore` file that is included in the commit.

### Requirement 15: Synthetic Data Only

**User Story:** As a project owner, I want the repository free of real patient data, so that the hackathon work raises no privacy concerns.

#### Acceptance Criteria

1. THE Repository SHALL contain Synthetic_Data only, with zero records in any tracked file that are copied from, derived from, or re-identifiable to a real individual.
2. THE README and `product.md` file SHALL each contain at least one statement that the project uses Synthetic_Data only and contains no real patient data.
3. THE Mock_Data SHALL contain, in every name field, either a fictional name or no value, and in every identifier field (including medical record number, date of birth, phone number, address, and email), either a fictional value or no value, where a fictional value is one generated for this project and not copied from any real-world source.
4. IF a record in the Repository is identified as real patient data or cannot be confirmed as fictional, THEN THE Repository SHALL have that record removed from all tracked files before the next merge into the default branch.