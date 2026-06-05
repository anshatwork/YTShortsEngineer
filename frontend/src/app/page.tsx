"use client";

import { useJobs } from "@/hooks/useJobs";
import { CommandBar } from "@/components/workspace/CommandBar";
import { JobsTable } from "@/components/dashboard/JobsTable";

export default function WorkspacePage() {
  const { data, isLoading, isFetching, refetch } = useJobs();

  return (
    <div className="space-y-6">
      <CommandBar />

      {/* Section ribbon — label + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
            Recent jobs
          </span>
          <span className="font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase num-tabular">
            {data ? `${String(data.total).padStart(2, "0")} total` : "loading…"}
          </span>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="font-mono text-[10px] tracking-[0.18em] text-ink-muted hover:text-ink uppercase disabled:opacity-40 transition-colors flex items-center gap-2"
        >
          <span
            aria-hidden
            className={`inline-block w-[6px] h-[6px] rounded-full bg-ink ${isFetching ? "ink-pulse" : ""}`}
          />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="border border-rule-soft px-4 py-12 font-mono text-[11px] tracking-[0.18em] text-ink-soft uppercase">
          Loading jobs…
        </div>
      ) : (
        <JobsTable jobs={data?.jobs ?? []} />
      )}
    </div>
  );
}
