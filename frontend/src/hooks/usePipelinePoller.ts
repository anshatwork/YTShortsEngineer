"use client";

import { useEffect, useRef } from "react";
import { useJob } from "@/hooks/useJob";
import { useJobStore } from "@/store/jobStore";
import { ApiError } from "@/lib/api";

/**
 * Polls GET /api/v1/jobs/{jobId} and syncs results into Zustand store.
 *
 * Toast policy:
 *   - 404 (job not found) — silent. The detail page renders a dedicated
 *     not-found view, so a toast would be noise on top of clear UI.
 *   - Any other error — toasted once. We dedupe by error message so a
 *     repeating failure does not flood the screen.
 *
 * When SSE replaces polling in useJob, this component's interface stays.
 */
export function usePipelinePoller(jobId: string) {
  const { data: job, isError, error } = useJob(jobId);
  const updateFromPoll = useJobStore((s) => s.updateFromPoll);
  const addToast = useJobStore((s) => s.addToast);
  const lastToastedRef = useRef<string | null>(null);

  useEffect(() => {
    if (job) updateFromPoll(job);
  }, [job, updateFromPoll]);

  useEffect(() => {
    if (!isError || !error) return;
    // Suppress noisy 404s — the page itself shows a not-found state.
    if (error instanceof ApiError && error.status === 404) return;

    const msg = (error as Error).message;
    if (lastToastedRef.current === msg) return;
    lastToastedRef.current = msg;
    console.error(`[poller] job ${jobId} polling error:`, error);
    addToast(msg, "error");
  }, [isError, error, addToast, jobId]);

  return { job, isError, error };
}
