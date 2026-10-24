import type {
  PatientRecord,
  Flag,
  Event,
  Sourced,
  ErrorBody,
  UtteranceRequest,
} from "@shared/types";

const RAW_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000";
// Strip any trailing slash so ${BASE}/api/... never doubles the slash.
const BASE = RAW_BASE.replace(/\/+$/, "");

export const API_BASE = BASE;

/** Thrown on any non-2xx response. `body` is null when unparseable. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody | null;
  constructor(status: number, body: ErrorBody | null) {
    super(body?.detail ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ErrorBody | null = null;
  try {
    const json = await res.json();
    if (
      json &&
      typeof json === "object" &&
      typeof json.category === "string" &&
      typeof json.detail === "string"
    ) {
      body = json as ErrorBody;
    }
  } catch {
    body = null;
  }
  return new ApiError(res.status, body);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw await parseError(res);
  const text = await res.text();
  return (text ? JSON.parse(text) : (null as unknown)) as T;
}

const POST: RequestInit = { method: "POST" };

export function postUtterance(body: UtteranceRequest): Promise<PatientRecord> {
  return request("/api/utterance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getRecord = () => request<PatientRecord>("/api/record");
export const getFlags = () => request<Flag[]>("/api/flags");
export const getEvents = () => request<Event[]>("/api/events");
export const getSbar = () => request<string>("/api/sbar");
export const getPreAlert = () => request<string>("/api/preAlert");
export const getChecklist = () => request<string[]>("/api/checklist");
export const getScenarios = () => request<string[]>("/api/scenarios");

export const relayFlag = (id: string) =>
  request<Flag>(`/api/flags/${encodeURIComponent(id)}/relay`, POST);
export const ackFlag = (id: string) =>
  request<Flag>(`/api/flags/${encodeURIComponent(id)}/ack`, POST);
export const confirmField = (path: string) =>
  request<Sourced<unknown>>(`/api/fields/${encodeURIComponent(path)}/confirm`, POST);
export const playScenario = (id: string) =>
  request<PatientRecord>(`/api/scenario/${encodeURIComponent(id)}/play`, POST);

export function openStream(): EventSource {
  return new EventSource(`${BASE}/api/stream`);
}
