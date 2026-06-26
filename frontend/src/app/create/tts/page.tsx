"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  useEditJob,
  useGenerateTtsScript,
  useSubmitTtsEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { API_HOST_URL } from "@/lib/constants";
import { isValidYouTubeUrl } from "@/lib/utils";
import type { TTSEditRequest, VoicePreset } from "@/types/api";

const VOICE_PRESETS: VoicePreset[] = ["default", "finance", "finance_energetic"];

type Mode = "write" | "summary";
type OutputMode = "audio" | "local_video" | "youtube";

const OUTPUT_LABELS: Record<OutputMode, string> = {
  audio: "save audio",
  local_video: "behind local video",
  youtube: "behind youtube",
};

function CreateTtsForm() {
  // Pre-fill from /create/tts?youtube_url=… (e.g. arriving from the Discover page).
  const searchParams = useSearchParams();
  const prefillUrl = searchParams.get("youtube_url") ?? "";

  const [mode, setMode] = useState<Mode>("write");

  // Summary → script
  const [summary, setSummary] = useState("");
  const [targetSeconds, setTargetSeconds] = useState(30);
  const genScript = useGenerateTtsScript();

  // Script → audio
  const [text, setText] = useState("");
  const [preset, setPreset] = useState<VoicePreset>("default");

  // Output: standalone audio, or narration laid behind a video.
  const [outputMode, setOutputMode] = useState<OutputMode>(
    prefillUrl ? "youtube" : "audio",
  );
  const [videoUrl, setVideoUrl] = useState(prefillUrl);
  const upload = useUploadAsset();
  const [videoUploadId, setVideoUploadId] = useState<string | null>(null);
  const [videoName, setVideoName] = useState("");

  const submit = useSubmitTtsEdit();
  const [editJobId, setEditJobId] = useState<string | null>(null);
  const result = useEditJob(editJobId);

  const onGenerateScript = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;
    const r = await genScript.mutateAsync({
      summary,
      target_seconds: targetSeconds,
    });
    setText(r.script);
  };

  const onPickVideo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setVideoName(file.name);
    setVideoUploadId(null);
    upload.mutate(file, {
      onSuccess: (r) => setVideoUploadId(r.upload_id),
    });
  };

  const outputReady =
    outputMode === "audio" ||
    (outputMode === "local_video" && !!videoUploadId) ||
    (outputMode === "youtube" && isValidYouTubeUrl(videoUrl.trim()));

  const canSubmit = !!text.trim() && outputReady && !submit.isPending;

  const onGenerateAudio = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setEditJobId(null);
    const body: TTSEditRequest = { text, voice_preset: preset };
    if (outputMode === "local_video" && videoUploadId) {
      body.video_upload_id = videoUploadId;
    } else if (outputMode === "youtube") {
      body.video_url = videoUrl.trim();
    }
    submit.mutate(body, {
      onSuccess: (job) => setEditJobId(job.edit_job_id),
    });
  };

  const done = result.data?.status === "done" && result.data.output_url;
  const resultUrl = done ? `${API_HOST_URL}${result.data!.output_url}` : null;
  const isVideoResult =
    !!result.data?.output_url && /\.(mp4|mov|webm)$/i.test(result.data.output_url);

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
          TTS voiceover
        </span>
        <Link
          href="/create"
          className="font-mono text-[10px] tracking-[0.18em] text-ink-muted hover:text-ink uppercase transition-colors"
        >
          ← create
        </Link>
      </div>

      {/* Script source: write it, or generate from a summary */}
      <section className="border border-ink bg-paper p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
          Script
        </p>

        <div className="flex border border-ink font-mono text-[10px] tracking-[0.18em] uppercase">
          {(["write", "summary"] as Mode[]).map((m, i) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`flex-1 h-8 ${i > 0 ? "border-l border-ink" : ""} ${
                mode === m
                  ? "bg-ink text-paper"
                  : "bg-paper text-ink hover:bg-paper-2"
              } transition-colors`}
            >
              {m === "write" ? "write script" : "from summary"}
            </button>
          ))}
        </div>

        {mode === "summary" && (
          <form onSubmit={onGenerateScript} className="space-y-3">
            <textarea
              rows={3}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="A basic summary of what the voiceover should say…"
              className="w-full border border-ink bg-paper-2 p-2 font-mono text-[12px] text-ink focus:outline-none focus:border-ink"
            />
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
                <span>Length</span>
                <input
                  type="number"
                  min={5}
                  max={180}
                  value={targetSeconds}
                  onChange={(e) =>
                    setTargetSeconds(parseInt(e.target.value, 10) || 30)
                  }
                  className="w-16 border border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                />
                <span className="text-ink-muted">sec</span>
              </label>
              <button
                type="submit"
                disabled={genScript.isPending || !summary.trim()}
                className="ml-auto border border-ink px-3 py-1 font-mono text-[11px] tracking-[0.18em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
              >
                {genScript.isPending ? "writing…" : "generate script"}
              </button>
            </div>
          </form>
        )}

        {/* Editable script — prefilled when generated from a summary */}
        <textarea
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            mode === "summary"
              ? "The generated script will appear here — edit freely before synthesizing."
              : "Narration text…"
          }
          className="w-full border border-ink bg-paper-2 p-2 font-mono text-[12px] text-ink focus:outline-none focus:border-ink"
        />
      </section>

      {/* Output destination */}
      <section className="border border-ink bg-paper p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
          Output
        </p>

        <div className="flex border border-ink font-mono text-[10px] tracking-[0.18em] uppercase">
          {(["audio", "local_video", "youtube"] as OutputMode[]).map((m, i) => (
            <button
              key={m}
              type="button"
              onClick={() => setOutputMode(m)}
              className={`flex-1 h-8 px-2 ${i > 0 ? "border-l border-ink" : ""} ${
                outputMode === m
                  ? "bg-ink text-paper"
                  : "bg-paper text-ink hover:bg-paper-2"
              } transition-colors`}
            >
              {OUTPUT_LABELS[m]}
            </button>
          ))}
        </div>

        {outputMode === "local_video" && (
          <div className="space-y-2">
            <label className="block">
              <span className="sr-only">Choose a video</span>
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                onChange={onPickVideo}
                className="block w-full font-mono text-[11px] text-ink file:mr-3 file:border file:border-ink file:bg-paper file:px-3 file:py-1 file:font-mono file:text-[10px] file:uppercase file:tracking-[0.18em] file:text-ink hover:file:bg-paper-2"
              />
            </label>
            {upload.isPending && (
              <p className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-muted">
                uploading {videoName}…
              </p>
            )}
            {videoUploadId && (
              <p className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-soft">
                ✓ {videoName}
              </p>
            )}
            <p className="font-mono text-[10px] text-ink-muted">
              The video&apos;s own audio is dropped; it is trimmed/looped to the
              narration length.
            </p>
          </div>
        )}

        {outputMode === "youtube" && (
          <div className="space-y-2">
            <input
              type="text"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=…"
              className="w-full border border-ink bg-paper-2 p-2 font-mono text-[12px] text-ink focus:outline-none focus:border-ink"
            />
            {videoUrl.trim() && !isValidYouTubeUrl(videoUrl.trim()) && (
              <p className="font-mono text-[10px] text-[var(--color-mark)]">
                Enter a valid YouTube URL.
              </p>
            )}
            <p className="font-mono text-[10px] text-ink-muted">
              The video is downloaded server-side; its audio is replaced by the
              narration and it is trimmed/looped to the narration length.
            </p>
          </div>
        )}
      </section>

      {/* Synthesize */}
      <section className="border border-ink bg-paper p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
          Synthesize
        </p>
        <form onSubmit={onGenerateAudio} className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span>Preset</span>
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value as VoicePreset)}
              className="border border-ink bg-paper px-2 py-1 font-mono text-[11px]"
            >
              {VOICE_PRESETS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={!canSubmit}
            className="ml-auto border border-ink px-3 py-1 font-mono text-[11px] tracking-[0.18em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
          >
            {submit.isPending
              ? "submitting…"
              : outputMode === "audio"
                ? "generate audio"
                : "generate video"}
          </button>
        </form>

        {/* Result */}
        {editJobId && (
          <div className="space-y-2 pt-1">
            <p className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-muted">
              {result.data?.status ?? "queued"} · {editJobId.slice(0, 8)}
            </p>
            {result.data?.error && (
              <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap">
                {result.data.error}
              </p>
            )}
            {resultUrl && isVideoResult && (
              <video
                controls
                src={resultUrl}
                className="w-full max-h-[420px] bg-ink"
              />
            )}
            {resultUrl && !isVideoResult && (
              <div className="space-y-2">
                <audio controls src={resultUrl} className="w-full" />
                <a
                  href={resultUrl}
                  download
                  className="inline-block border border-ink px-3 py-1 font-mono text-[10px] tracking-[0.18em] uppercase text-ink hover:bg-paper-2 transition-colors"
                >
                  download audio ↓
                </a>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export default function CreateTtsPage() {
  return (
    <Suspense fallback={null}>
      <CreateTtsForm />
    </Suspense>
  );
}
