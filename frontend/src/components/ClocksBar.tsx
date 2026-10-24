import { useEffect, useState } from "react";
import type { Clocks } from "@shared/types";
import { fmtDuration, fmtClock, secondsSince, secondsUntil } from "../format";

function Stat({
  label,
  value,
  tone,
  big,
}: {
  label: string;
  value: string;
  tone?: string;
  big?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 px-4">
      <span className="text-[9px] font-medium uppercase tracking-[0.2lem] text-slate-500">
        {label}
      </span>
      <span
        className={`font-mono tabular-nums ${big ? "text-xl" : "text-base"} font-semibold leading-none ${tone ?? "text-slate-900"}`}
      >
        {value}
      </span>
    </div>
  );
}

/** Top-bar live clocks. Ticks client-side between SSE `clocks` events. */
export default function ClocksBar({ clocks }: { clocks: Clocks | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const sinceContact = secondsSince(clocks?.contact_ts ?? null, now);
  const toEcg = secondsUntil(clocks?.door_to_ecg_target_ts ?? null, now);
  const dash = "—";

  return (
    <div className="flex items-stretch">
      <div className="flex items-center gap-2.5 border-r border-line px-4 py-2.5">
        <span className="flex h-2 w-2 items-center justify-center">
          <span className="h-1.5 w-1.5 animate-tick rounded-full bg-emerald-600" />
        </span>
        <div className="flex flex-col gap-0.5 leading-none">
          <div className="text-lg font-semibold tracking-tight text-slate-900">Relay</div>
          <div className="text-[9px] uppercase tracking-[0.2em] text-emerald-700">live · safety console</div>
        </div>
      </div>
      <div className="flex divide-x divide-line">
        <Stat big label="T + contact" value={sinceContact == null ? dash : fmtDuration(sinceContact)} />
        <Stat
          big
          label="Door → ECG"
          value={toEcg == null ? dash : toEcg < 0 ? fmtDuration(toEcg) : fmtDuration(toEcg)}
          tone={toEcg != null && toEcg < 0 ? "text-rose-700" : toEcg != null && toEcg < 60 ? "text-amber-700" : undefined}
        />
        <Stat big label="ETA" value={fmtClock(clocks?.eta ?? null)} />
      </div>
      <div className="flex flex-1 items-center gap-0 overflow-x-auto border-l border-line">
        {(clocks?.meds ?? []).length === 0 ? (
          <span className="px-4 text-[10px] uppercase tracking-wide text-slate-500">
            No meds given
          </span>
        ) : (
          (clocks?.meds ?? []).map((m) => {
            const live = secondsSince(m.last_dose_ts, now) ?? m.elapsed_s;
            return (
              <Stat
                key={m.med_id}
                label={`since ${m.med_id}`}
                value={fmtDuration(live)}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
