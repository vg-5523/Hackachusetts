import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Flag, PatientRecord } from "@shared/types";
import Layout from "./components/Layout";
import ClocksBar from "./components/ClocksBar";
import WhatChanged, { diffSummary } from "./components/WhatChanged";
import TranscriptPanel, { type TranscriptItem } from "./components/TranscriptPanel";
import UtteranceInput from "./components/UtteranceInput";
import RecordPanel from "./components/RecordPanel";
import ProvenanceDrawer, { type DrawerData } from "./components/ProvenanceDrawer";
import FlagsPanel from "./components/FlagsPanel";
import type { TransitionInfo } from "./components/SayToCrewBox";
import OutputsTabs from "./components/OutputsTabs";
import ErrorToast, { errorMessage } from "./components/ErrorToast";
import { useStream } from "./useStream";
import { getEvents, relayFlag, ackFlag, confirmField } from "./api";
import { utterancesFromEvents } from "./replay";

function nowStr(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function App() {
  const { record, flags, clocks } = useStream();
  const [drawer, setDrawer] = useState<DrawerData | null>(null);
  const [transitions, setTransitions] = useState<
    Record<string, { relayed?: TransitionInfo; acked?: TransitionInfo }>
  >({});
  const [toast, setToast] = useState<string | null>(null);
  const [utterances, setUtterances] = useState<TranscriptItem[]>([]);
  const [whatChanged, setWhatChanged] = useState<string | null>(null);
  const [outputsKey, setOutputsKey] = useState(0);

  const prevRef = useRef<{ record: PatientRecord | null; flags: Flag[] }>({
    record: null,
    flags: [],
  });

  // Refresh transcript from the event log when the record changes.
  useEffect(() => {
    let active = true;
    getEvents()
      .then((ev) => {
        if (active) setUtterances(utterancesFromEvents(ev));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [record, flags]);

  // Compute the "what changed" line on each record/flags update.
  useEffect(() => {
    const summary = diffSummary(
      { record: prevRef.current.record, flags: prevRef.current.flags },
      { record, flags }
    );
    if (summary) setWhatChanged(summary);
    prevRef.current = { record, flags };
    setOutputsKey((k) => k + 1);
  }, [record, flags]);

  const highlightIds = useMemo(
    () => new Set((drawer?.sources ?? []).map((s) => s.utterance_id)),
    [drawer]
  );

  const showError = useCallback((e: unknown) => setToast(errorMessage(e)), []);

  const onRelay = useCallback(
    async (id: string) => {
      try {
        await relayFlag(id);
        setTransitions((t) => ({
          ...t,
          [id]: { ...t[id], relayed: { who: "operator", when: nowStr() } },
        }));
      } catch (e) {
        showError(e);
      }
    },
    [showError]
  );

  const onAck = useCallback(
    async (id: string) => {
      try {
        await ackFlag(id);
        setTransitions((t) => ({
          ...t,
          [id]: { ...t[id], acked: { who: "operator", when: nowStr() } },
        }));
      } catch (e) {
        showError(e);
      }
    },
    [showError]
  );

  const onConfirm = useCallback(
    async (path: string) => {
      try {
        await confirmField(path);
      } catch (e) {
        showError(e);
      }
    },
    [showError]
  );

  return (
    <>
      <Layout
        topBar={<ClocksBar clocks={clocks} />}
        whatChanged={<WhatChanged text={whatChanged} />}
        left={
          <>
            <TranscriptPanel utterances={utterances} highlightIds={highlightIds} />
            <UtteranceInput onError={showError} />
          </>
        }
        center={
          <RecordPanel
            record={record}
            activePath={drawer?.path ?? null}
            onOpen={setDrawer}
            onConfirm={onConfirm}
          />
        }
        right={
          <div className="flex h-full min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto">
              <FlagsPanel
                flags={flags}
                transitions={transitions}
                onRelay={onRelay}
                onAck={onAck}
              />
            </div>
            <div className="h-[18rem] shrink-0 border-t border-line bg-ink-950">
              <OutputsTabs refreshKey={outputsKey} />
            </div>
          </div>
        }
        footerExtra={"synthetic training data"}
      />
      <ProvenanceDrawer data={drawer} onClose={() => setDrawer(null)} />
      <ErrorToast message={toast} onDismiss={() => setToast(null)} />
    </>
  );
}
