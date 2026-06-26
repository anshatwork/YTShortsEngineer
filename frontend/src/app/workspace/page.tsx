"use client";

import { useJobs } from "@/hooks/useJobs";
import { CommandBar } from "@/components/workspace/CommandBar";
import { JobsTable } from "@/components/dashboard/JobsTable";
import { Reveal } from "@/components/landing/Reveal";

export default function WorkspacePage() {
  const { data, isLoading, isFetching, refetch } = useJobs();

  const jobs    = data?.jobs ?? [];
  const running = jobs.filter((j) => j.status === "running").length;
  const queued  = jobs.filter((j) => j.status === "queued").length;
  const done    = jobs.filter((j) => j.status === "done").length;
  const failed  = jobs.filter((j) => j.status === "failed").length;
  const active  = running + queued;

  return (
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span className="hidden sm:inline">Pipeline · Control</span>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Workshop
        </span>
        <span className="num-tabular">
          {data ? `${String(data.total).padStart(2, "0")} jobs` : "—"}
        </span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Headline + live status strip (moved from Navbar) */}
      <Reveal>
        <div className="pt-8 pb-8 border-b border-rule-soft grid sm:grid-cols-[1fr_auto] items-end gap-6">
          <div>
            <p className="kicker mb-3">Active pipeline</p>
            <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
              Your{" "}
              <span className="display-italic text-[var(--color-mark)]">workspace</span>.
            </h1>
          </div>

          {data && (
            <div className="flex items-center gap-5 font-mono text-[11px] tracking-[0.18em] text-ink-muted pb-1">
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={`inline-block w-[6px] h-[6px] rounded-full shrink-0 ${
                    active > 0 ? "bg-ink ink-pulse" : "border border-ink-soft"
                  }`}
                />
                <span className={active > 0 ? "text-ink" : ""}>
                  {String(active).padStart(2, "0")} active
                </span>
              </span>
              <span aria-hidden className="text-ink-soft">/</span>
              <span className="num-tabular">{String(done).padStart(2, "0")} done</span>
              {failed > 0 && (
                <>
                  <span aria-hidden className="text-ink-soft">/</span>
                  <span className="num-tabular text-[var(--color-mark)]">
                    {String(failed).padStart(2, "0")} failed
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </Reveal>

      {/* Command bar */}
      <Reveal delay={0.05}>
        <div className="mt-8">
          <CommandBar />
        </div>
      </Reveal>

      {/* Jobs section */}
      <div className="mt-12">
        <Reveal>
          <div className="flex items-end justify-between border-b border-ink pb-3">
            <div>
              <p className="kicker mb-2">Job history</p>
              <h2 className="font-display text-[clamp(1.5rem,3vw,2.25rem)] leading-tight">
                Recent <span className="display-italic">runs</span>.
              </h2>
            </div>
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted hover:text-ink disabled:opacity-40 transition-colors mb-1"
            >
              <span
                aria-hidden
                className={`inline-block w-[6px] h-[6px] rounded-full bg-ink transition-opacity ${
                  isFetching ? "ink-pulse opacity-100" : "opacity-0"
                }`}
              />
              Refresh
            </button>
          </div>
        </Reveal>

        <div className="mt-5">
          {isLoading ? (
            <div className="flex items-center gap-3 py-4">
              <span className="w-4 h-4 rounded-full border border-ink border-t-transparent animate-spin" />
              <span className="font-mono text-[11px] tracking-[0.12em] text-ink-soft uppercase">
                Loading jobs…
              </span>
            </div>
          ) : (
            <JobsTable jobs={data?.jobs ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
