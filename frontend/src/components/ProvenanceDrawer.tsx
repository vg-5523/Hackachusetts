import type { SourceRef, FieldStatus } from "@shared/types";
import { fmtClock } from "../format";

export interface DrawerData {
  path: string;
  label: string;
  status: FieldStatus;
  sources: SourceRef[];
}

/** Shows every source (quote + timestamp) for the selected field. */
export default function ProvenanceDrawer({
  data,
  onClose,
}: {
  data: DrawerData | null;
  onClose: () => void;
}) {
  if (!data) return null;
  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-[28rem] max-w-[90vw] flex-col border-l border-slate-300 bg-slate-100 shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-900">Provenance</div>
          <div className="text-xs text-slate-500">{data.label} · {data.path}</div>
        </div>
        <button
          onClick={onClose}
          className="rounded bg-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-300"
          aria-label="Close provenance"
        >
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {data.sources.length === 0 ? (
          <p className="text-sm text-slate-500">No sources recorded for this field.</p>
        ) : (
          <ul className="space-y-3">
            {data.sources.map((s, i) => (
              <li key={`${s.utterance_id}-${i}`} className="rounded border border-slate-300 bg-slate-50 p-3">
                <p className="text-sm italic text-slate-900">“{s.quote}”</p>
                <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                  <span>{s.utterance_id}</span>
                  <span>{fmtClock(s.ts)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
