import { useEffect, useState } from "react";
import type { Event } from "@shared/types";
import { getSbar, getPreAlert, getChecklist, getEvents } from "../api";
import { replayFold } from "../replay";

type Tab = "sbar" | "preAlert" | "checklist" | "replay";

const TABS: ReadonlyArray<readonly [Tab, string]> = [
  ["sbar", "SBAR"],
  ["preAlert", "PRE-ALERT"],
  ["checklist", "CHECKLIST"],
  ["replay", "REPLAY"],
];

export default function OutputsTabs({ refreshKey }: { refreshKey: number }) {
  const [tab, setTab] = useState<Tab>("sbar");
  const [sbar, setSbar] = useState<string | null>(null);
  const [preAlert, setPreAlert] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<string[] | null>(null);
  const [err, setErr] = useState<Partial<Record<Tab, boolean>>>({});
  const [events, setEvents] = useState<Event[]>([]);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    getSbar().then(setSbar).catch(() => setErr((e) => ({ ...e, sbar: true })));
    getPreAlert().then(setPreAlert).catch(() => setErr((e) => ({ ...e, preAlert: true })));
    getChecklist().then(setChecklist).catch(() => setErr((e) => ({ ...e, checklist: true })));
    getEvents()
      .then((ev) => {
        setEvents(ev);
        setIdx(Math.max(0, ev.length - 1));
      })
      .catch(() => setEvents([]));
  }, [refreshKey]);

  const snap = events.length ? replayFold(events, idx) : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 border-b border-line">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`border-r border-line px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.2lem] transition-colors ${
              tab === id
                ? "bg-ink-800 text-accent border-b-2 border-b-accent"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-3 text-sm">
        {tab === "sbar" && <Out error={err.sbar} empty={!sbar} text={sbar ?? ""} />}
        {tab === "preAlert" && <Out error={err.preAlert} empty={!preAlert} text={preAlert ?? ""} />}
        {tab === "checklist" &&
          (err.checklist ? (
            <Err />
          ) : !checklist || checklist.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-0.5">
              {checklist.map((item, i) => (
                <li key={i} className="flex items-center gap-2 text-slate-800">
                  <input type="checkbox" className="h-3 w-3 accent-emerald-500" /> {item}
                </li>
              ))}
            </ul>
          ))}
        {tab === "replay" &&
          (events.length === 0 ? (
            <p className="text-slate-500">No events available for replay.</p>
          ) : (
            <div className="space-y-3">
              <input
                type="range"
                min={0}
                max={events.length - 1}
                value={idx}
                onChange={(e) => setIdx(Number(e.target.value))}
                className="w-full accent-accent"
              />
              <div className="flex justify-between font-mono text-[10px] text-slate-500">
                <span>
                  {idx + 1} / {events.length} · {events[idx].kind}
                </span>
                <span>{new Date(events[idx].ts).toLocaleTimeString()}</span>
              </div>
              {snap && (
                <div className="border-l border-line pl-2 font-mono text-[11px] text-slate-500">
                  <div>chief complaint · {snap.record.chief_complaint.value ?? "—"}</div>
                  <div>flags · {snap.flags.length}</div>
                </div>
              )}
            </div>
          ))}
      </div>
    </div>
  );
}

function Out({ error, empty, text }: { error?: boolean; empty: boolean; text: string }) {
  if (error) return <Err />;
  if (empty || !text) return <Empty />;
  return <pre className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-slate-800">{text}</pre>;
}
function Empty() {
  return <p className="text-slate-500">No content available yet.</p>;
}
function Err() {
  return <p className="text-rose-700">Could not load this content.</p>;
}
