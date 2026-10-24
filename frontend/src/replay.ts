import type { PatientRecord, Flag, Event, SourceRef } from "@shared/types";

/** An empty record mirroring `PatientRecord()` on the backend. */
export function emptyRecord(): PatientRecord {
  const s = <T>(v: T | null = null) => ({
    value: v,
    status: "unknown" as const,
    confidence: 0,
    sources: [] as SourceRef[],
  });
  return {
    age: s<string>(),
    sex: s<string>(),
    chief_complaint: s<string>(),
    suspected_condition: s<string>(),
    eta: s<string>(),
    acuity_esi: s<number>(),
    allergies: { value: [], status: "unknown", confidence: 0, sources: [] },
    meds_given: [],
    vitals_timeline: [],
    notes: "",
  };
}

export interface ReplaySnapshot {
  record: PatientRecord;
  flags: Flag[];
}

function getPath(obj: unknown, path: string): any {
  const segs = path.split(".");
  let cur: any = obj;
  for (const s of segs) {
    if (cur == null) return undefined;
    cur = cur[s as keyof typeof cur];
  }
  return cur;
}

function setFact(
  record: PatientRecord,
  path: string,
  value: unknown,
  source: SourceRef | undefined
): void {
  const segs = path.split(".");
  const head = segs[0];
  // List fields: meds_given.N (Sourced<Medication>)
  if (head === "meds_given" && segs.length >= 2) {
    const idx = Number(segs[1]);
    while (record.meds_given.length <= idx) {
      record.meds_given.push({ value: null, status: "unknown", confidence: 0.5, sources: [] });
    }
    const cell = record.meds_given[idx];
    cell.value = value as any;
    if (cell.status === "unknown") cell.status = "unverified";
    if (source) cell.sources = dedupe([...cell.sources, source]);
    return;
  }
  const cell = (record as any)[head];
  if (cell && typeof cell === "object" && "status" in cell) {
    const hadSources = cell.sources.length > 0;
    const same = JSON.stringify(cell.value) === JSON.stringify(value);
    if (!hadSources) {
      cell.value = value;
      cell.status = "unverified";
    } else if (!same) {
      cell.status = "conflicted";
    }
    if (source) cell.sources = dedupe([...cell.sources, source]);
  }
}

function dedupe(src: SourceRef[]): SourceRef[] {
  const seen = new Set<string>();
  const out: SourceRef[] = [];
  for (const s of src) {
    const k = `${s.utterance_id}|${s.quote}`;
    if (!seen.has(k)) { seen.add(k); out.push(s); }
  }
  return out;
}

export function replayFold(events: Event[], upToIndex: number): ReplaySnapshot {
  const record = emptyRecord();
  const flags: Flag[] = [];
  const limit = Math.min(upToIndex, events.length - 1);
  for (let i = 0; i <= limit; i++) {
    const ev = events[i];
    const p = ev.payload as any;
    switch (ev.kind) {
      case "fact":
        setFact(record, String(p.path), p.value, p.source as SourceRef);
        break;
      case "flag_raised": {
        const f = p.flag as Flag;
        if (!flags.some((ex) => ex.id === f.id)) flags.push({ ...f });
        break;
      }
      case "flag_relayed": {
        const f = flags.find((x) => x.id === p.flag_id);
        if (f) f.status = "relayed";
        break;
      }
      case "flag_acked": {
        const f = flags.find((x) => x.id === p.flag_id);
        if (f) f.status = "acknowledged";
        break;
      }
      case "field_confirmed": {
        const cell = getPath(record, String(p.path));
        if (cell && typeof cell === "object" && "status" in cell) cell.status = "confirmed";
        break;
      }
      case "utterance":
      default:
        break;
    }
  }
  return { record, flags };
}

/** Utterances in order up to and including the given index. */
export function utterancesFromEvents(events: Event[]) {
  return events
    .filter((e) => e.kind === "utterance")
    .map((e) => (e.payload as any).utterance as { id: string; text: string; ts: string })
    .filter(Boolean);
}
