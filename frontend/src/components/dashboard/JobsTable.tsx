"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import type { Job } from "@/types/api";
import { formatRelative } from "@/lib/utils";
import { useRerunJob } from "@/hooks/useRerunJob";
import { JobStatusBadge } from "./JobStatusBadge";

interface Props {
  jobs: Job[];
}

export function JobsTable({ jobs }: Props) {
  const rerun = useRerunJob();

  if (jobs.length === 0) return <EmptyState />;

  return (
    <section>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.map((job, i) => {
          const failed   = job.status === "failed";
          const running  = job.status === "running";
          const rerunning = rerun.isPending && rerun.variables === job.job_id;

          return (
            <motion.div
              key={job.job_id}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{
                duration: 0.55,
                delay: Math.min(i, 5) * 0.05,
                ease: [0.22, 1, 0.36, 1],
              }}
              className="group relative border border-ink bg-paper flex flex-col overflow-hidden discover-card"
            >
              {/* Running-job indicator — thin animated top rule */}
              {running && (
                <div
                  aria-hidden
                  className="absolute top-0 inset-x-0 h-[2px] bg-ink ink-pulse"
                />
              )}

              {/* Stretched link — z-0 so interactive children sit above it */}
              <Link
                href={`/jobs/${job.job_id}`}
                aria-label={`Open job ${job.video_title || job.job_id}`}
                className="absolute inset-0 z-0 hover:bg-paper-2/60 transition-colors"
              />

              {/* ── Status band ──────────────────────────────────────────── */}
              <div className="pointer-events-none relative z-10 flex items-center justify-between px-4 py-3 border-b border-ink">
                <JobStatusBadge status={job.status} />
                <span className="font-mono text-[10px] tracking-[0.14em] text-ink-soft num-tabular">
                  {formatRelative(job.created_at)}
                </span>
              </div>

              {/* ── Body ─────────────────────────────────────────────────── */}
              <div className="pointer-events-none relative z-10 px-4 pt-3 pb-3 flex-1 flex flex-col gap-1.5">
                <h3
                  className="font-display text-[15px] leading-snug text-ink line-clamp-2"
                  title={job.video_title ?? job.job_id}
                >
                  {job.video_title || (
                    <span className="font-mono text-[12px] text-ink-muted">{job.job_id}</span>
                  )}
                </h3>
                <p className="font-mono text-[11px] tracking-[0.1em] text-ink-soft truncate">
                  {stageLabel(job)}
                </p>
              </div>

              {/* ── Footer strip ─────────────────────────────────────────── */}
              <div className="relative z-10 flex items-center justify-between px-4 py-2.5 border-t border-rule-soft">
                {/* Metadata */}
                <div className="pointer-events-none flex items-center gap-4 font-mono text-[10px] tracking-[0.14em] text-ink-soft num-tabular uppercase">
                  <span>{String(job.clips?.length ?? 0).padStart(2, "0")} clips</span>
                  <span>{totalDuration(job)}</span>
                </div>

                {/* Action */}
                {failed ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      rerun.mutate(job.job_id);
                    }}
                    disabled={rerunning}
                    title="Re-run this job with the same settings"
                    className="font-mono text-[10px] tracking-[0.15em] uppercase text-[var(--color-mark)] hover:text-ink disabled:opacity-50 transition-colors"
                  >
                    {rerunning ? "…" : "↻ Rerun"}
                  </button>
                ) : (
                  <span className="pointer-events-none font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft group-hover:text-ink transition-colors flex items-center gap-1">
                    Open
                    <span className="transition-transform duration-200 group-hover:translate-x-0.5">→</span>
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Footer count */}
      <p className="mt-4 font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase num-tabular">
        {String(jobs.length).padStart(2, "0")} jobs
      </p>
    </section>
  );
}

function stageLabel(job: Job): string {
  if (job.status === "queued")  return "waiting in queue";
  if (job.status === "done")    return "pipeline complete";
  if (job.status === "failed")  return job.error ? job.error.slice(0, 60) : "pipeline error";
  return (job.current_node ?? "starting").toLowerCase().replace(/_/g, " ");
}

function totalDuration(job: Job): string {
  const clips = job.clips ?? [];
  if (clips.length === 0) return "—";
  const totalSec = clips.reduce(
    (acc, c) => acc + Math.max(0, c.timestamp_range[1] - c.timestamp_range[0]),
    0,
  );
  const m = Math.floor(totalSec / 60);
  const s = Math.round(totalSec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function EmptyState() {
  return (
    <section className="border border-rule-soft py-16 px-6 flex flex-col items-center text-center gap-4">
      <p className="kicker">No jobs yet</p>
      <p className="font-display text-[clamp(1.25rem,2.5vw,1.75rem)] text-ink-muted leading-snug max-w-sm">
        Paste a YouTube link into the command bar and press{" "}
        <span className="font-mono text-ink">↵</span> to dispatch the first job.
      </p>
    </section>
  );
}
