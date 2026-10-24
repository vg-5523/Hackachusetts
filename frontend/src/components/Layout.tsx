import type { ReactNode } from "react";

export const DISCLAIMER =
  "decision support, not clinical advice. Synthetic data only.";

interface LayoutProps {
  topBar?: ReactNode;
  whatChanged?: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  footerExtra?: ReactNode;
}

/**
 * Console shell for the single-screen operator UI. Fits 1280x720 with
 * no page scroll; columns scroll internally. Deep near-black, hairline
 * dividers, one clinical accent.
 */
export default function Layout({
  topBar,
  whatChanged,
  left,
  center,
  right,
  footerExtra,
}: LayoutProps) {
  return (
    <div className="grid h-screen w-screen grid-rows-[auto_auto_1fr_auto] overflow-hidden bg-ink-950 text-slate-900">
      <header className="border-b border-line bg-ink-900">{topBar}</header>
      <div className="flex min-h-[1.6rem] items-center border-b border-line bg-ink-900/40 px-4">
        {whatChanged}
      </div>
      <main className="grid min-h-0 grid-cols-[21rem_1fr_23rem]">
        <section
          aria-label="Transcript and input"
          className="flex min-h-0 flex-col border-r border-line bg-ink-900"
        >
          {left}
        </section>
        <section
          aria-label="Patient record"
          className="stage-grid min-h-0 overflow-y-auto bg-ink-950"
        >
          {center}
        </section>
        <section
          aria-label="Safety flags"
          className="min-h-0 overflow-y-auto border-l border-line bg-ink-900"
        >
          {right}
        </section>
      </main>
      <footer className="flex items-center justify-between gap-4 border-t border-line bg-ink-900 px-4 py-2">
        <span className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="h-1 w-1 rounded-full bg-amber-600" />
          {DISCLAIMER}
        </span>
        <span className="text-[11px] text-slate-500">{footerExtra}</span>
      </footer>
    </div>
  );
}
