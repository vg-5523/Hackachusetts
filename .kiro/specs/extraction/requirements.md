# Requirements Document

## Introduction

The Extraction package (`backend/extraction/`, Account A) turns a single paramedic
`Utterance` into structured `PatientRecord` facts with provenance. Its one public
function, `process_utterance(utterance, record) -> PatientRecord`, calls the shared
`call_llm` wrapper for strict-JSON extraction, verifies every quote against the
utterance text, and returns a new record with new facts appended. Conflict
resolution is the store's job; extraction only appends values and their sources.
Models are imported read-only from `shared.schema`; this spec edits only files
inside `backend/extraction/`.

## Glossary

- **Extractor**: The `process_utterance` function and its supporting helpers in `backend/extraction/`.
- **Utterance**: A `shared.schema.Utterance` with `id`, `text`, and aware `ts`.
- **PatientRecord**: The `shared.schema.PatientRecord` whose fields carry provenance.
- **Sourced**: The `shared.schema.Sourced[T]` wrapper (`value`, `status`, `confidence` 0..1, `sources`).
- **SourceRef**: A `shared.schema.SourceRef` (`utterance_id`, `quote` 1..1000 chars, aware `ts`).
- **LLM_Wrapper**: The `call_llm` function in `backend/llm.py`, invoked via the module so tests can patch it.
- **Cache**: On-disk JSON files under `backend/extraction/cache/`, keyed by a hash of the utterance text.

## Requirements

### Requirement 1: Structured extraction via the LLM

**User Story:** As a backend consumer, I want an utterance turned into structured record fields, so that the patient record stays current.

#### Acceptance Criteria

1. WHEN `process_utterance` is called, THE Extractor SHALL invoke LLM_Wrapper (via the module, so tests can patch it) with a prompt that requests a single strict-JSON object as output.
2. WHEN LLM_Wrapper returns a JSON object, THE Extractor SHALL extract these fields from it: age, sex, chief_complaint, suspected_condition, acuity_esi, allergies, meds_given, vitals_timeline, and eta.
3. WHEN the Extractor sets any extracted field on the returned PatientRecord, THE Extractor SHALL attach to that field at least one SourceRef carrying the verbatim source quote and the originating utterance timestamp.
4. IF the utterance provides no value for one of the extracted fields, THEN THE Extractor SHALL leave that field unchanged from the input record.
5. THE Extractor SHALL constrain acuity_esi to an integer from 1 to 5 inclusive.
6. IF the LLM response supplies an acuity_esi outside 1 to 5 inclusive, THEN THE Extractor SHALL reject that value and preserve all other extracted fields.
7. THE Extractor SHALL represent each administered medication with drug, dose, route, time, and given_by.
8. IF LLM_Wrapper returns output that is not a single conforming JSON object, THEN THE Extractor SHALL skip the unparseable content and return a record containing only the facts it could verify.

### Requirement 2: Provenance and quote verification

**User Story:** As a receiving clinician, I want every fact traceable to exact words, so that I can trust the record.

#### Acceptance Criteria

1. WHEN the Extractor sets a field, THE Extractor SHALL attach at least one SourceRef whose quote is 1 to 1000 characters.
2. WHEN the LLM response is received, THE Extractor SHALL verify each quote is a case-sensitive, character-for-character substring of `utterance.text`.
3. IF a quote is not a substring of `utterance.text`, THEN THE Extractor SHALL drop that SourceRef.
4. IF a fact has no surviving verified SourceRef after verification, THEN THE Extractor SHALL drop the fact.
5. THE Extractor SHALL set each SourceRef `utterance_id` to `utterance.id` and `ts` to `utterance.ts`.

### Requirement 3: Append-only, non-mutating updates

**User Story:** As the store owner, I want extraction to append facts without resolving conflicts, so that the store derives the final record.

#### Acceptance Criteria

1. WHEN extraction runs, THE Extractor SHALL return a new PatientRecord and SHALL leave the input `record` byte-for-byte identical, altering none of its values, statuses, confidence values, or source lists.
2. WHEN a new value is extracted for a field that already holds a different value, THE Extractor SHALL append the new value together with its SourceRef and SHALL leave the existing value and its SourceRef in place.
3. THE Extractor SHALL never set any field status to `conflicted` and SHALL leave conflicted-status resolution to `backend/store`.

### Requirement 4: Confidence and relative-time handling

**User Story:** As a clinician, I want hedged speech and relative times handled sensibly, so that uncertainty and timing are accurate.

#### Acceptance Criteria

1. WHEN an extracted fact derives from hedged or garbled speech (for example "maybe", "I think", or an incomplete quote), THE Extractor SHALL set the fact status to `unverified`.
2. WHEN an extracted fact derives from hedged or garbled speech, THE Extractor SHALL assign a confidence no greater than that of an equivalent unhedged fact.
3. WHEN an utterance states a relative time, THE Extractor SHALL resolve the relative time against `utterance.ts` and record the result as an offset-aware timestamp.

### Requirement 5: Offline cache

**User Story:** As a demo operator, I want responses replayed offline, so that demos run without network or keys.

#### Acceptance Criteria

1. WHEN LLM_Wrapper returns a response, THE Extractor SHALL store it on disk under `backend/extraction/cache/`, in a file named by a deterministic hash of the exact utterance text.
2. WHEN a cache entry exists for the utterance text, THE Extractor SHALL use the cached response and SHALL NOT call LLM_Wrapper.
3. WHEN no cache entry exists for the utterance text, THE Extractor SHALL call LLM_Wrapper.
4. IF a cache entry exists but cannot be read or parsed, THEN THE Extractor SHALL treat it as a miss and fall back to calling LLM_Wrapper.
5. THE Extractor SHALL keep cache files tracked in version control.

### Requirement 6: Error propagation without a key or cache

**User Story:** As an API maintainer, I want a clear, propagating error, so that the API returns a 500 and the stub stays up.

#### Acceptance Criteria

1. IF `LLM_API_KEY` is unset or empty and no cache entry exists for the utterance text, THEN THE Extractor SHALL raise an error whose message names `LLM_API_KEY`.
2. WHEN the Extractor raises the no-key error, THE Extractor SHALL allow that error to propagate to the caller unchanged, without catching, suppressing, or replacing it.
3. WHEN `LLM_API_KEY` is unset or empty and a cache entry exists for the utterance text, THE Extractor SHALL return the cached extraction result without raising an error.

### Requirement 7: Test suite with hand-written utterances

**User Story:** As a maintainer, I want representative tests, so that extraction behavior is verified.

#### Acceptance Criteria

1. THE Extractor SHALL ship five tests under `backend/extraction/tests/` driven by hand-written sample utterances with a patched `call_llm` that makes no network call.
2. THE Extractor test suite SHALL include a "no allergies" utterance followed by a "penicillin bracelet" utterance, asserting both allergy values are present with their sources so the store can later mark `allergies` conflicted.
3. THE Extractor test suite SHALL include an aspirin-given-twice case asserting two `meds_given` entries result, each with its own SourceRef.
4. THE Extractor test suite SHALL pass under pytest.
