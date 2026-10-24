import { useEffect, useRef } from "react";

export interface TranscriptItem {
  id: string;
  text: string;
  ts: string;
}

/** Live transcript; highlights the active source utterance when set. */
export default function TranscriptPanel({
  utterances,
  highlightIds,
}: {
  utterances: TranscriptItem[];
  highlightIds: Set<string>;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [utterances.length]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.2lem] text-slate-500">
          Transcript
        </h2>
        <span className="font-mono text-[10px] text-slate-500">{utterances.length} lines</span>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {utterances.length === 0 ? (
          <p className="p-3 text-sm text-slate-500">No utterances yet. Speak or type to begin.</p>
        ) : (
          <ul>
            {utterances.map((u) => {
              const on = highlightIds.has(u.id);
              return (
                <li
                  key={u.id}
                  className={`border-l-2 px-3 py-1.5 text-sm leading-snug transition-colors ${` 
                    `}${on ? "border-l-amber-600 bg-amber-600/10 text-amber-900" : "border-l-transparent text-slate-700"}`}
                >
                  <span className="mr-2 font-mono text-[10px] text-slate-500">
                    {new Date(u.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  {u.text}
                </li>
              );
            })}
            <div ref={endRef} />
          </ul>
        )}
      </div>
    </div>
  );
}
