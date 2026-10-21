"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import { getAccessToken } from "@/lib/api";
import { pushDebug } from "@/lib/debugLog";
import { API_BASE_URL, SSE_ENABLED } from "@/lib/constants";
import type { PublishingJob } from "@/types/api";

const TERMINAL = new Set(["complete", "failed", "cancelled"]);

/**
 * Subscribe to real-time publishing-run progress via Server-Sent Events.
 *
 * Mirrors useJobEvents: writes each snapshot/update into the React Query cache
 * under the SAME key usePublishing reads, so the detail page updates live as the
 * agent walks discovering → waiting_for_source_approval → generating → scoring →
 * evaluating → waiting_for_upload_approval → uploading → complete.
 *
 * Auth: EventSource can't set headers, so the Supabase token rides as ?token=.
 */
export function usePublishingEvents(id: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const queryClient = useQueryClient();
  const setConnectionStatus = useJobStore((s) => s.setConnectionStatus);

  useEffect(() => {
    if (!SSE_ENABLED || !id || userId === null) return;

    let cancelled = false;
    let closedTerminal = false;
    let es: EventSource | null = null;

    (async () => {
      const token = await getAccessToken();
      if (cancelled) return;

      const url = new URL(`${API_BASE_URL}/publishing/${id}/events`);
      if (token) url.searchParams.set("token", token);

      es = new EventSource(url.toString());
      setConnectionStatus("connecting");

      const onData = (e: MessageEvent) => {
        let job: PublishingJob;
        try {
          job = JSON.parse(e.data) as PublishingJob;
        } catch (err) {
          pushDebug("warn", "sse", `publishing ${id}: failed to parse event`, {
            error: err,
            raw: typeof e.data === "string" ? e.data.slice(0, 500) : e.data,
          });
          return;
        }
        queryClient.setQueryData(["publishing", userId, id], job);
        if (TERMINAL.has(job.status)) {
          closedTerminal = true;
          es?.close();
          setConnectionStatus("idle");
        }
      };

      es.addEventListener("snapshot", onData as EventListener);
      es.addEventListener("update", onData as EventListener);
      es.onopen = () => setConnectionStatus("live");
      es.onerror = () => {
        if (!closedTerminal) {
          setConnectionStatus("reconnecting");
          pushDebug("warn", "sse", `publishing ${id}: stream error, reconnecting`);
        }
      };
    })();

    return () => {
      cancelled = true;
      es?.close();
      setConnectionStatus("idle");
    };
  }, [id, userId, queryClient, setConnectionStatus]);
}
