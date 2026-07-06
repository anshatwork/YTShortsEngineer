"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { pushDebug } from "@/lib/debugLog";

/**
 * Route-segment error boundary. Catches runtime/render errors thrown anywhere
 * under the root layout, records them to the debug buffer (so they show up in
 * "Copy debug logs"), and offers a recovery action.
 *
 * Next.js 16: `unstable_retry` re-fetches + re-renders the segment; `reset`
 * clears the boundary without re-fetching. We prefer retry and fall back to
 * reset for forward/backward compatibility.
 */
export default function Error({
  error,
  reset,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  useEffect(() => {
    // Recorded to the debug buffer (and mirrored to the console in dev only,
    // via pushDebug). No raw console call — it would leak in production.
    pushDebug("error", "boundary", `Route error: ${error.message}`, {
      digest: error.digest,
      stack: error.stack,
    });
  }, [error]);

  const recover = () => (unstable_retry ?? reset)?.();

  return (
    <div className="border border-ink bg-paper p-6 font-mono text-[13px] text-ink-muted">
      <h2 className="text-[var(--color-mark)] text-[11px] tracking-[0.2em] uppercase mb-3">
        Something went wrong
      </h2>
      <p className="whitespace-pre-wrap break-words text-ink mb-1">{error.message}</p>
      {error.digest && (
        <p className="text-ink-soft text-[11px] mb-4">digest: {error.digest}</p>
      )}
      <button
        type="button"
        onClick={recover}
        className="mt-2 h-8 px-4 border border-ink text-[10px] tracking-[0.2em] uppercase text-ink hover:bg-paper-2/40 transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
