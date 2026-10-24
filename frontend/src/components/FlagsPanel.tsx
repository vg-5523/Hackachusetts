import { useEffect, useMemo, useRef, useState } from "react";
import type { Flag, FlagSeverity } from "@shared/types";
import FlagCard from "./FlagCard";
import type { TransitionInfo } from "./SayToCrewBox";

const RANK: Record<FlagSeverity, number> = { critical: 0, warn: 1, info: 2 };

function playBeep() {
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    // Two short descending blips - an alert, not a game chime.
    const blip = (freq: number, t0: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(0.15, t0 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.14);
      osc.start(t0);
      osc.stop(t0 + 0.14);
    };
    blip(940, ctx.currentTime);
    blip(704, ctx.currentTime + 0.18);
  } catch {
    /* audio optional */
  }
}

/** Right column: flags sorted by severity with human-in-the-loop relay. */
export default function FlagsPanel({
  flags,
  transitions,
  onRelay,
  onAck,
}: {
  flags: Flag[];
  transitions: Record<string, { relayed?: TransitionInfo; acked?: TransitionInfo }>;
  onRelay: (id: string) => void;
  onAck: (id: string) => void;
}) {
  const sorted = useMemo(
    () => [...flags].sort((a, b) => RANK[a.severity] - RANK[b.severity]),
    [flags]
  );
  const crit = sorted.filter((f) => f.severity === "critical").length;
  const seenCritical = useRef<Set<string>>(new Set());
  const [newCritical, setNewCritical] = useState<Set<string>>(new Set());

  useEffect(() => {
    const fresh: string[] = [];
    for (const f of flags) {
      if (f.severity === "critical" && !seenCritical.current.has(f.id)) {
        seenCritical.current.add(f.id);
        fresh.push(f.id);
      }
    }
    if (fresh.length) {
      playBeep();
      setNewCritical(new Set(fresh));
      const t = setTimeout(() => setNewCritical(new Set()), 2700);
      return () => clearTimeout(t);
    }
  }, [flags]);

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.2lem] text-slate-500">
          Safety flags
        </h2>
        <div className="flex items-center gap-2 font-mono text-[10px]">
          {crit > 0 && (
            <span className="flex items-center gap-1 text-rose-700">
              <span className="h-1.5 w-1.5 animate-tick rounded-full bg-rose-500" />
              {crit} crit
            </span>
          )}
          <span className="text-slate-500">{sorted.length} total</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">No active flags.</p>
        ) : (
          sorted.map((f) => {
            const t = transitions[f.id] ?? {};
            return (
              <FlagCard
                key={f.id}
                flag={f}
                isNewCritical={newCritical.has(f.id)}
                relayedAt={t.relayed ?? null}
                ackedAt={t.acked ?? null}
                onRelay={() => onRelay(f.id)}
                onAck={() => onAck(f.id)}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
