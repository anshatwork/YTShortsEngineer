"use client";

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_RUNNING, POLL_INTERVAL_FALLBACK, SSE_ENABLED } from "@/lib/constants";
import type { Job } from "@/types/api";

export function useJob(jobId: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<Job, Error>({
    // Scope by userId to prevent cross-user cache bleed on shared machines.
    queryKey: ["job", userId, jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: !!jobId && userId !== null,
    // Don't retry 4xx — a missing or unauthorized job will stay that way.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false;
      }
      return failureCount < 2;
    },
    refetchInterval: (query) => {
      if (query.state.error) return false;
      const status = query.state.data?.status;
      if (status !== "running" && status !== "queued") return false;
      // With SSE on, the stream carries real-time updates and polling is only a
      // slow safety net; without it, keep the original fast cadence.
      return SSE_ENABLED ? POLL_INTERVAL_FALLBACK : POLL_INTERVAL_RUNNING;
    },
    staleTime: 1_000,
  });
}
