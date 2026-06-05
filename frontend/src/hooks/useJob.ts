"use client";

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_RUNNING } from "@/lib/constants";
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
      if (status === "running" || status === "queued") return POLL_INTERVAL_RUNNING;
      return false;
    },
    staleTime: 1_000,
  });
}
