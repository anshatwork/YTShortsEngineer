"use client";

import { useState } from "react";
import {
  useEditJob,
  useSubmitSplitScreenEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { Reveal } from "@/components/landing/Reveal";
import { API_HOST_URL } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { SplitScreenAudioMode } from "@/types/api";

type BgMode = "default" | "upload" | "url";

export default function CreateSplitScreenPage() {
  const [fgFile, setFgFile] = useState<File | null>(null);
  const [fgUploadId, setFgUploadId] = useState<string | null>(null);
  const fgUpload = useUploadAsset();

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
    bgMode === "default" ||
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
        ...(bgMode === "upload" && bgUploadId ? { background_upload_id: bgUploadId } : {}),
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
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-center py-2.5">
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Compositor
        </span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Headline + format specimen */}
      <Reveal>
        <div className="pt-8 pb-8 border-b border-rule-soft grid sm:grid-cols-[1fr_auto] items-start gap-8">
          <div>
            <p className="kicker mb-3">split-screen format</p>
            <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
              Compose a{" "}
              <span className="display-italic text-[var(--color-mark)]">9:16 short</span>.
            </h1>
            <p className="mt-4 font-mono text-[12px] text-ink-muted max-w-md leading-relaxed">
              Upload a foreground video and pair it with a gameplay background.
              The pipeline stacks them vertically and exports a portrait short.
            </p>
            <div className="mt-5 flex gap-6">
              <div className="flex items-center gap-2">
                <div className="w-[18px] h-[2px] bg-ink" />
                <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-ink-muted">
                  foreground · top 50%
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-[18px] h-[2px]"
                  style={{
                    backgroundImage:
                      "repeating-linear-gradient(90deg, var(--color-ink) 0 3px, transparent 3px 5px)",
                  }}
                />
                <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-ink-muted">
                  background · bottom 50%
                </span>
              </div>
            </div>
          </div>

          {/* 9:16 format specimen */}
          <div
            className="border border-ink overflow-hidden flex flex-col shrink-0"
            style={{ width: "72px", height: "128px" }}
            aria-hidden
          >
            {/* Foreground zone */}
            <div className="flex-1 bg-ink flex items-center justify-center">
              <span className="font-mono text-[7px] tracking-[0.12em] uppercase text-paper/45">
                fg
              </span>
            </div>
            {/* Hairline separator */}
            <div className="h-px bg-paper/20" />
            {/* Background zone */}
            <div
              className="flex-1 flex items-center justify-center"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(45deg, transparent 0 6px, rgba(20,17,11,0.1) 6px 7px)",
              }}
            >
              <span className="font-mono text-[7px] tracking-[0.12em] uppercase text-ink/35">
                bg
              </span>
            </div>
          </div>
        </div>
      </Reveal>

      {/* Form */}
      <form onSubmit={onSubmit} className="max-w-2xl mt-0 divide-y divide-rule-soft">

        {/* ── Foreground ───────────────────────────────────────────── */}
        <fieldset className="space-y-3 pt-6 pb-7">
          <legend className="kicker mb-3">Foreground video — top half</legend>

          <label
            className={cn(
              "flex items-center justify-between border border-ink bg-paper h-12 px-3 cursor-pointer transition-colors hover:bg-paper-2",
              fgUpload.isPending && "opacity-60 cursor-wait",
            )}
          >
            <span className="font-mono text-[13px] text-ink truncate pr-2">
              {fgUpload.isPending
                ? `Uploading ${fgFile?.name ?? ""}…`
                : fgFile?.name || "Choose video file (.mp4, .mov, .webm)"}
            </span>
            <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft shrink-0">
              {fgUploadId ? "✓ Ready" : "Browse"}
            </span>
            <input
              type="file"
              accept="video/*"
              onChange={onUploadFg}
              className="hidden"
            />
          </label>

          <p className="font-mono text-[10px] text-ink-muted leading-relaxed">
            This video will occupy the top 50% of the frame. Its audio is kept or discarded based on your audio setting below.
          </p>
        </fieldset>

        {/* ── Background ───────────────────────────────────────────── */}
        <fieldset className="space-y-4 pt-6 pb-7">
          <legend className="kicker mb-3">Background — bottom half</legend>

          <div className="flex border border-ink h-9">
            {(["default", "upload", "url"] as BgMode[]).map((m, i) => (
              <button
                key={m}
                type="button"
                onClick={() => setBgMode(m)}
                className={cn(
                  "flex-1 font-mono text-[11px] tracking-[0.15em] uppercase transition-colors",
                  i > 0 && "border-l border-ink",
                  bgMode === m ? "bg-ink text-paper" : "bg-paper text-ink-soft hover:text-ink",
                )}
              >
                {m === "url" ? "YouTube URL" : m === "upload" ? "Upload" : "Default"}
              </button>
            ))}
          </div>

          {bgMode === "default" && (
            <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
              Uses the server&apos;s <code className="text-ink">BACKGROUND_VIDEO_PATH</code> environment variable — typically a Minecraft or GTA parkour loop.
            </p>
          )}

          {bgMode === "upload" && (
            <label
              className={cn(
                "flex items-center justify-between border border-ink bg-paper h-12 px-3 cursor-pointer transition-colors hover:bg-paper-2",
                bgUpload.isPending && "opacity-60 cursor-wait",
              )}
            >
              <span className="font-mono text-[13px] text-ink truncate pr-2">
                {bgUpload.isPending
                  ? `Uploading ${bgFile?.name ?? ""}…`
                  : bgFile?.name || "Choose background video"}
              </span>
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft shrink-0">
                {bgUploadId ? "✓ Ready" : "Browse"}
              </span>
              <input type="file" accept="video/*" onChange={onUploadBg} className="hidden" />
            </label>
          )}

          {bgMode === "url" && (
            <div className="flex items-center border border-ink bg-paper h-11 px-3">
              <span className="font-mono text-ink-soft text-[13px] pr-2">https://</span>
              <input
                type="text"
                value={bgUrl.replace(/^https?:\/\//, "")}
                onChange={(e) => {
                  const raw = e.target.value;
                  setBgUrl(raw.startsWith("http") ? raw : raw ? `https://${raw}` : "");
                }}
                placeholder="www.youtube.com/watch?v=…"
                className="flex-1 bg-transparent border-0 outline-none font-mono text-[13px] text-ink placeholder:text-ink-soft"
              />
            </div>
          )}
        </fieldset>

        {/* ── Audio ────────────────────────────────────────────────── */}
        <fieldset className="space-y-3 pt-6 pb-7">
          <legend className="kicker mb-3">Audio source</legend>

          <div className="flex border border-ink h-9 max-w-xs">
            {(
              [
                ["fetched_video", "Foreground"],
                ["bg_video", "Background"],
              ] as [SplitScreenAudioMode, string][]
            ).map(([value, label], i) => (
              <button
                key={value}
                type="button"
                onClick={() => setAudioMode(value)}
                className={cn(
                  "flex-1 font-mono text-[11px] tracking-[0.15em] uppercase transition-colors",
                  i > 0 && "border-l border-ink",
                  audioMode === value
                    ? "bg-ink text-paper"
                    : "bg-paper text-ink-soft hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="font-mono text-[10px] text-ink-muted leading-relaxed">
            Which video&apos;s audio track to keep in the final render.
          </p>
        </fieldset>

        {/* ── Render ───────────────────────────────────────────────── */}
        <div className="pt-6 pb-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className={cn(
              "group h-12 px-6 font-mono text-[11px] tracking-[0.2em] uppercase border border-ink transition-colors flex items-center gap-3",
              canSubmit
                ? "bg-ink text-paper hover:bg-ink-muted"
                : "bg-paper-2 text-ink-soft cursor-not-allowed",
            )}
          >
            {submit.isPending ? (
              <>
                <span className="w-3 h-3 rounded-full border border-paper border-t-transparent animate-spin" />
                Rendering
              </>
            ) : (
              <>
                Render split-screen
                <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* ── Result ─────────────────────────────────────────────────── */}
      {editJobId && (
        <div className="max-w-2xl mt-10 border-t border-ink pt-6 space-y-4">
          <div className="flex items-center gap-3">
            <p className="kicker">{result.data?.status ?? "queued"}</p>
            <span className="font-mono text-[10px] tracking-[0.12em] text-ink-muted num-tabular">
              {editJobId.slice(0, 8)}
            </span>
            {(!result.data || result.data.status === "running" || result.data.status === "queued") && (
              <span className="inline-block w-[6px] h-[6px] rounded-full bg-ink ink-pulse" />
            )}
          </div>

          {result.data?.error && (
            <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap">
              {result.data.error}
            </p>
          )}

          {videoUrl && (
            <video
              controls
              src={videoUrl}
              className="border border-ink bg-black"
              style={{ maxHeight: "420px", aspectRatio: "9/16" }}
            />
          )}
        </div>
      )}
    </div>
  );
}
