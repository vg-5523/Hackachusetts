import { useEffect, useRef, useState } from "react";
import type { PatientRecord, Flag, Clocks } from "@shared/types";
import { openStream } from "./api";

export interface StreamState {
  record: PatientRecord | null;
  flags: Flag[];
  clocks: Clocks | null;
  connected: boolean;
}

/**
 * Subscribes to GET /api/stream via EventSource and keeps the latest
 * `record`, `flags`, and `clocks` payloads. Reconnects automatically.
 */
export function useStream(): StreamState {
  const [state, setState] = useState<StreamState>({
    record: null,
    flags: [],
    clocks: null,
    connected: false,
  });
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let closed = false;

    const connect = () => {
      const es = openStream();
      esRef.current = es;

      es.addEventListener("open", () =>
        setState((s) => ({ ...s, connected: true }))
      );
      es.addEventListener("record", (e) => {
        try {
          const record = JSON.parse((e as MessageEvent).data) as PatientRecord;
          setState((s) => ({ ...s, record }));
        } catch { /* ignore malformed */ }
      });
      es.addEventListener("flags", (e) => {
        try {
          const flags = JSON.parse((e as MessageEvent).data) as Flag[];
          setState((s) => ({ ...s, flags }));
        } catch { /* ignore */ }
      });
      es.addEventListener("clocks", (e) => {
        try {
          const clocks = JSON.parse((e as MessageEvent).data) as Clocks;
          setState((s) => ({ ...s, clocks }));
        } catch { /* ignore */ }
      });
      es.addEventListener("error", () => {
        setState((s) => ({ ...s, connected: false }));
        es.close();
        if (!closed && retryRef.current == null) {
          retryRef.current = setTimeout(() => {
            retryRef.current = null;
            if (!closed) connect();
          }, 1000);
        }
      });
    };

    connect();
    return () => {
      closed = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      esRef.current?.close();
    };
  }, []);

  return state;
}
