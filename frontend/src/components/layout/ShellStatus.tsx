"use client";

import { useJobs } from "@/hooks/useJobs";

/**
 * Compact live-status counter shown on the right edge of the top shell.
 * Reads from the same useJobs() query already mounted on the dashboard, so
 * this component piggybacks on its cache and triggers no extra requests.
 */
export function ShellStatus() {
  const { data } = useJobs();
  const jobs = data?.jobs ?? [];

  const running = jobs.filter((j) => j.status === "running").length;
  const queued = jobs.filter((j) => j.status === "queued").length;
  const done = jobs.filter((j) => j.status === "done").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  const active = running + queued;

  return (
    <div className="flex items-center gap-4 font-mono text-[11px] tracking-wider text-ink-muted">
      <span className="flex items-center gap-1.5">
        <span
          aria-hidden
          className={`inline-block w-[6px] h-[6px] rounded-full ${
            active > 0 ? "bg-ink ink-pulse" : "border border-ink-soft"
          }`}
        />
        <span className={active > 0 ? "text-ink" : ""}>
          {String(active).padStart(2, "0")} ACTIVE
        </span>
      </span>
      <span aria-hidden className="text-ink-soft">/</span>
      <span className="num-tabular">
        {String(done).padStart(2, "0")} DONE
      </span>
      {failed > 0 && (
        <>
          <span aria-hidden className="text-ink-soft">/</span>
          <span className="num-tabular text-[var(--color-mark)]">
            {String(failed).padStart(2, "0")} FAILED
          </span>
        </>
      )}
    </div>
  );
}
