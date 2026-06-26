"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import { getAccessToken } from "@/lib/api";
import { pushDebug } from "@/lib/debugLog";
import { API_BASE_URL, SSE_ENABLED } from "@/lib/constants";
import type { Job } from "@/types/api";

/**
 * Subscribe to real-time job progress via Server-Sent Events.
 *
 * On each `snapshot` / `update` event we write the fresh Job into the React
 * Query cache under the SAME key `useJob` reads, so every consumer
 * (PipelineTracker, ClipsGrid, the poller) updates with zero extra wiring —
 * SSE simply pushes what polling used to pull.
 *
 * EventSource reconnects automatically if the connection drops; the slow
 * fallback poll in `useJob` is the safety net if the stream never recovers.
 * Disabled entirely when NEXT_PUBLIC_SSE_ENABLED=0 (pure-polling rollback).
 *
 * Auth: EventSource can't set headers, so the Supabase access token is passed
 * as a short-lived `?token=` query param (validated server-side per request).
 */
export function useJobEvents(jobId: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const queryClient = useQueryClient();
  const setConnectionStatus = useJobStore((s) => s.setConnectionStatus);

  useEffect(() => {
    if (!SSE_ENABLED || !jobId || userId === null) return;

    let cancelled = false;
    let closedTerminal = false;
    let es: EventSource | null = null;

    (async () => {
      const token = await getAccessToken();
      if (cancelled) return;

      const url = new URL(`${API_BASE_URL}/jobs/${jobId}/events`);
      if (token) url.searchParams.set("token", token);

      es = new EventSource(url.toString());
      setConnectionStatus("connecting");

      const onData = (e: MessageEvent) => {
        let job: Job;
        try {
          job = JSON.parse(e.data) as Job;
        } catch (err) {
          // Don't silently drop malformed events — record the raw payload so a
          // broken stream is debuggable.
          pushDebug("warn", "sse", `job ${jobId}: failed to parse event`, {
            error: err,
            raw: typeof e.data === "string" ? e.data.slice(0, 500) : e.data,
          });
          return;
        }
        queryClient.setQueryData(["job", userId, jobId], job);
        if (job.status === "done" || job.status === "failed") {
          closedTerminal = true;
          es?.close();
          setConnectionStatus("idle");
        }
      };

      es.addEventListener("snapshot", onData as EventListener);
      es.addEventListener("update", onData as EventListener);
      es.onopen = () => setConnectionStatus("live");
      es.onerror = () => {
        // EventSource retries on its own; reflect the gap in the UI unless we
        // closed it ourselves on a terminal status.
        if (!closedTerminal) {
          setConnectionStatus("reconnecting");
          pushDebug("warn", "sse", `job ${jobId}: stream error, reconnecting`);
        }
      };
    })();

    return () => {
      cancelled = true;
      es?.close();
      setConnectionStatus("idle");
    };
  }, [jobId, userId, queryClient, setConnectionStatus]);
}
