/** Format a whole number of seconds as mm:ss or h:mm:ss. */
export function fmtDuration(totalSeconds: number): string {
  const sign = totalSeconds < 0 ? "-" : "";
  let s = Math.abs(Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0
    ? `${sign}${h}:${pad(m)}:${pad(s)}`
    : `${sign}${pad(m)}:${pad(s)}`;
}

/** Seconds between a past ISO timestamp and now (non-negative). */
export function secondsSince(iso: string | null, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now - t) / 1000));
}

/** Seconds from now until a future ISO timestamp (may be negative = overdue). */
export function secondsUntil(iso: string | null, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.floor((t - now) / 1000);
}

/** Short clock time (HH:MM) from an ISO timestamp, or a dash. */
export function fmtClock(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
