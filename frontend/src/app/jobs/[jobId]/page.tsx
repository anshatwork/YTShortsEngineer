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
import { Reveal } from "@/components/landing/Reveal";
import { Masthead } from "@/components/ui/Masthead";
import { Button } from "@/components/ui/Button";
import { formatRelative } from "@/lib/utils";
import { ApiError } from "@/lib/api";

interface Props {
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

  const hasClips =
    job?.status === "done" &&
    (clips.length > 0 || (job.clips && job.clips.length > 0));

  return (
    <div className="-mt-2 space-y-8">
      {/* Masthead */}
      <Masthead
        left={
          <Link href="/workspace" className="hover:text-ink transition-colors">
            ← workspace
          </Link>
        }
        title="The Pipeline"
        right={<span className="num-tabular">{jobId.slice(0, 8)}</span>}
      />

      {/* Job header */}
      <Reveal>
        <div className="pb-6 border-b border-rule-soft grid sm:grid-cols-[1fr_auto] items-end gap-4">
          <div>
            <p className="kicker mb-3">pipeline job</p>
            <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(1.6rem,4vw,2.75rem)]">
              {job?.video_title ?? (
                <span className="font-mono text-[1.4rem] text-ink-muted">
                  {jobId.slice(0, 16)}…
                </span>
              )}
            </h1>
          </div>
          {job && (
            <div className="flex items-center gap-4 pb-1">
              <JobStatusBadge status={job.status} />
              <span className="font-mono text-[10px] tracking-[0.14em] text-ink-muted num-tabular">
                {formatRelative(job.created_at)}
              </span>
            </div>
          )}
        </div>
      </Reveal>

      {/* Pipeline tracker */}
      <Reveal delay={0.04}>
        <div>
          <p className="kicker mb-3">Pipeline stages</p>
          <PipelineTracker />
        </div>
      </Reveal>

      {/* Error notice */}
      {(job?.status === "failed" || isError) && (
        <div className="border border-[var(--color-mark)] bg-paper px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="kicker text-[var(--color-mark)] mb-2">
                {job?.status === "failed" ? "Job failed" : "Error"}
              </p>
              <p className="font-mono text-[12px] text-ink-muted leading-relaxed">
                {job?.status === "failed"
                  ? "Something went wrong while processing this job. You can re-run it with the same settings."
                  : "We couldn't load this job. Check your connection and try again."}
              </p>
              {job?.error && (
                <p className="font-mono text-[11px] text-ink mt-3 whitespace-pre-wrap break-words">
                  {job.error}
                </p>
              )}
            </div>
            {job?.status === "failed" && (
              <Button
                onClick={() => rerun.mutate(jobId)}
                pending={rerun.isPending}
                pendingLabel="Re-running"
                className="shrink-0 h-10"
              >
                ↻ Rerun
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Output clips */}
      <div>
        <Reveal>
          <div className="border-b border-ink pb-3 mb-6">
            <p className="kicker mb-2">Output</p>
            <h2 className="font-display text-[clamp(1.25rem,2.5vw,1.75rem)] leading-tight">
              Rendered <span className="display-italic">clips</span>.
            </h2>
          </div>
        </Reveal>
        {hasClips ? (
          <ClipsGrid
            clips={clips.length > 0 ? clips : job!.clips ?? []}
            jobId={jobId}
          />
        ) : (
          <WaitingCanvas status={job?.status} />
        )}
      </div>

      {/* Log panel */}
      <Reveal delay={0.02}>
        <div>
          <p className="kicker mb-3">Run log</p>
          <LogViewer />
        </div>
      </Reveal>
    </div>
  );
}

function JobNotFound({ jobId }: { jobId: string }) {
  return (
    <div className="-mt-2">
      <Masthead
        left={
          <Link href="/workspace" className="hover:text-ink transition-colors">
            ← workspace
          </Link>
        }
        title="The Pipeline"
        right={<span className="text-[var(--color-mark)]">404</span>}
      />

      <div className="mt-10">
        <p className="kicker text-[var(--color-mark)] mb-3">Not found</p>
        <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(1.6rem,4vw,2.75rem)] mb-4">
          This job doesn&apos;t{" "}
          <span className="display-italic text-[var(--color-mark)]">exist</span>.
        </h1>
        <p className="font-mono text-[11px] tracking-[0.1em] text-ink-muted mb-1">
          <span className="text-ink-soft">id</span>{" "}
          <span className="text-ink">{jobId}</span>
        </p>
        <p className="font-mono text-[12px] text-ink-muted max-w-lg leading-relaxed mt-3 mb-7">
          This job does not exist or you do not have access to it. It may have
          been submitted by a different account, or the job ID may be incorrect.
        </p>
        <Link
          href="/workspace"
          className="group inline-flex items-center gap-3 h-12 px-6 bg-ink text-paper hover:bg-ink-muted transition-colors font-mono text-[11px] tracking-[0.2em] uppercase"
        >
          ← Back to workspace
        </Link>
      </div>
    </div>
  );
}

function WaitingCanvas({ status }: { status?: string }) {
  if (status === "failed") return null;

  const label =
    status === "queued" ? "Queued — awaiting worker" : "Pipeline running";

  return (
    <section className="border border-ink bg-paper px-4 py-14 flex flex-col items-center gap-4">
      <span
        aria-hidden
        className="inline-block w-[7px] h-[7px] rounded-full bg-ink ink-pulse"
      />
      <p className="font-display text-[clamp(1rem,2vw,1.4rem)] text-ink-muted leading-snug">
        {label}
      </p>
      <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft">
        Clips appear here when done
      </p>
    </section>
  );
}
