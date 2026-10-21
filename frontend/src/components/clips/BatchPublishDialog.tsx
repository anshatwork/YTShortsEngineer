"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Upload, ExternalLink, AlertTriangle } from "lucide-react";
import type { ClipResult, PrivacyStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import {
  useConnectYouTube,
  useYouTubeAuthStatus,
  useYouTubeUpload,
  YOUTUBE_UPLOADS_KEY,
} from "@/hooks/useYouTube";

interface Props {
  jobId: string;
  clips: ClipResult[];
  privacy: PrivacyStatus;
  /** When true, uploads fire immediately on open (auto-upload, no confirm). */
  autoStart: boolean;
  onClose: () => void;
}

type RowState = { uploadId: string | null; submitError: string | null };

function buildRequest(clip: ClipResult, jobId: string, privacy: PrivacyStatus) {
  return {
    parent_job_id: jobId,
    clip_id: clip.clip_id,
    title: (clip.title || clip.hook_text || clip.clip_id).slice(0, 100),
    description: clip.summary ?? "",
    tags: (clip.hashtags ?? [])
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean),
    privacy_status: privacy,
  };
}

/**
 * Batch upload modal: submits one YouTube upload per selected clip (reusing the
 * single-upload endpoint), then shows live per-clip status. In auto-start mode
 * it fires on open with no confirmation step.
 */
export function BatchPublishDialog({
  jobId,
  clips,
  privacy,
  autoStart,
  onClose,
}: Props) {
  const { data: authStatus, isLoading: authLoading } = useYouTubeAuthStatus();
  const connect = useConnectYouTube();
  const addToast = useJobStore((s) => s.addToast);
  const queryClient = useQueryClient();

  // Freeze the clip set for this dialog's lifetime so the row list is stable
  // (hooks-per-row must not change count). Lazy initializer → captured once.
  const [clipList] = useState(() => clips);

  const [rows, setRows] = useState<RowState[]>(() =>
    clipList.map(() => ({ uploadId: null, submitError: null })),
  );
  const [started, setStarted] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const startedRef = useRef(false);

  const connected = authStatus?.connected ?? false;

  const runUploads = useCallback(async () => {
    if (startedRef.current) return; // guard double-fire (StrictMode / re-entry)
    startedRef.current = true;
    setStarted(true);
    const results = await Promise.allSettled(
      clipList.map((clip) =>
        api.submitYouTubeUpload(buildRequest(clip, jobId, privacy)),
      ),
    );
    setRows(
      results.map((r) =>
        r.status === "fulfilled"
          ? { uploadId: r.value.upload_id, submitError: null }
          : {
              uploadId: null,
              submitError:
                (r.reason as Error)?.message ?? "Failed to queue upload",
            },
      ),
    );
    const failures = results.filter((r) => r.status === "rejected").length;
    if (failures > 0) {
      addToast(`${failures} clip(s) could not be queued.`, "error");
    }
    // Refresh the per-clip badges on the cards behind this dialog.
    queryClient.invalidateQueries({ queryKey: [YOUTUBE_UPLOADS_KEY] });
  }, [clipList, jobId, privacy, addToast, queryClient]);

  // Auto-start: fire once when connected. Deferred to a macrotask so we don't
  // trigger setState synchronously inside the effect; the ref guards re-entry.
  useEffect(() => {
    if (!autoStart || !connected || startedRef.current) return;
    const id = setTimeout(() => void runUploads(), 0);
    return () => clearTimeout(id);
  }, [autoStart, connected, runUploads]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onRowStatus = useCallback((clipId: string, status: string) => {
    setStatuses((prev) =>
      prev[clipId] === status ? prev : { ...prev, [clipId]: status },
    );
  }, []);

  // Aggregate summary across rows.
  const done = rows.filter((r, i) => {
    if (r.submitError) return false;
    return statuses[clipList[i].clip_id] === "done";
  }).length;
  const failed = rows.filter((r, i) => {
    if (r.submitError) return true;
    return statuses[clipList[i].clip_id] === "failed";
  }).length;
  const settled = done + failed;
  const allSettled = started && settled === clipList.length;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-ink/40"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Publish clips to YouTube"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg border border-ink bg-paper flex flex-col max-h-[85vh]"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink shrink-0">
          <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.18em] uppercase text-ink">
            <Upload size={14} strokeWidth={1.4} />
            Publish {clipList.length} clip{clipList.length === 1 ? "" : "s"}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-6 h-6 flex items-center justify-center font-mono text-[12px] text-ink hover:bg-ink hover:text-paper transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-4 sm:p-5 overflow-y-auto">
          {authLoading ? (
            <p className="font-mono text-[11px] tracking-[0.15em] text-ink-muted uppercase">
              Checking connection…
            </p>
          ) : !connected ? (
            <div className="space-y-4 text-center py-2">
              <p className="text-[13px] text-ink-muted leading-relaxed">
                Connect a YouTube account to publish these clips.
              </p>
              <button
                type="button"
                onClick={() => connect.mutate()}
                disabled={connect.isPending}
                className="w-full h-10 flex items-center justify-center gap-2 border border-ink bg-ink text-paper font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-paper hover:text-ink transition-colors disabled:opacity-50"
              >
                <Upload size={14} strokeWidth={1.4} />
                {connect.isPending ? "Redirecting…" : "Connect YouTube"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Privacy + auto-upload note */}
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-soft">
                  Channel: {authStatus?.channel_title ?? "connected"}
                </span>
                <span
                  className={cn(
                    "font-mono text-[10px] tracking-[0.16em] uppercase px-2 py-1 border",
                    privacy === "public"
                      ? "border-[var(--color-mark)] text-[var(--color-mark)]"
                      : "border-ink text-ink",
                  )}
                >
                  {privacy}
                </span>
              </div>

              {!started && autoStart && (
                <p className="flex items-start gap-1.5 font-mono text-[10px] leading-relaxed text-[var(--color-mark)]">
                  <AlertTriangle size={12} strokeWidth={1.6} className="mt-[1px] shrink-0" />
                  Auto-upload is on — publishing without per-clip review…
                </p>
              )}

              {/* Clip rows */}
              <ul className="border border-rule-soft divide-y divide-rule-soft">
                {clipList.map((clip, i) => (
                  <UploadRow
                    key={clip.clip_id}
                    clip={clip}
                    uploadId={rows[i]?.uploadId ?? null}
                    submitError={rows[i]?.submitError ?? null}
                    started={started}
                    onStatus={onRowStatus}
                  />
                ))}
              </ul>

              {/* Footer / action */}
              {!started ? (
                <button
                  type="button"
                  onClick={() => void runUploads()}
                  className="w-full h-10 flex items-center justify-center gap-2 border border-ink bg-ink text-paper font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-paper hover:text-ink transition-colors"
                >
                  <Upload size={14} strokeWidth={1.4} />
                  Publish {clipList.length} clip{clipList.length === 1 ? "" : "s"}
                </button>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-muted num-tabular">
                    {done} done
                    {failed > 0 && (
                      <span className="text-[var(--color-mark)]"> · {failed} failed</span>
                    )}
                    <span className="text-ink-soft"> / {clipList.length}</span>
                  </span>
                  <button
                    type="button"
                    onClick={onClose}
                    className="h-9 px-4 border border-ink bg-paper text-ink font-mono text-[10px] tracking-[0.18em] uppercase hover:bg-ink hover:text-paper transition-colors"
                  >
                    {allSettled ? "Done" : "Close"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** One clip's live status. Polls its upload job (when queued) via useYouTubeUpload. */
function UploadRow({
  clip,
  uploadId,
  submitError,
  started,
  onStatus,
}: {
  clip: ClipResult;
  uploadId: string | null;
  submitError: string | null;
  started: boolean;
  onStatus: (clipId: string, status: string) => void;
}) {
  const { data: job } = useYouTubeUpload(uploadId);
  const status = submitError ? "failed" : job?.status;

  useEffect(() => {
    if (status) onStatus(clip.clip_id, status);
  }, [status, clip.clip_id, onStatus]);

  const title = clip.title || clip.hook_text || clip.clip_id;

  return (
    <li className="flex items-center gap-3 px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-ink truncate">{title}</p>
        <p className="font-mono text-[9px] tracking-[0.12em] uppercase text-ink-soft truncate">
          {clip.clip_id}
        </p>
      </div>
      <StatusPill
        started={started}
        status={status}
        error={submitError ?? job?.error ?? null}
        videoUrl={job?.video_url ?? null}
      />
    </li>
  );
}

function StatusPill({
  started,
  status,
  error,
  videoUrl,
}: {
  started: boolean;
  status?: string;
  error: string | null;
  videoUrl: string | null;
}) {
  if (!started) {
    return (
      <span className="font-mono text-[9px] tracking-[0.16em] uppercase text-ink-soft shrink-0">
        Ready
      </span>
    );
  }
  if (status === "done" && videoUrl) {
    return (
      <a
        href={videoUrl}
        target="_blank"
        rel="noreferrer"
        title={videoUrl}
        className="flex items-center gap-1 font-mono text-[9px] tracking-[0.16em] uppercase text-ink hover:underline shrink-0"
      >
        <ExternalLink size={11} strokeWidth={1.5} /> View
      </a>
    );
  }
  if (status === "failed") {
    return (
      <span
        title={error ?? undefined}
        className="font-mono text-[9px] tracking-[0.16em] uppercase text-[var(--color-mark)] shrink-0"
      >
        ✕ Failed
      </span>
    );
  }
  // queued / running / not-yet-assigned
  return (
    <span className="flex items-center gap-1.5 font-mono text-[9px] tracking-[0.16em] uppercase text-ink-muted shrink-0">
      <span className="inline-block w-3 h-3 border border-ink border-t-transparent rounded-full animate-spin" />
      {status === "running" ? "Uploading" : "Queued"}
    </span>
  );
}
