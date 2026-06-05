"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_RUNNING } from "@/lib/constants";
import { useJobStore } from "@/store/jobStore";
import type { YouTubeUploadJob, YouTubeUploadRequest } from "@/types/api";

// ─── Connection status ────────────────────────────────────────────────────────
export function useYouTubeAuthStatus() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery({
    queryKey: ["youtube-auth-status", userId],
    queryFn: () => api.getYouTubeAuthStatus(),
    enabled: userId !== null,
    staleTime: 30_000,
  });
}

// ─── Begin the Connect-YouTube OAuth flow ─────────────────────────────────────
// Fetches the Google consent URL, then performs a full-page redirect. Google
// returns to the backend callback, which redirects back here with ?youtube=…
export function useConnectYouTube() {
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: () => api.getYouTubeLoginUrl(),
    onSuccess: ({ authorization_url }) => {
      window.location.href = authorization_url;
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Disconnect ───────────────────────────────────────────────────────────────
export function useDisconnectYouTube() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: () => api.disconnectYouTube(),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["youtube-auth-status", user?.id ?? null],
      });
      addToast("YouTube disconnected.", "success");
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Submit an upload ───────────────────────────────────────────────────────--
export function useSubmitYouTubeUpload() {
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: YouTubeUploadRequest) => api.submitYouTubeUpload(body),
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Poll a single upload job until terminal ──────────────────────────────────
export function useYouTubeUpload(uploadId: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<YouTubeUploadJob>({
    queryKey: ["youtube-upload", userId, uploadId],
    queryFn: () => api.getYouTubeUpload(uploadId!),
    enabled: !!uploadId && userId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "running" || status === "queued") return POLL_INTERVAL_RUNNING;
      return false;
    },
    staleTime: 1_000,
  });
}
