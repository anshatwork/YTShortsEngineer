"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import type { AddSongRequest, MusicSearchResponse, MusicTrackListResponse } from "@/types/api";

// ─── List cached music tracks (optionally filtered by theme) ──────────────────
export function useMusicTracks(theme?: string | null) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<MusicTrackListResponse>({
    queryKey: ["music-tracks", userId, theme ?? "all"],
    queryFn: () => api.listMusicTracks({ theme: theme ?? undefined, limit: 200 }),
    enabled: userId !== null,
    staleTime: 30_000,
  });
}

// ─── Per-theme track counts (for chips / badges) ──────────────────────────────
export function useMusicThemes() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery({
    queryKey: ["music-themes", userId],
    queryFn: () => api.listMusicThemes(),
    enabled: userId !== null,
    staleTime: 30_000,
  });
}

// ─── Search free catalogs for named/trending songs ────────────────────────────
// When `conversational` is set, `term` is a natural-language vibe phrase the
// server LLM-interprets into a catalog query + order.
export function useSearchMusic(
  term: string,
  order: string = "popular",
  conversational = false,
) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const q = term.trim();

  return useQuery<MusicSearchResponse>({
    queryKey: ["music-search", userId, q, order, conversational],
    queryFn: () => api.searchMusic(q, order, 12, conversational),
    enabled: userId !== null && q.length > 0,
    staleTime: 60_000,
  });
}

// ─── Browse trending YouTube songs (copyrighted — manual pick only) ───────────
export function useTrendingSongs(enabled = true) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<MusicSearchResponse>({
    queryKey: ["music-trending", userId],
    queryFn: () => api.getTrendingSongs(25),
    enabled: userId !== null && enabled,
    staleTime: 10 * 60_000, // matches the server-side chart cache
  });
}

// ─── Keyword-search YouTube for copyrighted songs (manual pick) ───────────────
// Pricey (100 quota units/search), server-cached. Only fires when there's a term.
export function useYouTubeSongSearch(term: string, order: string = "relevance") {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const q = term.trim();

  return useQuery<MusicSearchResponse>({
    queryKey: ["music-yt-search", userId, q, order],
    queryFn: () => api.searchYouTubeSongs(q, order, 15),
    enabled: userId !== null && q.length > 0,
    staleTime: 10 * 60_000,
  });
}

// ─── Add a searched song into the 'songs' library ─────────────────────────────
export function useAddSong() {
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: AddSongRequest) => api.addSong(body),
    onSuccess: (track) => {
      addToast(`Added “${track.title}” to your songs.`, "success");
      queryClient.invalidateQueries({ queryKey: ["music-tracks"] });
      queryClient.invalidateQueries({ queryKey: ["music-search"] });
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Add a user-supplied track ────────────────────────────────────────────────
export function useUploadMusicTrack() {
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (args: { file: File; theme: string; title?: string }) =>
      api.uploadMusicTrack(args.file, args.theme, args.title),
    onSuccess: (track) => {
      addToast(`Added “${track.title}” to ${track.theme}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["music-tracks"] });
      queryClient.invalidateQueries({ queryKey: ["music-themes"] });
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Delete a user-added track ────────────────────────────────────────────────
export function useDeleteMusicTrack() {
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (args: { trackId: string; theme: string }) =>
      api.deleteMusicTrack(args.trackId, args.theme),
    onSuccess: () => {
      addToast("Track removed.", "success");
      queryClient.invalidateQueries({ queryKey: ["music-tracks"] });
      queryClient.invalidateQueries({ queryKey: ["music-themes"] });
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}

// ─── Trigger a background refresh of the cache ────────────────────────────────
export function useRefreshMusic() {
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: () => api.refreshMusic(),
    onSuccess: (res) => {
      addToast(
        res.queued ? "Music refresh queued — new tracks land shortly." : res.detail,
        res.queued ? "success" : "error",
      );
      // Give the worker a moment, then re-pull the library.
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["music-tracks"] });
        queryClient.invalidateQueries({ queryKey: ["music-themes"] });
      }, 4_000);
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}
