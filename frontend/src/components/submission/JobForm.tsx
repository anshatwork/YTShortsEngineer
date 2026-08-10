"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useSubmitJob } from "@/hooks/useSubmitJob";
import { useUploadAsset } from "@/hooks/useEditJob";
import { useYouTubeAuthStatus } from "@/hooks/useYouTube";
import { isValidYouTubeUrl, cn } from "@/lib/utils";
import { pushDebug } from "@/lib/debugLog";
import { ConfigPanel } from "./ConfigPanel";
import type { JobRequest, ClipMode, SubtitlePosition, SubtitleSize, ThumbnailStyle } from "@/types/api";

type Source = "youtube" | "local";

export function JobForm() {
  // Pre-fill from /new?youtube_url=… (e.g. arriving from the Discover page).
  const searchParams = useSearchParams();
  const prefillUrl = searchParams.get("youtube_url") ?? "";

  const [source, setSource] = useState<Source>("youtube");

  // YouTube mode
  const [url, setUrl] = useState(prefillUrl);
  const [urlError, setUrlError] = useState("");

  // Local-upload mode
  const [videoName, setVideoName] = useState("");
  const [videoPath, setVideoPath] = useState("");
  const [videoUploading, setVideoUploading] = useState(false);
  const [srtName, setSrtName] = useState("");
  const [srtPath, setSrtPath] = useState("");
  const [srtUploading, setSrtUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  // Pipeline options
  const [topN, setTopN] = useState(3);
  const [clipMode, setClipMode] = useState<ClipMode>("portrait");
  const [addSubtitles, setAddSubtitles] = useState(false);
  const [subtitlePosition, setSubtitlePosition] = useState<SubtitlePosition>("bottom");
  const [subtitleSize, setSubtitleSize] = useState<SubtitleSize>("medium");
  const [addTopText, setAddTopText] = useState(false);
  const [addThumbnail, setAddThumbnail] = useState(false);
  const [thumbnailStyle, setThumbnailStyle] = useState<ThumbnailStyle>("auto");
  const [addIntro, setAddIntro] = useState(true);
  const [userContext, setUserContext] = useState("");
  const [autoUpload, setAutoUpload] = useState(false);

  const { mutate, isPending } = useSubmitJob();
  const upload = useUploadAsset();
  const { data: ytAuth } = useYouTubeAuthStatus();
  const ytConnected = ytAuth?.connected ?? false;

  const busy = isPending || videoUploading || srtUploading;

  const handleVideoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploadError("");
    setVideoName(f.name);
    setVideoPath("");
    setVideoUploading(true);
    try {
      const r = await upload.mutateAsync(f);
      setVideoPath(r.path);
    } catch (err) {
      setVideoName("");
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setUploadError(`Video upload failed: ${msg}`);
      pushDebug("error", "upload", `video upload failed: ${f.name}`, err);
    } finally {
      setVideoUploading(false);
    }
  };

  const handleSrtSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".srt")) {
      setUploadError("Subtitles must be a .srt file.");
      return;
    }
    setUploadError("");
    setSrtName(f.name);
    setSrtPath("");
    setSrtUploading(true);
    try {
      const r = await upload.mutateAsync(f);
      setSrtPath(r.path);
    } catch (err) {
      setSrtName("");
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setUploadError(`Subtitle upload failed: ${msg}`);
      pushDebug("error", "upload", `srt upload failed: ${f.name}`, err);
    } finally {
      setSrtUploading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const base = {
      top_n: topN,
      clip_mode: clipMode,
      add_subtitles: addSubtitles,
      subtitle_position: subtitlePosition,
      subtitle_size: subtitleSize,
      add_top_text: addTopText,
      add_thumbnail: addThumbnail,
      thumbnail_style: thumbnailStyle,
      add_intro: addIntro,
      user_context: userContext.trim() || undefined,
      auto_upload: autoUpload,
      auto_upload_privacy: "public" as const,
    };

    let body: JobRequest;
    if (source === "youtube") {
      if (!isValidYouTubeUrl(url)) {
        setUrlError("That doesn't look like a YouTube link.");
        return;
      }
      setUrlError("");
      body = { ...base, youtube_url: url };
    } else {
      if (!videoPath) {
        setUploadError("Upload a video file first.");
        return;
      }
      body = { ...base, video_path: videoPath, video_filename: videoName, srt_path: srtPath || undefined };
    }
    mutate(body);
  };

  const canSubmit =
    source === "youtube" ? !!url : !!videoPath && !videoUploading && !srtUploading;

  return (
    <form onSubmit={handleSubmit} className="divide-y divide-rule-soft">
      {/* SOURCE TYPE TOGGLE */}
      <fieldset className="space-y-3 pt-6 pb-7">
        <legend className="kicker mb-3">Source</legend>
        <div className="flex border border-ink h-10" role="tablist">
          {(["youtube", "local"] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={source === s}
              disabled={busy}
              onClick={() => setSource(s)}
              className={cn(
                "flex-1 font-mono text-[11px] tracking-[0.2em] uppercase transition-colors",
                source === s
                  ? "bg-ink text-paper"
                  : "bg-paper text-ink-soft hover:text-ink",
                s === "local" && "border-l border-ink",
              )}
            >
              {s === "youtube" ? "YouTube URL" : "Local Video"}
            </button>
          ))}
        </div>
      </fieldset>

      {/* YOUTUBE SOURCE */}
      {source === "youtube" && (
        <fieldset className="space-y-2 pt-6 pb-7">
          <legend className="kicker mb-3">Source URL</legend>
          <div
            className={cn(
              "flex items-center border border-ink bg-paper h-12 px-3",
              urlError && "border-[var(--color-mark)]",
            )}
          >
            <span className="font-mono text-ink-soft text-[13px] pr-2">https://</span>
            <input
              id="yt-url"
              type="text"
              value={url.replace(/^https?:\/\//, "")}
              onChange={(e) => {
                const raw = e.target.value;
                setUrl(raw.startsWith("http") ? raw : `https://${raw}`);
                setUrlError("");
              }}
              placeholder="www.youtube.com/watch?v=…"
              className="flex-1 bg-transparent border-0 outline-none font-mono text-[13px] text-ink placeholder:text-ink-soft"
              disabled={busy}
              spellCheck={false}
              autoComplete="off"
            />
          </div>
          {urlError && (
            <p className="font-mono text-[11px] tracking-[0.05em] text-[var(--color-mark)]">
              <span aria-hidden className="mr-2">✕</span>
              {urlError}
            </p>
          )}
        </fieldset>
      )}

      {/* LOCAL UPLOAD SOURCE */}
      {source === "local" && (
        <fieldset className="space-y-3 pt-6 pb-7">
          <legend className="kicker mb-3">Local files</legend>

          {/* Video file (required) */}
          <label
            className={cn(
              "flex items-center justify-between border border-ink bg-paper h-12 px-3 cursor-pointer",
              uploadError && !videoPath && "border-[var(--color-mark)]",
              busy && "cursor-not-allowed opacity-60",
            )}
          >
            <span className="font-mono text-[13px] text-ink truncate pr-2">
              {videoUploading
                ? "Uploading…"
                : videoName || "Choose video file (.mp4, .mov, .webm)"}
            </span>
            <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft shrink-0">
              {videoPath ? "✓ Ready" : "Browse"}
            </span>
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
              className="hidden"
              disabled={busy}
              onChange={handleVideoSelect}
            />
          </label>

          {/* SRT file (optional) */}
          <label
            className={cn(
              "flex items-center justify-between border border-ink bg-paper h-12 px-3 cursor-pointer",
              busy && "cursor-not-allowed opacity-60",
            )}
          >
            <span className="font-mono text-[13px] text-ink truncate pr-2">
              {srtUploading
                ? "Uploading…"
                : srtName || "Choose subtitles (.srt) — optional"}
            </span>
            <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft shrink-0">
              {srtPath ? "✓ Ready" : "Browse"}
            </span>
            <input
              type="file"
              accept=".srt"
              className="hidden"
              disabled={busy}
              onChange={handleSrtSelect}
            />
          </label>

          <p className="font-mono text-[10px] tracking-[0.05em] text-ink-soft leading-relaxed">
            No .srt? Subtitles are auto-generated with Whisper when enabled below.
          </p>

          {uploadError && (
            <p className="font-mono text-[11px] tracking-[0.05em] text-[var(--color-mark)]">
              <span aria-hidden className="mr-2">✕</span>
              {uploadError}
            </p>
          )}
        </fieldset>
      )}

      {/* VIDEO CONTEXT (optional) */}
      <fieldset className="space-y-2 pt-6 pb-7">
        <legend className="kicker mb-3">Video context — optional</legend>
        <textarea
          id="user-context"
          value={userContext}
          onChange={(e) => setUserContext(e.target.value)}
          placeholder="Describe your video so titles, hooks & thumbnails fit it (e.g. 'deep dive on AI agents — focus on the technical payoff'). Leave blank for generic copy."
          rows={3}
          maxLength={500}
          disabled={busy}
          spellCheck
          className="w-full bg-paper border border-ink px-3 py-2 font-mono text-[13px] text-ink placeholder:text-ink-soft outline-none resize-none disabled:opacity-60"
        />
        <p className="font-mono text-[10px] tracking-[0.05em] text-ink-soft">
          {userContext.length}/500 — steers clip selection, titles, hooks & thumbnails.
        </p>
      </fieldset>

      {/* OPTIONS */}
      <fieldset className="space-y-3 pt-6 pb-7">
        <legend className="kicker mb-3">Pipeline options</legend>
        <ConfigPanel
          topN={topN} setTopN={setTopN}
          clipMode={clipMode} setClipMode={setClipMode}
          addSubtitles={addSubtitles} setAddSubtitles={setAddSubtitles}
          subtitlePosition={subtitlePosition} setSubtitlePosition={setSubtitlePosition}
          subtitleSize={subtitleSize} setSubtitleSize={setSubtitleSize}
          addTopText={addTopText} setAddTopText={setAddTopText}
          addThumbnail={addThumbnail} setAddThumbnail={setAddThumbnail}
          thumbnailStyle={thumbnailStyle} setThumbnailStyle={setThumbnailStyle}
          addIntro={addIntro} setAddIntro={setAddIntro}
          disabled={busy}
        />
      </fieldset>

      {/* AUTO-PUBLISH (opt-in, decided before the run) */}
      <fieldset className="space-y-3 pt-6 pb-7">
        <legend className="kicker mb-3">Auto-publish</legend>
        <label
          className={cn(
            "flex items-start gap-3 border border-ink bg-paper px-3 py-3 cursor-pointer",
            autoUpload && "border-[var(--color-mark)]",
            busy && "cursor-not-allowed opacity-60",
          )}
        >
          <input
            type="checkbox"
            checked={autoUpload}
            disabled={busy}
            onChange={(e) => setAutoUpload(e.target.checked)}
            className="mt-0.5 accent-[var(--color-mark)] w-4 h-4 shrink-0"
          />
          <span className="min-w-0">
            <span className="block font-mono text-[11px] tracking-[0.16em] uppercase text-ink">
              Auto-upload every clip to YouTube as{" "}
              <span className="text-[var(--color-mark)]">public</span>
            </span>
            <span className="block font-mono text-[10px] leading-relaxed tracking-[0.04em] text-ink-soft mt-1">
              When the pipeline finishes, all generated clips are published to
              your connected channel automatically — with their AI-generated
              titles, descriptions &amp; tags, and no per-clip review.
            </span>
          </span>
        </label>

        {autoUpload && (
          <p
            className={cn(
              "flex items-start gap-1.5 font-mono text-[10px] leading-relaxed tracking-[0.04em]",
              ytConnected ? "text-[var(--color-mark)]" : "text-ink-muted",
            )}
          >
            <AlertTriangle size={12} strokeWidth={1.6} className="mt-[1px] shrink-0" />
            {ytConnected ? (
              <span>
                Clips will go live publicly on your channel as soon as they
                render. Double-check this is what you want before dispatching.
              </span>
            ) : (
              <span>
                No YouTube account connected yet — connect one (navbar or a clip’s
                Publish dialog) before the job finishes, or the uploads are
                skipped and the clips just wait in your workspace.
              </span>
            )}
          </p>
        )}
      </fieldset>

      {/* Submit */}
      <div className="pt-6 pb-2 flex flex-col sm:flex-row sm:items-center gap-4">
        <button
          type="submit"
          disabled={busy || !canSubmit}
          className={cn(
            "group h-12 px-6 font-mono text-[11px] tracking-[0.2em] uppercase border border-ink transition-colors flex items-center gap-3",
            busy || !canSubmit
              ? "bg-paper-2 text-ink-soft cursor-not-allowed"
              : "bg-ink text-paper hover:bg-ink-muted",
          )}
        >
          {isPending ? (
            <>
              <span className="inline-block w-3 h-3 rounded-full border border-paper border-t-transparent animate-spin" />
              Submitting
            </>
          ) : videoUploading || srtUploading ? (
            <>
              <span className="inline-block w-3 h-3 rounded-full border border-ink border-t-transparent animate-spin" />
              Uploading
            </>
          ) : (
            <>
              Dispatch job
              <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
            </>
          )}
        </button>
        <p className="font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase leading-relaxed">
          {source === "youtube"
            ? "Or paste into the command bar on the workspace."
            : "Video uploads to the backend before the job starts."}
        </p>
      </div>
    </form>
  );
}
