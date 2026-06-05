"use client";

import { useJobStore } from "@/store/jobStore";
import { NodeStep } from "./NodeStep";

/**
 * Horizontal pipeline strip — always visible at the top of the job detail
 * workspace. Each stage is a dot on a hairline rule; a progress sliver
 * underneath fills as stages complete.
 *
 * Exported as `PipelineTracker` so existing imports continue to resolve;
 * the visual is now a strip rather than the prior vertical run-sheet.
 */
export function PipelineTracker() {
  const { nodes } = useJobStore();
  const totalDone = nodes.filter((n) => n.status === "done").length;
  const progress  = nodes.length > 0 ? (totalDone / nodes.length) * 100 : 0;
  const isFailed  = nodes.some((n) => n.status === "error");
  const currentNode = nodes.find((n) => n.status === "running")?.node ?? null;

  return (
    <section className="border border-ink bg-paper">
      {/* Toolbar — stage name and progress percent */}
      <div className="flex items-center justify-between px-4 h-8 border-b border-rule-soft font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase">
        <span>Pipeline</span>
        <span className="flex items-center gap-3">
          {currentNode && (
            <span className="text-ink">
              <span aria-hidden className="inline-block w-[6px] h-[6px] rounded-full bg-ink ink-pulse mr-2" />
              {currentNode}
            </span>
          )}
          <span className="num-tabular text-ink-soft">
            {String(Math.round(progress)).padStart(3, "0")}%
          </span>
        </span>
      </div>

      {/* The strip */}
      <ol className="flex items-stretch px-4 sm:px-6 pt-5 pb-4">
        {nodes.map((node, i) => (
          <NodeStep
            key={node.node}
            node={node}
            index={i}
            total={nodes.length}
          />
        ))}
      </ol>

      {/* Progress sliver */}
      <div className="h-[2px] bg-rule-soft relative overflow-hidden">
        <span
          className={`absolute inset-y-0 left-0 transition-[width] duration-500 ease-out ${isFailed ? "bg-[var(--color-mark)]" : "bg-ink"}`}
          style={{ width: `${progress}%` }}
          aria-hidden
        />
      </div>
    </section>
  );
}
