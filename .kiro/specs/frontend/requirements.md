# Requirements Document

## Introduction

This feature is the Ambulance Scribe + Safety Check frontend: a single-screen React
application (React + Vite + TypeScript + Tailwind) that a human operator uses during an
ambulance run. The Frontend consumes the existing stub backend over the shared HTTP +
SSE contract and renders the patient record, safety flags, live clocks, and generated
outputs. It imports all data types from `shared/types.ts` and treats `shared/` and the
backend as read-only. The Frontend only surfaces decision support to a human operator;
it never sends anything to the paramedic crew.

## Glossary

- **Frontend**: The React + Vite + TypeScript + Tailwind single-page application under `frontend/`.
- **API_Base**: The backend base URL, read from the `VITE_API_BASE` environment variable, defaulting to `http://localhost:8000`.
- **Stream**: The SSE connection to `GET /api/stream`, which emits `record`, `flags`, and `clocks` events.
- **Provenance_Drawer**: A panel that shows the source quote(s), timestamp(s), and status for a selected record field.
- **Say_To_Crew_Box**: The flag control that presents the `say_to_crew` line and the Relayed and Acknowledged actions.
- **Disclaimer**: The exact footer text "decision support, not clinical advice. Synthetic data only."

## Requirements

### Requirement 1: Glanceable single-screen layout

**User Story:** As an operator, I want one dark, high-contrast screen sized for a projector, so that I can read the run at a glance.

#### Acceptance Criteria

1. THE Frontend SHALL render a single screen laid out as three side-by-side columns in left-to-right order: a left transcript column, a center patient-record column, and a right flags column, with all three columns visible simultaneously without scrolling.
2. THE Frontend SHALL render all screen states using a dark theme in which the background is darker than the foreground text and every text element against its background meets a contrast ratio of at least 7:1.
3. WHILE the viewport is exactly 1280x720 pixels, THE Frontend SHALL display the complete layout, including all three columns and the Disclaimer footer, fully within the viewport without requiring scrolling, zooming, or any user interaction.
4. THE Frontend SHALL display the Disclaimer footer containing the exact text "decision support, not clinical advice. Synthetic data only." in every screen state.
5. WHILE the Disclaimer footer is displayed, THE Frontend SHALL keep it visible within the viewport without requiring scrolling or interaction.

### Requirement 2: Transcript and input (left column)

**User Story:** As an operator, I want to capture speech or typed text and replay scenarios, so that I can drive and follow the run.

#### Acceptance Criteria

1. WHEN one or more utterances exist, THE Frontend SHALL display a transcript of those utterances in the left column ordered by ascending timestamp, and SHALL render each newly received utterance within 1 second of receiving it.
2. WHILE no utterances exist, THE Frontend SHALL display an empty-transcript placeholder in the left column.
3. WHERE the Web Speech API is available, THE Frontend SHALL provide a mic button that performs continuous speech capture and posts each non-empty recognized result as an `UtteranceRequest` (text of 1 to 2000 characters and ts as an ISO 8601 timestamp with UTC offset) to `POST /api/utterance`.
4. IF the Web Speech API is unavailable or speech capture permission is denied or fails, THEN THE Frontend SHALL keep the typed-input textarea available as the input fallback and SHALL display an indication that speech capture is unavailable.
5. THE Frontend SHALL display a typed-input textarea, always present regardless of Web Speech API availability, that posts its content as an `UtteranceRequest` (text of 1 to 2000 characters and ts as an ISO 8601 timestamp with UTC offset) to `POST /api/utterance`.
6. IF the operator submits typed input whose text is empty or exceeds 2000 characters, THEN THE Frontend SHALL reject the submission, SHALL NOT post to `POST /api/utterance`, SHALL retain the entered text in the textarea, and SHALL display a validation message indicating the allowed length is 1 to 2000 characters.
7. IF a `POST /api/utterance` request fails, THEN THE Frontend SHALL retain the submitted text, SHALL display an error indication that the utterance was not recorded, and SHALL allow the operator to retry.
8. WHEN the operator activates the play-scenario control, THE Frontend SHALL send `POST /api/scenario/{id}/play`.
9. IF a `POST /api/scenario/{id}/play` request fails, THEN THE Frontend SHALL display an error indication that the scenario did not start.
10. WHILE a Provenance_Drawer is open, THE Frontend SHALL highlight the source utterance of the displayed field in the transcript.

### Requirement 3: Patient record card with provenance (center column)

**User Story:** As an operator, I want each record field shown with its status and sources, so that I can trust and confirm values.

#### Acceptance Criteria

1. THE Frontend SHALL display each `PatientRecord` field with a status badge showing exactly one of `confirmed`, `unverified`, `conflicted`, or `unknown`.
2. THE Frontend SHALL display every `PatientRecord` field together with its status badge, and SHALL NOT display any field value without its associated status badge.
3. WHEN the operator selects a record field, THE Frontend SHALL open a Provenance_Drawer showing every source for that field, each listed with its source quote and its offset-aware ISO 8601 timestamp.
4. WHILE a field status is `conflicted`, THE Frontend SHALL display all of the field's sources in the Provenance_Drawer, one entry per source.
5. WHERE a field status is `unverified`, THE Frontend SHALL display a Confirm control that sends a confirm request for that field's path to `POST /api/fields/{path}/confirm`.
6. WHEN the operator activates the Confirm control and the confirm request succeeds, THE Frontend SHALL update the field's status badge to `confirmed` using the returned field value.
7. IF the confirm request fails because the field path does not resolve, THEN THE Frontend SHALL display an error indication identifying that the field was not found, SHALL retain the field's existing status badge unchanged, and SHALL keep the Confirm control available for retry.
8. THE Frontend SHALL address each administered medication using the field path `meds_given.N`, where `N` is the zero-based list index.

### Requirement 4: Safety flags and human-in-the-loop relay (right column)

**User Story:** As an operator, I want to review flags and relay them to the crew myself, so that the machine never speaks to the crew directly.

#### Acceptance Criteria

1. THE Frontend SHALL display flags sorted by severity in the order `critical`, then `warn`, then `info`, and SHALL display flags of equal severity in ascending order of their first-appearance time (oldest first).
2. THE Frontend SHALL display each flag's `message`, all `evidence` quotes, a `source_ref` link, and a Say_To_Crew_Box containing the flag's `say_to_crew` line verbatim, where that line is between 1 and 280 characters.
3. WHILE a flag's status is `open`, THE Frontend SHALL keep the Relayed control enabled and the Acknowledged control disabled.
4. WHILE a flag's status is `relayed`, THE Frontend SHALL keep the Relayed control disabled and the Acknowledged control enabled.
5. WHILE a flag's status is `acknowledged`, THE Frontend SHALL keep both the Relayed control and the Acknowledged control disabled.
6. WHEN the operator activates the Relayed control, THE Frontend SHALL send `POST /api/flags/{id}/relay` for that flag's `id`.
7. WHEN the operator activates the Acknowledged control, THE Frontend SHALL send `POST /api/flags/{id}/ack` for that flag's `id`.
8. WHEN a relay or acknowledge request returns a success response, THE Frontend SHALL display the `status` value and the transition timestamp carried by the returned `Flag`.
9. IF a relay or acknowledge request returns a 409 conflict response, THEN THE Frontend SHALL leave the affected flag's displayed status unchanged and display a conflict message from the `ErrorBody` `detail`.
10. WHEN a flag with severity `critical` is displayed for the first time for that flag `id`, THE Frontend SHALL animate the flag into view and play an audible alert exactly once for that `id`.

### Requirement 5: Top bar clocks

**User Story:** As an operator, I want live running timers, so that I can track time-critical thresholds.

#### Acceptance Criteria

1. WHEN a `clocks` event is received on the Stream, THE Frontend SHALL update the top bar display from the event's `Clocks` payload within 200 milliseconds of receipt.
2. THE Frontend SHALL display time since contact derived from `contact_ts`, a door-to-ECG countdown derived from `door_to_ecg_target_ts`, and the ETA derived from `eta`.
3. THE Frontend SHALL display time since last dose for each `ClockEntry` in the `clocks` payload `meds` list, using the entry's `elapsed_s` value.
4. WHILE no new `clocks` event has been received, THE Frontend SHALL continue advancing each displayed timer so that each value increases (or the countdown decreases) by 1 second at least once per second.
5. IF `contact_ts`, `eta`, or `door_to_ecg_target_ts` is null, THEN THE Frontend SHALL display a placeholder indicating the corresponding value is unavailable instead of a computed time.
6. IF `door_to_ecg_target_ts` is earlier than the current time, THEN THE Frontend SHALL display the door-to-ECG countdown as an overdue value indicating the target time has passed.

### Requirement 6: Live updates and what-changed summary

**User Story:** As an operator, I want updates to be visible and summarized, so that I notice every change without staring.

#### Acceptance Criteria

1. WHEN the Frontend loads, THE Frontend SHALL subscribe to `GET /api/stream` using an `EventSource` and register handlers for the `record`, `flags`, and `clocks` events, updating its displayed state from the payload of each received event.
2. WHEN a `record` or `flags` event changes the displayed state, THE Frontend SHALL apply a visual transition to the changed content that begins within 200 milliseconds of the event and lasts between 300 and 1000 milliseconds.
3. WHEN a `record` or `flags` event changes the displayed state, THE Frontend SHALL display a single "what changed" summary of at most 140 characters beneath the top bar.
4. WHEN a subsequent `record` or `flags` event changes the displayed state, THE Frontend SHALL replace any previously displayed "what changed" summary with the summary for the most recent change.
5. IF the `EventSource` connection to `GET /api/stream` drops, THEN THE Frontend SHALL attempt to reconnect and resume handling the `record`, `flags`, and `clocks` events without operator interaction.

### Requirement 7: Generated outputs and replay

**User Story:** As an operator, I want to read generated handoffs and replay the run, so that I can prepare the receiving team and review history.

#### Acceptance Criteria

1. THE Frontend SHALL provide three selectable tabs labeled SBAR, pre-alert, and checklist, populated respectively from `GET /api/sbar` (string), `GET /api/preAlert` (string), and `GET /api/checklist` (string[]).
2. IF `GET /api/sbar` or `GET /api/preAlert` returns an empty string, OR `GET /api/checklist` returns an empty array, THEN THE Frontend SHALL display a placeholder message indicating no content is available for that tab rather than a blank area.
3. IF any of `GET /api/sbar`, `GET /api/preAlert`, or `GET /api/checklist` fails to return a response, THEN THE Frontend SHALL display an error indication for the affected tab stating the content could not be loaded, and SHALL leave the other tabs unaffected.
4. THE Frontend SHALL provide a replay scrubber positioned over the events returned by `GET /api/events` ordered oldest to newest, with one scrubber position per event.
5. IF `GET /api/events` returns an empty array, THEN THE Frontend SHALL disable the replay scrubber and display an indication that no events are available for replay.
6. WHEN the Frontend finishes loading a non-empty event list from `GET /api/events`, THE Frontend SHALL set the scrubber to the newest event and display the record and flag state derived from all events up to and including that event.
7. WHEN the operator moves the replay scrubber to a selected event, THE Frontend SHALL display the record and flag state derived from all events up to and including the selected event, within 500 milliseconds of the move.

### Requirement 8: Error handling

**User Story:** As an operator, I want clear feedback when a request fails, so that I understand what went wrong.

#### Acceptance Criteria

1. WHEN an API response has a non-2xx status, THE Frontend SHALL parse the response body as an `ErrorBody` and present a resulting message within 1 second of receiving the response.
2. IF the response status is 422, THEN THE Frontend SHALL display a validation message that includes the `ErrorBody` `detail`, and SHALL include the `ErrorBody` `field` name in that message when `field` is a non-null string and omit any field reference when `field` is null.
3. IF the response status is 404, THEN THE Frontend SHALL display a not-found message containing the `ErrorBody` `detail`.
4. IF the response status is 409, THEN THE Frontend SHALL display a conflict message containing the `ErrorBody` `detail` and leave the affected control's displayed state unchanged.
5. IF the response status is 500, THEN THE Frontend SHALL display an error message containing the `ErrorBody` `detail` for both the `processing` and `response_validation` categories and leave all displayed record state unchanged.
6. IF a non-2xx response body cannot be parsed as a valid `ErrorBody`, THEN THE Frontend SHALL display a generic failure message indicating the request did not succeed and leave all displayed record state unchanged.
