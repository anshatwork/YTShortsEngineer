"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Upload } from "lucide-react";
import type { ClipResult, PrivacyStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import {
  useConnectYouTube,
  useSubmitYouTubeUpload,
  useYouTubeAuthStatus,
  useYouTubeUpload,
} from "@/hooks/useYouTube";

interface PublishDialogProps {
  clip: ClipResult;
  jobId: string;
  onClose: () => void;
}

const PRIVACY_OPTIONS: { value: PrivacyStatus; label: string; hint: string }[] = [
  { value: "private", label: "PRIVATE", hint: "only you" },
  { value: "unlisted", label: "UNLISTED", hint: "link only" },
  { value: "public", label: "PUBLIC", hint: "everyone" },
];

/**
 * Modal for publishing a single clip to YouTube. Renders a Connect prompt when
 * the account isn't linked, a metadata form once connected, and a live status
 * panel (queued → running → done/failed) after submission.
 */
export function PublishDialog({ clip, jobId, onClose }: PublishDialogProps) {
  const { data: authStatus, isLoading: authLoading } = useYouTubeAuthStatus();
  const connect = useConnectYouTube();
  const submit = useSubmitYouTubeUpload();

  const [title, setTitle] = useState(clip.title ?? clip.hook_text ?? "");
  const [description, setDescription] = useState(clip.summary ?? "");
  const [tags, setTags] = useState((clip.hashtags ?? []).join(", "));
  const [privacy, setPrivacy] = useState<PrivacyStatus>("private");
  const [uploadId, setUploadId] = useState<string | null>(null);

  const { data: uploadJob } = useYouTubeUpload(uploadId);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const connected = authStatus?.connected ?? false;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit.mutate(
      {
        parent_job_id: jobId,
        clip_id: clip.clip_id,
        title: title.trim(),
        description: description.trim(),
        tags: tags
          .split(",")
          .map((t) => t.trim().replace(/^#/, ""))
          .filter(Boolean),
        privacy_status: privacy,
      },
      { onSuccess: (job) => setUploadId(job.upload_id) },
    );
  };

  const status = uploadJob?.status;
  const inFlight = status === "queued" || status === "running" || submit.isPending;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-ink/40"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Publish to YouTube"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md border border-ink bg-paper"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-11 border-b border-ink">
          <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.18em] uppercase text-ink">
            <Upload size={14} strokeWidth={1.4} />
            Publish to YouTube
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
        <div className="p-4 sm:p-5">
          {authLoading ? (
            <p className="font-mono text-[11px] tracking-[0.15em] text-ink-muted uppercase">
              Checking connection…
            </p>
          ) : uploadJob && status === "done" ? (
            <SuccessPanel url={uploadJob.video_url} onClose={onClose} />
          ) : uploadJob && status === "failed" ? (
            <FailedPanel error={uploadJob.error} onRetry={() => setUploadId(null)} />
          ) : uploadId ? (
            <ProgressPanel status={status} />
          ) : !connected ? (
            <ConnectPrompt
              loading={connect.isPending}
              onConnect={() => connect.mutate()}
            />
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="font-mono text-[10px] tracking-[0.15em] text-ink-soft uppercase">
                Channel: {authStatus?.channel_title ?? "connected"}
              </p>

              <Field label="Title">
                <input
                  type="text"
                  value={title}
                  maxLength={100}
                  required
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 h-9 border border-ink bg-paper text-[13px] text-ink focus:outline-none focus:bg-paper-2"
                />
              </Field>

              <Field label="Description">
                <textarea
                  value={description}
                  rows={3}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-ink bg-paper text-[13px] text-ink resize-none focus:outline-none focus:bg-paper-2"
                />
              </Field>

              <Field label="Tags (comma-separated)">
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="shorts, viral"
                  className="w-full px-3 h-9 border border-ink bg-paper text-[13px] text-ink focus:outline-none focus:bg-paper-2"
                />
              </Field>

              <div>
                <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-2">
                  Privacy
                </span>
                <div className="grid grid-cols-3 border border-ink">
                  {PRIVACY_OPTIONS.map((opt, i) => {
                    const active = privacy === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setPrivacy(opt.value)}
                        className={cn(
                          "px-2 py-2 flex flex-col items-start gap-0.5 transition-colors",
                          i < 2 && "border-r border-ink",
                          active ? "bg-ink text-paper" : "text-ink hover:bg-paper-2",
                        )}
                      >
                        <span className="font-mono text-[11px] tracking-[0.1em]">
                          {opt.label}
                        </span>
                        <span
                          className={cn(
                            "font-mono text-[9px] tracking-[0.14em] uppercase",
                            active ? "text-paper/70" : "text-ink-soft",
                          )}
                        >
                          {opt.hint}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <button
                type="submit"
                disabled={inFlight || !title.trim()}
                className="w-full h-10 flex items-center justify-center gap-2 border border-ink bg-ink text-paper font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-paper hover:text-ink transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submit.isPending ? "Submitting…" : "Publish"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-1.5">
        {label}
      </span>
      {children}
    </label>
  );
}

function ConnectPrompt({
  loading,
  onConnect,
}: {
  loading: boolean;
  onConnect: () => void;
}) {
  return (
    <div className="space-y-4 text-center py-2">
      <p className="text-[13px] text-ink-muted leading-relaxed">
        Connect a YouTube account to publish clips directly.
      </p>
      <button
        type="button"
        onClick={onConnect}
        disabled={loading}
        className="w-full h-10 flex items-center justify-center gap-2 border border-ink bg-ink text-paper font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-paper hover:text-ink transition-colors disabled:opacity-50"
      >
        <Upload size={14} strokeWidth={1.4} />
        {loading ? "Redirecting…" : "Connect YouTube"}
      </button>
    </div>
  );
}

function ProgressPanel({ status }: { status?: string }) {
  const label =
    status === "running" ? "Uploading to YouTube…" : "Queued — starting upload…";
  return (
    <div className="flex items-center gap-3 py-4">
      <span className="inline-block w-4 h-4 border border-ink border-t-transparent rounded-full animate-spin" />
      <span className="font-mono text-[11px] tracking-[0.15em] text-ink uppercase">
        {label}
      </span>
    </div>
  );
}

function SuccessPanel({
  url,
  onClose,
}: {
  url: string | null;
  onClose: () => void;
}) {
  return (
    <div className="space-y-4 py-2">
      <p className="font-mono text-[11px] tracking-[0.15em] text-ink uppercase">
        ✓ Published
      </p>
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 text-[13px] text-ink underline underline-offset-2 break-all"
        >
          <ExternalLink size={13} strokeWidth={1.4} className="shrink-0" />
          {url}
        </a>
      )}
      <button
        type="button"
        onClick={onClose}
        className="w-full h-10 border border-ink bg-paper text-ink font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-ink hover:text-paper transition-colors"
      >
        Done
      </button>
    </div>
  );
}

function FailedPanel({
  error,
  onRetry,
}: {
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-4 py-2">
      <p className="font-mono text-[11px] tracking-[0.15em] uppercase text-[var(--color-mark)]">
        ✕ Upload failed
      </p>
      {error && (
        <p className="text-[12px] text-ink-muted leading-relaxed break-words">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={onRetry}
        className="w-full h-10 border border-ink bg-paper text-ink font-mono text-[11px] tracking-[0.18em] uppercase hover:bg-ink hover:text-paper transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
