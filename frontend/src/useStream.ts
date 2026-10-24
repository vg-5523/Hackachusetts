import { useEffect, useRef, useState } from "react";
import type { PatientRecord, Flag, Clocks } from "@shared/types";
import { openStream } from "./api";

export interface StreamState {
  record: PatientRecord | null;
  flags: Flag[];
  clocks: Clocks | null;
  /** True once the stream has opened at least once and is currently live. */
  connected: boolean;
  /** True while a reconnect is pending after a drop. */
  reconnecting: boolean;
}

/**
 * Subscribes to GET /api/stream via EventSource and keeps the latest
 * `record`, `flags`, and `clocks` payloads. On a drop it shows a
 * reconnecting state and retries after 2 seconds.
 */
export function useStream(): StreamState {
  const [state, setState] = useState<StreamState>({
    record: null,
    flags: [],
    clocks: null,
    connected: false,
    reconnecting: false,
  });
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let closed = false;

    const safe = <T,>(raw: string, apply: (v: T) => void) => {
      try {
        apply(JSON.parse(raw) as T);
      } catch {
        /* ignore malformed payload - never crash */
      }
    };

    const connect = () => {
      const es = openStream();
      esRef.current = es;

      es.addEventListener("open", () =>
        setState((s) => ({ ...s, connected: true, reconnecting: false }))
      );
      es.addEventListener("record", (e) =>
        safe<PatientRecord>((e as MessageEvent).data, (record) =>
          setState((s) => ({ ...s, record }))
        )
      );
      es.addEventListener("flags", (e) =>
        safe<Flag[]>((e as MessageEvent).data, (flags) =>
          setState((s) => ({ ...s, flags: Array.isArray(flags) ? flags : [] }))
        )
      );
      es.addEventListener("clocks", (e) =>
        safe<Clocks>((e as MessageEvent).data, (clocks) =>
          setState((s) => ({ ...s, clocks }))
        )
      );
      es.addEventListener("error", () => {
        // EventSource dropped. Mark reconnecting and retry after 2s.
        es.close();
        if (closed) return;
        setState((s) => ({ ...s, connected: false, reconnecting: true }));
        if (retryRef.current == null) {
          retryRef.current = setTimeout(() => {
            retryRef.current = null;
            if (!closed) connect();
          }, 2000);
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
