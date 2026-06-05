import { cn } from "@/lib/utils";
import type { JobStatus } from "@/types/api";

/**
 * Compact status indicator — ink dot + mono label. Used in tables and
 * detail headers where the badge is UI chrome, not editorial copy.
 */
const config: Record<JobStatus, { label: string; dot: string; text: string }> = {
  queued:  { label: "queued",  dot: "border border-ink-soft",            text: "text-ink-soft" },
  running: { label: "running", dot: "bg-ink ink-pulse",                  text: "text-ink" },
  done:    { label: "done",    dot: "bg-ink",                            text: "text-ink" },
  failed:  { label: "failed",  dot: "bg-[var(--color-mark)]",            text: "text-[var(--color-mark)]" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, dot, text } = config[status];
  return (
    <span className={cn("inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.16em]", text)}>
      <span aria-hidden className={cn("inline-block w-[7px] h-[7px] rounded-full", dot)} />
      {label}
    </span>
  );
}
