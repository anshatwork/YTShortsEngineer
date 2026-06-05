"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import {
  useConnectYouTube,
  useDisconnectYouTube,
  useYouTubeAuthStatus,
} from "@/hooks/useYouTube";

/**
 * Compact navbar control for the connected-YouTube account.
 *   - Not connected → "Connect YT" button (starts the OAuth flow)
 *   - Connected     → "YT · <channel>" with a disconnect affordance
 *
 * Also consumes the ?youtube=connected|error query param that the backend
 * OAuth callback appends when it redirects back here.
 */
export function YouTubeConnect() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { addToast } = useJobStore();

  const { data: status } = useYouTubeAuthStatus();
  const connect = useConnectYouTube();
  const disconnect = useDisconnectYouTube();

  // Handle the OAuth callback redirect (?youtube=connected|error).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const result = params.get("youtube");
    if (!result) return;

    if (result === "connected") {
      addToast("YouTube connected.", "success");
      queryClient.invalidateQueries({
        queryKey: ["youtube-auth-status", user?.id ?? null],
      });
    } else if (result === "error") {
      addToast("YouTube connection failed.", "error");
    }

    // Strip the param so a refresh doesn't re-toast.
    params.delete("youtube");
    const qs = params.toString();
    window.history.replaceState(
      {},
      "",
      window.location.pathname + (qs ? `?${qs}` : ""),
    );
  }, [queryClient, addToast, user?.id]);

  if (status?.connected) {
    return (
      <button
        type="button"
        onClick={() => disconnect.mutate()}
        disabled={disconnect.isPending}
        title={`Connected as ${status.channel_title ?? "YouTube"} — click to disconnect`}
        className="hidden sm:flex items-center gap-1.5 font-mono text-[10px] tracking-[0.15em] uppercase text-ink-muted hover:text-[var(--color-mark)] transition-colors disabled:opacity-50"
      >
        <Upload size={13} strokeWidth={1.4} className="text-ink" />
        <span className="max-w-[100px] truncate hidden lg:inline">
          {status.channel_title ?? "YouTube"}
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => connect.mutate()}
      disabled={connect.isPending}
      className="hidden sm:flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft hover:text-ink transition-colors disabled:opacity-50"
    >
      <Upload size={13} strokeWidth={1.4} />
      {connect.isPending ? "…" : "Connect YT"}
    </button>
  );
}
