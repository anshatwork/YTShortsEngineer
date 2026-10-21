"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_RUNNING } from "@/lib/constants";
import { useJobStore } from "@/store/jobStore";
import type {
  YouTubeUploadJob,
  YouTubeUploadListResponse,
  YouTubeUploadRequest,
} from "@/types/api";

/** Broad key for a user's upload lists — invalidate it after any submit so the
 * per-clip badges refetch and pick up the newly queued upload. */
export const YOUTUBE_UPLOADS_KEY = "youtube-uploads";

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
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();
  return useMutation({
    mutationFn: (body: YouTubeUploadRequest) => api.submitYouTubeUpload(body),
    onSuccess: () => {
      // Refetch per-clip upload lists so the card's Published/Uploading badge
      // reflects the new upload (prefix match covers every clip-specific key).
      queryClient.invalidateQueries({ queryKey: [YOUTUBE_UPLOADS_KEY] });
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── List a clip's upload history (drives the persistent "Published" badge) ───
export function useYouTubeUploadsForClip(
  parentJobId: string | null,
  clipId: string | null,
) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<YouTubeUploadListResponse>({
    queryKey: [YOUTUBE_UPLOADS_KEY, userId, parentJobId, clipId],
    queryFn: () =>
      api.listYouTubeUploads({
        parent_job_id: parentJobId ?? undefined,
        clip_id: clipId ?? undefined,
      }),
    enabled: !!parentJobId && userId !== null,
    // Poll only while an upload is in flight; once terminal we stop and rely on
    // mount / window-focus / post-submit invalidation to stay fresh.
    refetchInterval: (query) => {
      const uploads = query.state.data?.uploads ?? [];
      const inFlight = uploads.some(
        (u) => u.status === "running" || u.status === "queued",
      );
      return inFlight ? POLL_INTERVAL_RUNNING : false;
    },
    refetchOnWindowFocus: true,
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
