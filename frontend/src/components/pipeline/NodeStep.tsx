"use client";

import type { NodeState } from "@/types/api";
import { cn } from "@/lib/utils";

interface NodeStepProps {
  node: NodeState;
  index: number;
  total: number;
}

/**
 * One segment of the horizontal PipelineStrip — a connector pair on either
 * side of a status dot, with the stage label set below.
 */
export function NodeStep({ node, index, total }: NodeStepProps) {
  const isFirst = index === 0;
  const isLast  = index === total - 1;

  const isRunning = node.status === "running";
  const isDone    = node.status === "done";
  const isError   = node.status === "error";

  // Connector colors — left segment "before" the dot, right segment "after"
  const leftIsDone  = isDone || isError || index > 0;  // there is something to the left to draw
  const rightIsDone = isDone;

  return (
    <li className="flex-1 flex flex-col items-center">
      <div className="flex items-center w-full h-6">
        <span
          aria-hidden
          className={cn(
            "flex-1 h-px transition-colors",
            isFirst && "invisible",
            leftIsDone && index > 0 ? "bg-ink" : "bg-rule-soft",
          )}
        />

        {/* Dot */}
        <span
          aria-hidden
          className={cn(
            "shrink-0 mx-1.5 w-[10px] h-[10px] rounded-full border border-ink transition-colors",
            isDone && "bg-ink",
            isRunning && "bg-ink ink-pulse",
            isError && "bg-[var(--color-mark)] border-[var(--color-mark)]",
            !isDone && !isRunning && !isError && "bg-paper",
          )}
        />

        <span
          aria-hidden
          className={cn(
            "flex-1 h-px transition-colors",
            isLast && "invisible",
            rightIsDone ? "bg-ink" : "bg-rule-soft",
          )}
        />
      </div>

      <span
        className={cn(
          "mt-2 font-mono text-[10px] tracking-[0.16em] uppercase text-center px-1",
          isRunning && "text-ink",
          isDone && "text-ink-muted",
          isError && "text-[var(--color-mark)]",
          !isDone && !isRunning && !isError && "text-ink-soft",
        )}
      >
        {node.node}
      </span>
    </li>
  );
}
