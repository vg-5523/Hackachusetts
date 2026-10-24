import { useEffect, useRef, useState } from "react";
import { postUtterance, playScenario, getScenarios } from "../api";

function recognizer(): SpeechRecognition | null {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <rect x="4.5" y="1" width="3" height="6" rx="1.5" fill={active ? "currentColor" : "none"} stroke="currentColor" />
      <path d="M3 6a3 3 0 0 0 6 0" stroke="currentColor" fill="none" />
      <path d="M6 9v2" stroke="currentColor" />
    </svg>
  );
}

/** Mic (Web Speech, continuous) + typed fallback + play-scenario. */
export default function UtteranceInput({
  onError,
}: {
  onError: (e: unknown) => void;
}) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speechOk, setSpeechOk] = useState(true);
  const [validation, setValidation] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const recRef = useRef<SpeechRecognition | null>(null);

  useEffect(() => {
    setSpeechOk(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
    getScenarios().then(setScenarios).catch(() => setScenarios([]));
    return () => recRef.current?.abort();
  }, []);

  const nowIso = () => new Date().toISOString();

  async function send(raw: string) {
    const t = raw.trim();
    if (t.length < 1 || t.length > 2000) {
      setValidation("Utterance text must be 1 to 2000 characters.");
      return;
    }
    setValidation(null);
    try {
      await postUtterance({ text: t, ts: nowIso() });
      setText("");
    } catch (e) {
      onError(e);
    }
  }

  function toggleMic() {
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = recognizer();
    if (!rec) { setSpeechOk(false); return; }
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = (ev) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) void send(r[0].transcript);
      }
    };
    rec.onerror = () => { setListening(false); setSpeechOk(false); };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }

  async function play(id: string) {
    try { await playScenario(id); } catch (e) { onError(e); }
  }

  return (
    <div className="space-y-2 border-t border-line bg-ink-950 p-3">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={toggleMic}
          disabled={!speechOk}
          className={`flex items-center gap-1.5 border px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${` 
            `}${
            listening
              ? "border-rose-500 bg-rose-500/15 text-rose-700"
              : speechOk
              ? "border-accent/40 bg-accent/10 text-accent hover:bg-accent/20"
              : "border-line bg-ink-800 text-slate-500"
          }`}
        >
          <MicIcon active={listening} />
          {listening ? "Listening" : "Mic"}
        </button>
        <select
          onChange={(e) => e.target.value && play(e.target.value)}
          defaultValue=""
          className="flex-1 border border-line bg-ink-800 px-2 py-1.5 text-[11px] uppercase tracking-wide text-slate-700 outline-none focus:border-accent/40"
        >
          <option value="" disabled>
            Play scenario
          </option>
          {scenarios.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      {!speechOk && (
        <p className="text-[10px] uppercase tracking-wide text-amber-700/80">
          Speech capture unavailable — type below
        </p>
      )}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); }
        }}
        placeholder="Type an utterance, Enter to send"
        rows={2}
        className="w-full resize-none border border-line bg-ink-800 p-2 font-mono text-sm text-slate-900 outline-none placeholder:text-slate-500 focus:border-accent/50"
      />
      {validation && <p className="text-[11px] text-rose-700">{validation}</p>}
      <button
        type="button"
        onClick={() => send(text)}
        className="w-full border border-line bg-ink-800 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-800 hover:border-slate-400 hover:bg-ink-700"
      >
        Send utterance
      </button>
    </div>
  );
}
