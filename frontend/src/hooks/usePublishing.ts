"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import { POLL_INTERVAL_LIST, POLL_INTERVAL_FALLBACK, POLL_INTERVAL_RUNNING, SSE_ENABLED } from "@/lib/constants";
import type {
  ApproveSourceRequest,
  ApproveUploadRequest,
  PublishingJob,
  PublishingStartRequest,
  PublishingReviewRequest,
} from "@/types/api";

const TERMINAL = new Set(["complete", "failed", "cancelled"]);
// The two human gates: the run idles here until the user decides, so polling
// can stop (SSE already delivered the snapshot; nothing changes until we act).
const GATES = new Set(["waiting_for_source_approval", "waiting_for_context_review", "waiting_for_upload_approval"]);

// ─── List ─────────────────────────────────────────────────────────────────────
export function usePublishingList() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  return useQuery({
    queryKey: ["publishing-list", userId],
    queryFn: () => api.listPublishing(),
    enabled: userId !== null,
    refetchInterval: POLL_INTERVAL_LIST,
    staleTime: 2_000,
  });
}

// ─── Poll one run (SSE is primary; this is the safety-net poll) ─────────────────
export function usePublishing(id: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  return useQuery<PublishingJob, Error>({
    queryKey: ["publishing", userId, id],
    queryFn: () => api.getPublishing(id!),
    enabled: !!id && userId !== null,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
      return failureCount < 2;
    },
    refetchInterval: (query) => {
      if (query.state.error) return false;
      const status = query.state.data?.status;
      if (!status || TERMINAL.has(status) || GATES.has(status)) return false;
      return SSE_ENABLED ? POLL_INTERVAL_FALLBACK : POLL_INTERVAL_RUNNING;
    },
    staleTime: 1_000,
  });
}

// ─── Start ──────────────────────────────────────────────────────────────────--
export function useStartPublishing() {
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: PublishingStartRequest) => api.startPublishing(body),
    onError: (err: Error) => addToast(err.message, "error"),
  });
}

// ─── Approve source (decision #1) ───────────────────────────────────────────---
export function useApproveSource(id: string) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: ApproveSourceRequest) => api.approvePublishingSource(id, body),
    onSuccess: (job) => {
      queryClient.setQueryData(["publishing", user?.id ?? null, id], job);
    },
    onError: (err: Error) => addToast(err.message, "error"),
  });
}

// ─── Approve upload (decision #2) ───────────────────────────────────────────---
export function useApproveUpload(id: string) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: ApproveUploadRequest) => api.approvePublishingUpload(id, body),
    onSuccess: (job) => {
      queryClient.setQueryData(["publishing", user?.id ?? null, id], job);
    },
    onError: (err: Error) => addToast(err.message, "error"),
  });
}

export function useReviewPublishing(id: string) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: PublishingReviewRequest) => api.reviewPublishing(id, body),
    onSuccess: (job) => queryClient.setQueryData(["publishing", user?.id ?? null, id], job),
    onError: (err: Error) => addToast(err.message, "error"),
  });
}
