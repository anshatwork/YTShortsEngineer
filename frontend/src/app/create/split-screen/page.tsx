"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useEditJob,
  useSubmitSplitScreenEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { API_HOST_URL } from "@/lib/constants";
import type { SplitScreenAudioMode } from "@/types/api";

export default function CreateSplitScreenPage() {
  // Foreground (top half) — required upload
  const [fgFile, setFgFile] = useState<File | null>(null);
  const [fgUploadId, setFgUploadId] = useState<string | null>(null);
  const fgUpload = useUploadAsset();

  // Background (bottom half)
  type BgMode = "default" | "upload" | "url";
  const [bgMode, setBgMode] = useState<BgMode>("default");
  const [bgUrl, setBgUrl] = useState("");
  const [bgFile, setBgFile] = useState<File | null>(null);
  const [bgUploadId, setBgUploadId] = useState<string | null>(null);
  const bgUpload = useUploadAsset();

  const [audioMode, setAudioMode] = useState<SplitScreenAudioMode>("fetched_video");

  const submit = useSubmitSplitScreenEdit();
  const [editJobId, setEditJobId] = useState<string | null>(null);
  const result = useEditJob(editJobId);

  const onUploadFg = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFgFile(f);
    setFgUploadId(null);
    if (f) setFgUploadId((await fgUpload.mutateAsync(f)).upload_id);
  };

  const onUploadBg = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setBgFile(f);
    setBgUploadId(null);
    if (f) setBgUploadId((await bgUpload.mutateAsync(f)).upload_id);
  };

  const bgReady =
    (bgMode === "default") ||
    (bgMode === "upload" && !!bgUploadId) ||
    (bgMode === "url" && /^https?:\/\//.test(bgUrl.trim()));

  const canSubmit = !!fgUploadId && bgReady && !submit.isPending;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || !fgUploadId) return;
    setEditJobId(null);
    submit.mutate(
      {
        foreground_upload_id: fgUploadId,
        audio_mode: audioMode,
        ...(bgMode === "default" ? { background_default: true } : {}),
        ...(bgMode === "upload" && bgUploadId
          ? { background_upload_id: bgUploadId }
          : {}),
        ...(bgMode === "url" ? { background_url: bgUrl.trim() } : {}),
      },
      { onSuccess: (job) => setEditJobId(job.edit_job_id) },
    );
  };

  const videoUrl =
    result.data?.status === "done" && result.data.output_url
      ? `${API_HOST_URL}${result.data.output_url}`
      : null;

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
          Split-screen
        </span>
        <Link
          href="/create"
          className="font-mono text-[10px] tracking-[0.18em] text-ink-muted hover:text-ink uppercase transition-colors"
        >
          ← create
        </Link>
      </div>

      <form onSubmit={onSubmit} className="space-y-6">
        {/* Foreground */}
        <section className="border border-ink bg-paper p-4 space-y-3">
          <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
            Foreground video (top half)
          </p>
          <div className="flex items-center gap-3 font-mono text-[11px] text-ink">
            <input
              type="file"
              accept="video/*"
              onChange={onUploadFg}
              className="font-mono text-[11px]"
            />
            {fgUpload.isPending && <span className="text-ink-muted">uploading…</span>}
            {fgUploadId && (
              <span className="text-ink-soft truncate max-w-[12rem]">
                ✓ {fgFile?.name}
              </span>
            )}
          </div>
        </section>

        {/* Background */}
        <section className="border border-ink bg-paper p-4 space-y-3">
          <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
            Background (bottom half)
          </p>
          <div className="flex border border-ink font-mono text-[10px] tracking-[0.18em] uppercase">
            {(["default", "upload", "url"] as BgMode[]).map((m, i) => (
              <button
                key={m}
                type="button"
                onClick={() => setBgMode(m)}
                className={`flex-1 h-8 ${i > 0 ? "border-l border-ink" : ""} ${
                  bgMode === m
                    ? "bg-ink text-paper"
                    : "bg-paper text-ink hover:bg-paper-2"
                } transition-colors`}
              >
                {m === "url" ? "youtube url" : m}
              </button>
            ))}
          </div>

          {bgMode === "default" && (
            <p className="font-mono text-[11px] text-ink-muted">
              Uses the server&apos;s <code>BACKGROUND_VIDEO_PATH</code> env (e.g. a
              Minecraft / GTA parkour loop).
            </p>
          )}
          {bgMode === "upload" && (
            <div className="flex items-center gap-3 font-mono text-[11px] text-ink">
              <input
                type="file"
                accept="video/*"
                onChange={onUploadBg}
                className="font-mono text-[11px]"
              />
              {bgUpload.isPending && <span className="text-ink-muted">uploading…</span>}
              {bgUploadId && (
                <span className="text-ink-soft truncate max-w-[12rem]">
                  ✓ {bgFile?.name}
                </span>
              )}
            </div>
          )}
          {bgMode === "url" && (
            <input
              type="url"
              value={bgUrl}
              onChange={(e) => setBgUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=…"
              className="w-full border border-ink bg-paper-2 p-2 font-mono text-[11px] text-ink"
            />
          )}

          {/* Audio source */}
          <fieldset className="flex flex-wrap items-center gap-4 font-mono text-[11px] text-ink">
            <legend className="text-ink-soft">Audio</legend>
            {(
              [
                ["fetched_video", "foreground"],
                ["bg_video", "background"],
              ] as [SplitScreenAudioMode, string][]
            ).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="split-audio-mode"
                  checked={audioMode === value}
                  onChange={() => setAudioMode(value)}
                />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!canSubmit}
              className="border border-ink px-3 py-1 font-mono text-[11px] tracking-[0.18em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
            >
              {submit.isPending ? "submitting…" : "render split-screen"}
            </button>
          </div>
        </section>
      </form>

      {/* Result */}
      {editJobId && (
        <section className="border border-ink bg-paper p-4 space-y-2">
          <p className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-muted">
            {result.data?.status ?? "queued"} · {editJobId.slice(0, 8)}
          </p>
          {result.data?.error && (
            <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap">
              {result.data.error}
            </p>
          )}
          {videoUrl && (
            <video controls src={videoUrl} className="max-h-[400px] aspect-[9/16] bg-black" />
          )}
        </section>
      )}
    </div>
  );
}
