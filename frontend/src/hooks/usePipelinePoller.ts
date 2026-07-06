"use client";

import { useEffect, useRef } from "react";
import { useJob } from "@/hooks/useJob";
import { useJobEvents } from "@/hooks/useJobEvents";
import { useJobStore } from "@/store/jobStore";
import { ApiError } from "@/lib/api";
import { pushDebug } from "@/lib/debugLog";

/**
 * Polls GET /api/v1/jobs/{jobId} and syncs results into Zustand store.
 *
 * Toast policy:
 *   - 404 (job not found) — silent. The detail page renders a dedicated
 *     not-found view, so a toast would be noise on top of clear UI.
 *   - Any other error — toasted once. We dedupe by error message so a
 *     repeating failure does not flood the screen.
 *
 * Real-time updates arrive via SSE (useJobEvents), which writes into the same
 * React Query cache useJob reads; useJob keeps a slow fallback poll as a safety
 * net. This hook's interface is unchanged for callers.
 */
export function usePipelinePoller(jobId: string) {
  // Open the live event stream; it pushes updates into the useJob query cache.
  useJobEvents(jobId);

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
    // Route through the debug buffer (dev-gated console mirror) instead of a
    // raw console.error, so nothing leaks to the prod console.
    pushDebug("error", "poller", `Job ${jobId} polling error: ${msg}`, error);
    addToast(msg, "error");
  }, [isError, error, addToast, jobId]);

  return { job, isError, error };
}
