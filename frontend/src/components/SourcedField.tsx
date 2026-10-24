import type { Sourced, FieldStatus } from "@shared/types";

const DOT: Record<FieldStatus, string> = {
  confirmed: "bg-emerald-600",
  unverified: "bg-amber-600",
  conflicted: "bg-rose-500",
  unknown: "bg-slate-400",
};
const EDGE: Record<FieldStatus, string> = {
  confirmed: "before:bg-emerald-500/70",
  unverified: "before:bg-amber-600/70",
  conflicted: "before:bg-rose-500",
  unknown: "before:bg-slate-300",
};
const LABEL: Record<FieldStatus, string> = {
  confirmed: "text-emerald-700",
  unverified: "text-amber-700",
  conflicted: "text-rose-700",
  unknown: "text-slate-500",
};

function isEmptyValue(v: unknown): boolean {
  if (v == null || v === "") return true;
  if (Array.isArray(v)) return v.length === 0;
  return false;
}

function displayValue(v: unknown, status: FieldStatus, path: string): string {
  // A conflicted field keeps its FIRST value, which for allergies is an
  // empty list. Never render an empty conflicted value as "none" / dash:
  // the conflict itself is the signal.
  if (status === "conflicted" && isEmptyValue(v)) {
    if (path === "allergies") return "No allergies reported, but conflicting report";
    return "Conflicting report - see sources";
  }
  if (v == null || v === "") return "\u2014";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "\u2014";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    return Object.values(o).filter((x) => x != null && x !== "").join(" \u00b7 ") || "\u2014";
  }
  return String(v);
}

/**
 * One record field: left status edge + square dot + monospace value.
 * Never a value without its status; click opens provenance; unverified
 * fields get a Confirm.
 */
export default function SourcedField({
  path,
  label,
  field,
  active,
  onOpen,
  onConfirm,
}: {
  path: string;
  label: string;
  field: Sourced<unknown>;
  active: boolean;
  onOpen: () => void;
  onConfirm: () => void;
}) {
  const status = field.status;
  return (
    <div
      className={`relative before:absolute before:left-0 before:top-0 before:h-full before:w-[2px] before:content-[''] ${EDGE[status]} ${
        active
          ? "bg-ink-800"
          : "bg-ink-900 hover:bg-ink-800/60"
      } transition-colors`}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
        aria-label={`Open provenance for ${label}`}
      >
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.15lem] text-slate-500">{label}</div>
          <div className={`font-mono text-sm text-slate-900 ${status === "conflicted" ? "" : "truncate"}`}>{displayValue(field.value, status, path)}</div>
        </div>
        <span className="flex shrink-0 items-center gap-1.5" data-testid="badge">
          <span className={`h-1.5 w-1.5 ${DOT[status]}`} />
          <span className={`text-[9px] font-semibold uppercase tracking-[0.15lem] ${LABEL[status]}`}>
            {status}
          </span>
        </span>
      </button>
      {status === "unverified" && (
        <div className="pb-2 pl-3">
          <button
            type="button"
            onClick={onConfirm}
            className="border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 hover:bg-emerald-500/20"
          >
            Confirm
          </button>
        </div>
      )}
    </div>
  );
}
