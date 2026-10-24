import type { Flag, FlagSeverity } from "@shared/types";
import SayToCrewBox, { type TransitionInfo } from "./SayToCrewBox";

const EDGE: Record<FlagSeverity, string> = {
  critical: "border-l-rose-500 bg-rose-500/5",
  warn: "border-l-amber-600 bg-amber-600/5",
  info: "border-l-sky-500 bg-ink-900",
};
const TAG: Record<FlagSeverity, string> = {
  critical: "bg-rose-500 text-ink-950",
  warn: "bg-amber-600 text-ink-950",
  info: "bg-sky-500/80 text-ink-950",
};

export default function FlagCard({
  flag,
  isNewCritical,
  relayedAt,
  ackedAt,
  onRelay,
  onAck,
}: {
  flag: Flag;
  isNewCritical: boolean;
  relayedAt: TransitionInfo | null;
  ackedAt: TransitionInfo | null;
  onRelay: () => void;
  onAck: () => void;
}) {
  return (
    <div
      className={`border-l-2 ${EDGE[flag.severity]} ${isNewCritical ? "animate-flag-in" : ""} ${
        isNewCritical && flag.severity === "critical" ? "animate-crit-scan" : ""
      } border-b border-b-line p-3`}
      data-testid="flag-card"
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`px-1.5 py-[2px] text-[9px] font-bold uppercase tracking-[0.2lem] ${TAG[flag.severity]}`}>
          {flag.severity}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
          {flag.type.replace(/_/g, "·")}
        </span>
      </div>
      <p className="text-sm leading-snug text-slate-900">{flag.message}</p>
      {flag.evidence.length > 0 && (
        <ul className="mt-1.5 space-y-1 border-l border-line pl-2">
          {flag.evidence.map((e, i) => (
            <li key={i} className="text-[11px] leading-snug text-slate-500">{e}</li>
          ))}
        </ul>
      )}
      <a
        href={flag.source_ref.url}
        target="_blank"
        rel="noreferrer"
        className="mt-1.5 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-accent hover:text-sky-700"
      >
        {flag.source_ref.name} ↗
      </a>
      <SayToCrewBox
        flag={flag}
        relayedAt={relayedAt}
        ackedAt={ackedAt}
        onRelay={onRelay}
        onAck={onAck}
      />
    </div>
  );
}
