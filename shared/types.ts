/**
 * Shared TypeScript contract for the Ambulance Scribe + Safety Check system.
 *
 * This file is hand-written to mirror `shared/schema.py` (the Pydantic v2 single
 * source of truth). There is no generator: names, field names, enum string
 * values, and nullability must match `shared/schema.py` exactly. Keep this file
 * in sync by hand whenever the schema changes.
 *
 * Representation choices:
 * - Pydantic enums (`str, Enum`) become string-literal union types with the
 *   same string values.
 * - `AwareDatetime` is serialized as an ISO 8601 `string`.
 * - `AnyHttpUrl` is a `string`.
 */

/** Provenance status of a {@link Sourced} field. */
export type FieldStatus = "confirmed" | "unverified" | "conflicted" | "unknown";

/** Category of a safety flag. */
export type FlagType =
  | "duplicate_dose"
  | "allergy_conflict"
  | "interaction"
  | "contradiction"
  | "missing_info";

/** Severity of a safety flag. */
export type FlagSeverity = "critical" | "warn" | "info";

/** Lifecycle state of a safety flag. */
export type FlagStatus = "open" | "relayed" | "acknowledged";

/** A pointer to the utterance that supports a {@link Sourced} value. */
export interface SourceRef {
  utterance_id: string;
  quote: string;
  /** AwareDatetime, ISO 8601. */
  ts: string;
}

/** A named, linkable source backing a safety flag. */
export interface Citation {
  name: string;
  /** AnyHttpUrl. */
  url: string;
}

/** A value wrapped with provenance: status, confidence, and source quotes. */
export interface Sourced<T> {
  value: T | null;
  status: FieldStatus;
  confidence: number;
  sources: SourceRef[];
}

/** One administered drug, every field optional provenance-free text. */
export interface Medication {
  drug: string | null;
  dose: string | null;
  route: string | null;
  time: string | null;
  given_by: string | null;
}

/** One vitals measurement at a point in time. */
export interface VitalsEntry {
  /** AwareDatetime, ISO 8601. */
  ts: string;
  hr: number | null;
  bp: string | null;
  spo2: number | null;
  rr: number | null;
  source: string;
}

/** The structured patient record. Every value carries provenance. */
export interface PatientRecord {
  age: Sourced<string>;
  sex: Sourced<string>;
  chief_complaint: Sourced<string>;
  suspected_condition: Sourced<string>;
  eta: Sourced<string>;
  acuity_esi: Sourced<number>;
  allergies: Sourced<string[]>;
  meds_given: Sourced<Medication>[];
  vitals_timeline: VitalsEntry[];
  notes: string;
}

/** A deterministic, cited safety alert. The LLM only phrases `say_to_crew`. */
export interface Flag {
  id: string;
  type: FlagType;
  severity: FlagSeverity;
  message: string;
  say_to_crew: string;
  evidence: string[];
  source_ref: Citation;
  status: FlagStatus;
}

/** The JSON body of every error response (see `shared/api.md`). */
export interface ErrorBody {
  category: string;
  field?: string | null;
  detail: string;
}

/** A unit of paramedic speech or typed text, logged as an Event payload. */
export interface Utterance {
  id: string;
  text: string;
  /** AwareDatetime, ISO 8601. */
  ts: string;
}

/** The `POST /api/utterance` request body (an {@link Utterance} sans id). */
export interface UtteranceRequest {
  text: string;
  /** AwareDatetime, ISO 8601. */
  ts: string;
}

/** One entry in the append-only Event_Log, the single source of truth. */
export interface Event {
  id: string;
  /** AwareDatetime, ISO 8601 with millisecond precision. */
  ts: string;
  kind: string;
  payload: Record<string, unknown>;
}

/** Elapsed-time timer for one administered medication in the clock bar. */
export interface ClockEntry {
  med_id: string;
  /** AwareDatetime, ISO 8601. */
  last_dose_ts: string;
  elapsed_s: number;
}

/** The running-timer snapshot broadcast on the SSE `clocks` channel. */
export interface Clocks {
  /** AwareDatetime, ISO 8601. */
  contact_ts: string | null;
  /** AwareDatetime, ISO 8601. */
  eta: string | null;
  /** AwareDatetime, ISO 8601. */
  door_to_ecg_target_ts: string | null;
  meds: ClockEntry[];
}
