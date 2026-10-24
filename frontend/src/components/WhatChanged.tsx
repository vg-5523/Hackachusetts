import type { PatientRecord, Flag } from "@shared/types";

export interface Snapshot {
  record: PatientRecord | null;
  flags: Flag[];
}

const FIELDS: ReadonlyArray<readonly [string, string]> = [
  ["age", "age"],
  ["sex", "sex"],
  ["chief_complaint", "chief complaint"],
  ["suspected_condition", "suspected condition"],
  ["eta", "ETA"],
  ["acuity_esi", "acuity"],
];

function val(r: PatientRecord | null, k: string): string {
  if (!r) return "";
  const cell = (r as unknown as Record<string, { value?: unknown }>)[k];
  return cell && cell.value != null ? JSON.stringify(cell.value) : "";
}

/** One-sentence (<=140 char) summary of the change between snapshots. */
export function diffSummary(prev: Snapshot, next: Snapshot): string | null {
  const parts: string[] = [];
  for (const [k, label] of FIELDS) {
    const a = val(prev.record, k);
    const b = val(next.record, k);
    if (a !== b && b) parts.push(`${label} → ${b.replace(/^"|"$/g, "")}`);
  }
  const pMeds = prev.record?.meds_given.length ?? 0;
  const nMeds = next.record?.meds_given.length ?? 0;
  if (nMeds > pMeds) parts.push(`${nMeds - pMeds} med(s) given`);
  const pFlags = new Set(prev.flags.map((f) => f.id));
  const added = next.flags.filter((f) => !pFlags.has(f.id));
  if (added.length) parts.push(`${added.length} new flag(s): ${added[0].type}`);
  for (const f of next.flags) {
    const old = prev.flags.find((x) => x.id === f.id);
    if (old && old.status !== f.status) parts.push(`flag ${f.status}`);
  }
  if (!parts.length) return null;
  const s = parts.join("; ");
  return s.length <= 140 ? s : s.slice(0, 137) + "…";
}

export default function WhatChanged({ text }: { text: string | null }) {
  return (
    <div className="flex min-w-0 items-center gap-2 font-mono text-[11px]">
      <span className="shrink-0 text-accent">▸</span>
      <span className="shrink-0 uppercase tracking-[0.2lem] text-slate-500">
        change
      </span>
      {text ? (
        <span className="truncate text-slate-800">{text}</span>
      ) : (
        <span className="text-slate-400">awaiting updates…</span>
      )}
    </div>
  );
}
