"use client";

import Link from "next/link";
import type { Job } from "@/types/api";
import { formatRelative } from "@/lib/utils";
import { JobStatusBadge } from "./JobStatusBadge";

interface Props {
  jobs: Job[];
}

/**
 * Dense data-grid of jobs. Each row links to the job detail. The columns
 * are sized so the most-scanned values (status, ID, stage) sit on the
 * left where the eye lands first.
 */
export function JobsTable({ jobs }: Props) {
  if (jobs.length === 0) return <EmptyState />;

  return (
    <section className="border border-ink bg-paper">
      <Header />
      <ul className="divide-y divide-rule-soft">
        {jobs.map((job) => (
          <li key={job.job_id}>
            <Link
              href={`/jobs/${job.job_id}`}
              className="grid grid-cols-[112px_minmax(0,1.4fr)_minmax(0,1fr)_56px_72px_72px] items-center gap-3 px-4 h-10 hover:bg-paper-2/70 transition-colors"
            >
              <div className="flex items-center">
                <JobStatusBadge status={job.status} />
              </div>
              <div className="font-mono text-[12px] text-ink truncate">
                {job.job_id}
              </div>
              <div className="font-mono text-[11px] text-ink-muted truncate">
                {stageLabel(job)}
              </div>
              <div className="font-mono text-[12px] text-ink-muted num-tabular text-right">
                {String(job.clips?.length ?? 0).padStart(2, "0")}
              </div>
              <div className="font-mono text-[11px] text-ink-muted num-tabular text-right">
                {totalDuration(job)}
              </div>
              <div className="font-mono text-[11px] text-ink-muted num-tabular text-right">
                {formatRelative(job.created_at)}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      <Footer count={jobs.length} />
    </section>
  );
}

function Header() {
  return (
    <div className="grid grid-cols-[112px_minmax(0,1.4fr)_minmax(0,1fr)_56px_72px_72px] gap-3 px-4 h-8 items-center border-b border-ink bg-paper-2/60 font-mono text-[10px] tracking-[0.18em] text-ink-muted uppercase">
      <span>Status</span>
      <span>Job ID</span>
      <span>Stage</span>
      <span className="text-right">Clips</span>
      <span className="text-right">Duration</span>
      <span className="text-right">Created</span>
    </div>
  );
}

function Footer({ count }: { count: number }) {
  return (
    <div className="px-4 h-7 border-t border-rule-soft flex items-center justify-end font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase">
      {String(count).padStart(2, "0")} jobs
    </div>
  );
}

function stageLabel(job: Job): string {
  if (job.status === "queued") return "—";
  if (job.status === "done")   return "complete";
  if (job.status === "failed") return job.error ? "error: " + job.error.slice(0, 40) : "error";
  return (job.current_node ?? "starting").toLowerCase();
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
    <section className="border border-ink bg-paper px-6 py-16 flex flex-col items-center text-center gap-3">
      <p className="font-mono text-[11px] tracking-[0.2em] text-ink-soft uppercase">
        No jobs yet
      </p>
      <p className="text-sm text-ink-muted max-w-sm">
        Paste a YouTube link into the command bar above and press <span className="font-mono text-ink">↵</span> to dispatch the first job.
      </p>
    </section>
  );
}
