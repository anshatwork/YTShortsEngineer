"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_RUNNING } from "@/lib/constants";
import { useJobStore } from "@/store/jobStore";
import type {
  EditJob,
  EditJobListResponse,
  MusicEditRequest,
  SplitScreenEditRequest,
  TTSEditRequest,
} from "@/types/api";

// ─── Poll a single edit job until it reaches a terminal state ─────────────────
export function useEditJob(editJobId: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<EditJob>({
    queryKey: ["edit-job", userId, editJobId],
    queryFn: () => api.getEditJob(editJobId!),
    enabled: !!editJobId && userId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "running" || status === "queued") return POLL_INTERVAL_RUNNING;
      return false;
    },
    staleTime: 1_000,
  });
}

// ─── List edit jobs (optionally filtered by parent job + clip) ────────────────
export function useEditJobsForClip(
  parentJobId: string | null,
  clipId: string | null,
) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<EditJobListResponse>({
    queryKey: ["edit-jobs", userId, parentJobId, clipId],
    queryFn: () =>
      api.listEditJobs({
        parent_job_id: parentJobId ?? undefined,
        clip_id: clipId ?? undefined,
      }),
    enabled: !!parentJobId && userId !== null,
    refetchInterval: 4_000,
  });
}

function editJobsQueryKey(userId: string | null) {
  return ["edit-jobs", userId] as const;
}

// ─── Submit TTS edit ──────────────────────────────────────────────────────────
export function useSubmitTtsEdit() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: TTSEditRequest) => api.submitTtsEdit(body),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: editJobsQueryKey(user?.id ?? null) });
      queryClient.setQueryData(
        ["edit-job", user?.id ?? null, job.edit_job_id],
        job,
      );
      addToast(`TTS edit queued (${job.edit_job_id.slice(0, 8)})`, "success");
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Submit music-mix edit ────────────────────────────────────────────────────
export function useSubmitMusicEdit() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: MusicEditRequest) => api.submitMusicEdit(body),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: editJobsQueryKey(user?.id ?? null) });
      queryClient.setQueryData(
        ["edit-job", user?.id ?? null, job.edit_job_id],
        job,
      );
      addToast(`Music mix queued (${job.edit_job_id.slice(0, 8)})`, "success");
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Submit split-screen edit ─────────────────────────────────────────────────
export function useSubmitSplitScreenEdit() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: SplitScreenEditRequest) => api.submitSplitScreenEdit(body),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: editJobsQueryKey(user?.id ?? null) });
      queryClient.setQueryData(
        ["edit-job", user?.id ?? null, job.edit_job_id],
        job,
      );
      addToast(`Split-screen queued (${job.edit_job_id.slice(0, 8)})`, "success");
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Upload an audio/video asset ──────────────────────────────────────────────
export function useUploadAsset() {
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (file: File) => api.uploadAsset(file),
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}
