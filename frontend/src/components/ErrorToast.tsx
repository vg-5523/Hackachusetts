import { useEffect } from "react";
import { ApiError } from "../api";

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body;
    if (!b) return "The request did not succeed.";
    const field = typeof b.field === "string" ? ` (${b.field})` : "";
    switch (e.status) {
      case 422: return `Validation error${field}: ${b.detail}`;
      case 404: return `Not found: ${b.detail}`;
      case 409: return `Conflict: ${b.detail}`;
      case 500: return `Server error: ${b.detail}`;
      default: return b.detail;
    }
  }
  return "The request did not succeed.";
}

/** Transient error toast anchored bottom-right. */
export default function ErrorToast({
  message,
  onDismiss,
}: {
  message: string | null;
  onDismiss: () => void;
}) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDismiss, 6000);
    return () => clearTimeout(t);
  }, [message, onDismiss]);
  if (!message) return null;
  return (
    <div
      role="alert"
      className="fixed bottom-10 right-4 z-50 max-w-sm rounded-lg border border-red-500 bg-red-50 px-4 py-3 text-sm text-red-900 shadow-lg"
    >
      <div className="flex items-start justify-between gap-3">
        <span>{message}</span>
        <button onClick={onDismiss} className="text-red-700 hover:text-white" aria-label="Dismiss">
          ×
        </button>
      </div>
    </div>
  );
}
