import type { Flag } from "@shared/types";

export interface TransitionInfo {
  who: string;
  when: string;
}

/**
 * The prominent SAY TO CREW callout. The operator relays the line; the
 * machine never speaks to the crew. Ack is disabled until relayed.
 */
export default function SayToCrewBox({
  flag,
  relayedAt,
  ackedAt,
  onRelay,
  onAck,
}: {
  flag: Flag;
  relayedAt: TransitionInfo | null;
  ackedAt: TransitionInfo | null;
  onRelay: () => void;
  onAck: () => void;
}) {
  const st = flag.status;
  const canRelay = st === "open";
  const canAck = st === "relayed";
  return (
    <div className="mt-2.5 border border-accent/30 bg-accent/5">
      <div className="flex items-center justify-between border-b border-accent/20 bg-accent/10 px-2 py-1">
        <span className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[0.25lem] text-accent">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
            <path d="M1 3h4l3-2v8L5 7H1z" stroke="currentColor" stroke-width="1" stroke-linejoin="round" />
          </svg>
          Say to crew
        </span>
        <span className="font-mono text-[9px] uppercase tracking-wide text-slate-500">{st}</span>
      </div>
      <p className="px-2 py-2 text-sm font-medium leading-snug text-sky-900">{flag.say_to_crew}</p>
      <div className="flex gap-px border-t border-accent/20">
        <button
          type="button"
          onClick={onRelay}
          disabled={!canRelay}
          className={`flex-1 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
            canRelay
              ? "bg-accent text-ink-950 hover:bg-sky-700"
              : st === "relayed" || st === "acknowledged"
              ? "bg-accent/10 text-accent/60"
              : "bg-ink-800 text-slate-500"
          }`}
        >
          {st === "open" ? "Relay → crew" : "Relayed ✓"}
        </button>
        <button
          type="button"
          onClick={onAck}
          disabled={!canAck}
          className={`flex-1 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
            canAck
              ? "bg-emerald-500 text-ink-950 hover:bg-emerald-600"
              : st === "acknowledged"
              ? "bg-emerald-500/15 text-emerald-700"
              : "bg-ink-800 text-slate-400"
          }`}
        >
          {st === "acknowledged" ? "Acknowledged ✓" : "Acknowledge"}
        </button>
      </div>
      {(relayedAt || ackedAt) && (
        <div className="border-t border-accent/20 px-2 py-1 font-mono text-[9px] leading-relaxed">
          {relayedAt && (
            <div className="text-accent/80">
              RELAYED · {relayedAt.who} · {relayedAt.when}
            </div>
          )}
          {ackedAt && (
            <div className="text-emerald-700/80">
              ACKNOWLEDGED · {ackedAt.who} · {ackedAt.when}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
