import type { PatientRecord, Sourced, Medication } from "@shared/types";
import type { ReactNode } from "react";
import SourcedField from "./SourcedField";
import type { DrawerData } from "./ProvenanceDrawer";

const SCALARS: ReadonlyArray<readonly [keyof PatientRecord, string]> = [
  ["age", "Age"],
  ["sex", "Sex"],
  ["chief_complaint", "Chief complaint"],
  ["suspected_condition", "Suspected condition"],
  ["acuity_esi", "Acuity (ESI)"],
  ["eta", "ETA"],
  ["allergies", "Allergies"],
];

function medLabel(m: Medication | null, i: number): string {
  if (!m) return `Medication ${i + 1}`;
  const bits = [m.drug, m.dose].filter(Boolean).join(" ");
  return bits || `Medication ${i + 1}`;
}

function Section({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section>
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-ink-950/95 px-3 py-1.5 backdrop-blur-sm">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.2lem] text-slate-500">{title}</h3>
        {meta && <span className="font-mono text-[10px] text-slate-500">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

/** Center patient-record stage: every field via SourcedField, plus vitals. */
export default function RecordPanel({
  record,
  activePath,
  onOpen,
  onConfirm,
}: {
  record: PatientRecord | null;
  activePath: string | null;
  onOpen: (d: DrawerData) => void;
  onConfirm: (path: string) => void;
}) {
  if (!record) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Waiting for the patient record…
      </div>
    );
  }
  const open = (path: string, label: string, f: Sourced<unknown>) =>
    onOpen({ path, label, status: f.status, sources: f.sources });
  return (
    <div className="pb-20">
      <Section title="Patient record" meta={record.suspected_condition.value ?? undefined}>
        <div className="grid grid-cols-2">
          {SCALARS.map(([key, label], i) => {
            const f = record[key] as unknown as Sourced<unknown>;
            return (
              <div
                key={key}
                className={`border-b border-line ${i % 2 === 0 ? "border-r" : ""}`}
              >
                <SourcedField
                  path={key}
                  label={label}
                  field={f}
                  active={activePath === key}
                  onOpen={() => open(key, label, f)}
                  onConfirm={() => onConfirm(key)}
                />
              </div>
            );
          })}
        </div>
      </Section>

      <Section
        title="Medications given"
        meta={record.meds_given.length ? `${record.meds_given.length}` : undefined}
      >
        {record.meds_given.length === 0 ? (
          <p className="px-3 py-2 text-sm text-slate-500">None recorded.</p>
        ) : (
          <div className="grid grid-cols-2">
            {record.meds_given.map((m, i) => {
              const path = `meds_given.${i}`;
              const label = medLabel(m.value, i);
              return (
                <div
                  key={path}
                  className={`border-b border-line ${i % 2 === 0 ? "border-r" : ""}`}
                >
                  <SourcedField
                    path={path}
                    label={label}
                    field={m as Sourced<unknown>}
                    active={activePath === path}
                    onOpen={() => open(path, label, m as Sourced<unknown>)}
                    onConfirm={() => onConfirm(path)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </Section>

      <Section
        title="Vitals"
        meta={record.vitals_timeline.length ? `${record.vitals_timeline.length} readings` : undefined}
      >
        {record.vitals_timeline.length === 0 ? (
          <p className="px-3 py-2 text-sm text-slate-500">None recorded.</p>
        ) : (
          <table className="w-full text-left font-mono text-xs">
            <thead>
              <tr className="text-[9px] uppercase tracking-wide text-slate-500">
                <th className="px-3 py-1 font-medium">Time</th>
                <th className="pr-3 font-medium">HR</th>
                <th className="pr-3 font-medium">BP</th>
                <th className="pr-3 font-medium">SpO2</th>
                <th className="font-medium">RR</th>
              </tr>
            </thead>
            <tbody className="text-slate-800">
              {record.vitals_timeline.map((v, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-3 py-1 text-slate-500">
                    {new Date(v.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="pr-3">{v.hr ?? "—"}</td>
                  <td className="pr-3">{v.bp ?? "—"}</td>
                  <td className="pr-3">{v.spo2 ?? "—"}</td>
                  <td>{v.rr ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {record.notes && (
        <Section title="Notes">
          <p className="px-3 py-2 text-sm leading-relaxed text-slate-700">{record.notes}</p>
        </Section>
      )}
    </div>
  );
}
