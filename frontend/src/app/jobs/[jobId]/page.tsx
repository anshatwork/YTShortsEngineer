"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { usePipelinePoller } from "@/hooks/usePipelinePoller";
import { useRerunJob } from "@/hooks/useRerunJob";
import { useJobStore } from "@/store/jobStore";
import { PipelineTracker } from "@/components/pipeline/PipelineTracker";
import { LogViewer } from "@/components/pipeline/LogViewer";
import { ClipsGrid } from "@/components/clips/ClipsGrid";
import { JobStatusBadge } from "@/components/dashboard/JobStatusBadge";
import { formatRelative } from "@/lib/utils";
import { ApiError } from "@/lib/api";

interface Props {
  // Next.js 16: dynamic route params are a Promise that must be unwrapped.
  params: Promise<{ jobId: string }>;
}

export default function JobPage({ params }: Props) {
  const { jobId } = use(params);
  const { setActiveJob, clips } = useJobStore();
  const { job, isError, error } = usePipelinePoller(jobId);
  const rerun = useRerunJob();

  useEffect(() => {
    setActiveJob(jobId);
  }, [jobId, setActiveJob]);

  const notFound = error instanceof ApiError && error.status === 404;

  if (notFound) {
    return <JobNotFound jobId={jobId} />;
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb / toolbar */}
      <div className="flex items-center justify-between font-mono text-[10px] tracking-[0.18em] uppercase">
        <div className="flex items-center gap-2 text-ink-muted">
          <Link href="/workspace" className="hover:text-ink transition-colors">
            ← workspace
          </Link>
          <span aria-hidden className="text-ink-soft">/</span>
          <span>jobs</span>
          <span aria-hidden className="text-ink-soft">/</span>
          <span className="text-ink">{jobId.slice(0, 12)}</span>
        </div>
        {job && (
          <div className="flex items-center gap-4">
            <JobStatusBadge status={job.status} />
            <span className="text-ink-soft num-tabular">
              {formatRelative(job.created_at)}
            </span>
          </div>
        )}
      </div>

      {/* Pipeline strip — always visible */}
      <PipelineTracker />

      {/* Error notice */}
      {(job?.status === "failed" || isError) && (
        <div className="border border-[var(--color-mark)] bg-paper px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-[var(--color-mark)]">
                {job?.status === "failed" ? "Job failed" : "Error"}
              </p>
              <p className="text-[12px] text-ink-muted mt-1">
                {job?.status === "failed"
                  ? "Something went wrong while processing this job. You can re-run it with the same settings."
                  : "We couldn't load this job. Check your connection and try again."}
              </p>
              {job?.error && (
                <p className="font-mono text-[11px] text-ink mt-2 whitespace-pre-wrap break-words">
                  {job.error}
                </p>
              )}
            </div>
            {job?.status === "failed" && (
              <button
                type="button"
                onClick={() => rerun.mutate(jobId)}
                disabled={rerun.isPending}
                className="shrink-0 h-9 px-4 bg-ink text-paper hover:bg-ink-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-mono text-[10px] tracking-[0.2em] uppercase"
              >
                {rerun.isPending ? "Re-running…" : "↻ Rerun job"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Clips canvas */}
      <div className="pt-2">
        {job?.status === "done" && (clips.length > 0 || (job.clips && job.clips.length > 0)) ? (
          <ClipsGrid clips={clips.length > 0 ? clips : job.clips ?? []} jobId={jobId} />
        ) : (
          <WaitingCanvas status={job?.status} />
        )}
      </div>

      {/* Log panel pinned beneath the workspace */}
      <div className="pt-2">
        <LogViewer />
      </div>
    </div>
  );
}

function JobNotFound({ jobId }: { jobId: string }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <Link href="/workspace" className="hover:text-ink transition-colors">
          ← workspace
        </Link>
        <span aria-hidden className="text-ink-soft">/</span>
        <span>jobs</span>
        <span aria-hidden className="text-ink-soft">/</span>
        <span className="text-ink truncate max-w-[60vw]">{jobId.slice(0, 12)}</span>
      </div>

      <section className="border border-ink bg-paper">
        <div className="px-4 h-8 flex items-center border-b border-rule-soft font-mono text-[10px] tracking-[0.2em] uppercase text-[var(--color-mark)]">
          404 · job not found
        </div>
        <div className="px-6 py-10 flex flex-col items-start gap-4">
          <p className="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-muted">
            <span className="text-ink-soft">id</span>{" "}
            <span className="text-ink">{jobId}</span>
          </p>
          <p className="text-sm text-ink-muted max-w-lg leading-relaxed">
            This job does not exist or you do not have access to it. It may
            have been submitted by a different account, or the job ID may be
            incorrect.
          </p>
          <Link
            href="/workspace"
            className="mt-2 inline-flex items-center gap-3 px-4 h-10 bg-ink text-paper hover:bg-ink-muted transition-colors font-mono text-[11px] tracking-[0.2em] uppercase"
          >
            ← back to workspace
          </Link>
        </div>
      </section>
    </div>
  );
}

function WaitingCanvas({ status }: { status?: string }) {
  if (status === "failed") return null;

  const label =
    status === "queued"
      ? "queued — awaiting worker"
      : "pipeline running";

  return (
    <section className="border border-rule-soft bg-paper px-4 py-12 flex flex-col items-center gap-3">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
        No clips yet
      </p>
      <p className="flex items-center gap-3 font-mono text-[12px] text-ink-muted">
        <span aria-hidden className="inline-block w-[7px] h-[7px] rounded-full bg-ink ink-pulse" />
        {label}
      </p>
    </section>
  );
}
