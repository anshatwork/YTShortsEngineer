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
    // Recorded to the debug buffer only (dev mirrors to console via pushDebug).
    // This boundary runs outside providers, so no toast/store is available.
    pushDebug("error", "global-boundary", `Global error: ${error.message}`, {
      digest: error.digest,
      stack: error.stack,
    });
  }, [error]);

  const recover = () => (unstable_retry ?? reset)?.();

  // Runs outside the root layout, so globals.css / Tailwind tokens are NOT
  // applied here — the palette is inlined to keep the crash screen on-brand.
  const PAPER = "#FBFAF5";
  const INK = "#14110B";
  const INK_MUTED = "#6B6657";
  const INK_SOFT = "#948E7B";
  const MARK = "#6E2A1A";

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          background: PAPER,
          color: INK,
          fontFamily:
            '"Iowan Old Style", "Cormorant Garamond", Georgia, serif',
          WebkitFontSmoothing: "antialiased",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
        }}
      >
        <div style={{ width: "100%", maxWidth: "640px" }}>
          <div style={{ borderTop: `1px solid ${INK}`, paddingTop: "1.25rem" }}>
            <p
              style={{
                margin: 0,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "10.5px",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: MARK,
              }}
            >
              Something went wrong
            </p>
            <h2
              style={{
                margin: "0.75rem 0 0",
                fontSize: "clamp(1.6rem, 4vw, 2.5rem)",
                fontWeight: 400,
                lineHeight: 1.02,
                letterSpacing: "-0.01em",
                color: INK,
              }}
            >
              The page failed to <span style={{ fontStyle: "italic", color: MARK }}>load</span>.
            </h2>
            <p
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                marginTop: "1rem",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "12px",
                lineHeight: 1.6,
                color: INK_MUTED,
              }}
            >
              {error.message}
            </p>
            {error.digest && (
              <p
                style={{
                  marginTop: "0.5rem",
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: "11px",
                  color: INK_SOFT,
                }}
              >
                digest: {error.digest}
              </p>
            )}
            <button
              type="button"
              onClick={recover}
              style={{
                marginTop: "1.5rem",
                height: "40px",
                padding: "0 1.5rem",
                border: "none",
                background: INK,
                color: PAPER,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                textTransform: "uppercase",
                fontSize: "11px",
                letterSpacing: "0.2em",
                cursor: "pointer",
              }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
