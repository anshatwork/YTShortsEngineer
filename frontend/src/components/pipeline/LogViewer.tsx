"use client";

import { useState } from "react";
import { useJobStore } from "@/store/jobStore";
import { cn } from "@/lib/utils";
import { getDebugDump } from "@/lib/debugLog";

/**
 * Collapsed by default to a 28px single-line bar. Click to expand into a
 * mono-text panel pinned beneath. No editorial framing — just a log
 * disclosure.
 */
export function LogViewer() {
  const { logs, addToast } = useJobStore();
  const [expanded, setExpanded] = useState(false);

  if (logs.length === 0) return null;

  const visible = expanded ? logs : logs.slice(-1);

  // Copy the full client-side diagnostic trace (API calls, SSE, query errors,
  // error-boundary catches) so it can be pasted when reporting an issue.
  const copyDebug = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(getDebugDump());
      addToast("Debug logs copied to clipboard", "info");
    } catch {
      addToast("Could not copy debug logs", "error");
    }
  };

  return (
    <section className="border border-ink bg-paper">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full h-8 px-4 flex items-center justify-between border-b border-rule-soft font-mono text-[10px] tracking-[0.2em] uppercase text-ink-muted hover:text-ink transition-colors"
      >
        <span className="flex items-center gap-3">
          <span>Log</span>
          <span className="text-ink-soft num-tabular">
            {String(logs.length).padStart(3, "0")} lines
          </span>
        </span>
        <span className="flex items-center gap-3">
          <span
            role="button"
            tabIndex={0}
            onClick={copyDebug}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") copyDebug(e as unknown as React.MouseEvent);
            }}
            className="text-[10px] tracking-[0.15em] text-ink-soft hover:text-ink transition-colors cursor-pointer"
          >
            Copy debug logs
          </span>
          <span aria-hidden className="text-[11px] tracking-normal text-ink-soft">
            {expanded ? "↓ collapse" : "↑ expand"}
          </span>
        </span>
      </button>

      <div
        className={cn(
          "px-4 py-2 overflow-y-auto bg-paper-2/40 font-mono text-[11px] leading-[1.55] transition-[max-height] duration-200",
          expanded ? "max-h-72" : "max-h-7",
        )}
      >
        {visible.map((line, i) => (
          <p
            key={i}
            className={cn(
              "whitespace-pre-wrap truncate",
              line.startsWith("[ERROR]") ? "text-[var(--color-mark)]" : "text-ink-muted",
            )}
          >
            {line}
          </p>
        ))}
      </div>
    </section>
  );
}
