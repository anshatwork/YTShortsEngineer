"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { pushDebug } from "@/lib/debugLog";

/**
 * Root-level error boundary. Replaces the root layout when an error is thrown
 * in the layout/template itself, so it must define its own <html>/<body>.
 * It runs OUTSIDE the providers, so it cannot use the Zustand store or toasts —
 * it logs to the debug buffer and console only.
 *
 * Next.js 16: prefer `unstable_retry`, fall back to `reset`.
 */
export default function GlobalError({
  error,
  reset,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  useEffect(() => {
    pushDebug("error", "global-boundary", `Global error: ${error.message}`, {
      digest: error.digest,
      stack: error.stack,
    });
    console.error("[global-boundary] root error", error);
  }, [error]);

  const recover = () => (unstable_retry ?? reset)?.();

  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          padding: "2rem",
          maxWidth: "720px",
          margin: "0 auto",
        }}
      >
        <h2 style={{ fontSize: "12px", letterSpacing: "0.2em", textTransform: "uppercase", color: "#c0392b" }}>
          Something went wrong
        </h2>
        <p style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: "0.75rem" }}>
          {error.message}
        </p>
        {error.digest && (
          <p style={{ fontSize: "11px", color: "#888" }}>digest: {error.digest}</p>
        )}
        <button
          type="button"
          onClick={recover}
          style={{
            marginTop: "1rem",
            height: "32px",
            padding: "0 1rem",
            border: "1px solid currentColor",
            background: "transparent",
            textTransform: "uppercase",
            fontSize: "10px",
            letterSpacing: "0.2em",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
