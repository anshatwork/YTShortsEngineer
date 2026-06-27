"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  useEditJob,
  useGenerateTtsScript,
  useSubmitTtsEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { Reveal } from "@/components/landing/Reveal";
import { API_HOST_URL } from "@/lib/constants";
import { isValidYouTubeUrl, cn } from "@/lib/utils";
import type { TTSEditRequest, VoicePreset } from "@/types/api";

const VOICE_PRESETS: VoicePreset[] = ["default", "finance", "finance_energetic"];

const VOICE_PRESET_LABELS: Record<VoicePreset, string> = {
  default: "Neutral",
  finance: "Finance",
  finance_energetic: "Energetic",
};

type Mode = "write" | "summary";
type OutputMode = "audio" | "local_video" | "youtube";

const OUTPUT_LABELS: Record<OutputMode, string> = {
  audio: "Save audio",
  local_video: "Behind local video",
  youtube: "Behind YouTube",
};

const EXAMPLE_SCRIPTS = [
  {
    label: "Tech insight",
    duration: "~15s",
    text: "Most developers ship features. The ones who advance ship understanding. That gap is wider than you think — and it's entirely learnable in six months of deliberate practice.",
  },
  {
    label: "Finance hook",
    duration: "~20s",
    text: "The rule nobody teaches about compound interest: it works exactly the same way for debt. If you're carrying a balance you're funding someone else's wealth at the same rate.",
  },
  {
    label: "Productivity",
    duration: "~18s",
    text: "Your calendar is lying to you. You don't have eight hours of work — you have two good hours surrounded by six hours of maintenance. Schedule accordingly.",
  },
];

function CreateTtsForm() {
  const searchParams = useSearchParams();
  const prefillUrl = searchParams.get("youtube_url") ?? "";

  const [mode, setMode] = useState<Mode>("write");

  const [summary, setSummary] = useState("");
  const [targetSeconds, setTargetSeconds] = useState(30);
  const genScript = useGenerateTtsScript();

  const [text, setText] = useState("");
  const [preset, setPreset] = useState<VoicePreset>("default");

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
    const r = await genScript.mutateAsync({ summary, target_seconds: targetSeconds });
    setText(r.script);
  };

  const onPickVideo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setVideoName(file.name);
    setVideoUploadId(null);
    upload.mutate(file, { onSuccess: (r) => setVideoUploadId(r.upload_id) });
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
    if (outputMode === "local_video" && videoUploadId) body.video_upload_id = videoUploadId;
    else if (outputMode === "youtube") body.video_url = videoUrl.trim();
    submit.mutate(body, { onSuccess: (job) => setEditJobId(job.edit_job_id) });
  };

  const done = result.data?.status === "done" && result.data.output_url;
  const resultUrl = done ? `${API_HOST_URL}${result.data!.output_url}` : null;
  const isVideoResult =
    !!result.data?.output_url && /\.(mp4|mov|webm)$/i.test(result.data.output_url);

  return (
    <div className="max-w-2xl mt-8 divide-y divide-rule-soft">

      {/* ── Script ─────────────────────────────────────────────────── */}
      <fieldset className="space-y-4 pt-6 pb-7">
        <legend className="kicker mb-3">Script</legend>

        {/* Mode toggle */}
        <div className="flex border border-ink h-9">
          {(["write", "summary"] as Mode[]).map((m, i) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cn(
                "flex-1 font-mono text-[11px] tracking-[0.18em] uppercase transition-colors",
                i > 0 && "border-l border-ink",
                mode === m ? "bg-ink text-paper" : "bg-paper text-ink-soft hover:text-ink",
              )}
            >
              {m === "write" ? "Write script" : "From summary"}
            </button>
          ))}
        </div>

        {/* Example script chips (write mode only) */}
        {mode === "write" && (
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_SCRIPTS.map((ex) => (
              <button
                key={ex.label}
                type="button"
                onClick={() => setText(ex.text)}
                className={cn(
                  "flex items-center gap-2 h-8 px-3 border border-ink font-mono text-[10px] tracking-[0.12em] uppercase transition-colors",
                  text === ex.text
                    ? "bg-ink text-paper"
                    : "bg-paper text-ink-soft hover:text-ink",
                )}
              >
                {ex.label}
                <span
                  className={cn(
                    "font-mono text-[9px]",
                    text === ex.text ? "text-paper/60" : "text-ink-muted",
                  )}
                >
                  {ex.duration}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Summary → generate script form */}
        {mode === "summary" && (
          <form onSubmit={onGenerateScript} className="space-y-3">
            <textarea
              rows={3}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="A basic summary of what the voiceover should say…"
              className="w-full bg-paper border border-ink px-3 py-2 font-mono text-[13px] text-ink placeholder:text-ink-soft outline-none resize-none"
            />
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
                <span>Length</span>
                <input
                  type="number"
                  min={5}
                  max={180}
                  value={targetSeconds}
                  onChange={(e) => setTargetSeconds(parseInt(e.target.value, 10) || 30)}
                  className="w-16 border border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                />
                <span className="text-ink-muted">sec</span>
              </label>
              <button
                type="submit"
                disabled={genScript.isPending || !summary.trim()}
                className="group ml-auto h-9 px-4 font-mono text-[11px] tracking-[0.18em] uppercase border border-ink bg-ink text-paper hover:bg-ink-muted transition-colors disabled:opacity-40 flex items-center gap-2"
              >
                {genScript.isPending ? (
                  <>
                    <span className="w-3 h-3 rounded-full border border-paper border-t-transparent animate-spin" />
                    Writing
                  </>
                ) : (
                  <>
                    Generate script
                    <span className="transition-transform duration-200 group-hover:translate-x-0.5">→</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* Script textarea */}
        <textarea
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            mode === "summary"
              ? "Generated script will appear here — edit freely before synthesizing."
              : "Narration text…"
          }
          className="w-full bg-paper border border-ink px-3 py-2 font-mono text-[13px] text-ink placeholder:text-ink-soft outline-none resize-none"
        />
      </fieldset>

      {/* ── Output ─────────────────────────────────────────────────── */}
      <fieldset className="space-y-4 pt-6 pb-7">
        <legend className="kicker mb-3">Output</legend>

        <div className="flex border border-ink h-9">
          {(["audio", "local_video", "youtube"] as OutputMode[]).map((m, i) => (
            <button
              key={m}
              type="button"
              onClick={() => setOutputMode(m)}
              className={cn(
                "flex-1 px-2 font-mono text-[11px] tracking-[0.15em] uppercase transition-colors",
                i > 0 && "border-l border-ink",
                outputMode === m ? "bg-ink text-paper" : "bg-paper text-ink-soft hover:text-ink",
              )}
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
                Uploading {videoName}…
              </p>
            )}
            {videoUploadId && (
              <p className="font-mono text-[10px] tracking-[0.12em] uppercase text-ink-soft">
                ✓ {videoName}
              </p>
            )}
            <p className="font-mono text-[10px] text-ink-muted leading-relaxed">
              The video&apos;s own audio is dropped; it is trimmed or looped to the narration length.
            </p>
          </div>
        )}

        {outputMode === "youtube" && (
          <div className="space-y-2">
            <div className="flex items-center border border-ink bg-paper h-11 px-3">
              <span className="font-mono text-ink-soft text-[13px] pr-2">https://</span>
              <input
                type="text"
                value={videoUrl.replace(/^https?:\/\//, "")}
                onChange={(e) => {
                  const raw = e.target.value;
                  setVideoUrl(raw.startsWith("http") ? raw : `https://${raw}`);
                }}
                placeholder="www.youtube.com/watch?v=…"
                className="flex-1 bg-transparent border-0 outline-none font-mono text-[13px] text-ink placeholder:text-ink-soft"
              />
            </div>
            {videoUrl.trim() && !isValidYouTubeUrl(videoUrl.trim()) && (
              <p className="font-mono text-[10px] text-[var(--color-mark)]">
                Enter a valid YouTube URL.
              </p>
            )}
            <p className="font-mono text-[10px] text-ink-muted leading-relaxed">
              The video is downloaded server-side; its audio is replaced by the narration and
              trimmed or looped to the narration length.
            </p>
          </div>
        )}
      </fieldset>

      {/* ── Synthesize ─────────────────────────────────────────────── */}
      <fieldset className="space-y-4 pt-6 pb-7">
        <legend className="kicker mb-3">Synthesize</legend>

        {/* Voice preset segmented */}
        <div>
          <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted mb-2">
            Voice preset
          </p>
          <div className="flex border border-ink h-9 max-w-xs">
            {VOICE_PRESETS.map((p, i) => (
              <button
                key={p}
                type="button"
                onClick={() => setPreset(p)}
                className={cn(
                  "flex-1 font-mono text-[11px] tracking-[0.12em] uppercase transition-colors",
                  i > 0 && "border-l border-ink",
                  preset === p ? "bg-ink text-paper" : "bg-paper text-ink-soft hover:text-ink",
                )}
              >
                {VOICE_PRESET_LABELS[p]}
              </button>
            ))}
          </div>
        </div>

        {/* Submit */}
        <form onSubmit={onGenerateAudio}>
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
                Submitting
              </>
            ) : (
              <>
                {outputMode === "audio" ? "Generate audio" : "Generate video"}
                <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
              </>
            )}
          </button>
        </form>
      </fieldset>

      {/* ── Result ─────────────────────────────────────────────────── */}
      {editJobId && (
        <div className="pt-6 pb-4">
          <div className="flex items-center gap-3 mb-4">
            <p className="kicker">{result.data?.status ?? "queued"}</p>
            <span className="font-mono text-[10px] tracking-[0.12em] text-ink-muted num-tabular">
              {editJobId.slice(0, 8)}
            </span>
            {!result.data || result.data.status === "running" || result.data.status === "queued" ? (
              <span className="inline-block w-[6px] h-[6px] rounded-full bg-ink ink-pulse" />
            ) : null}
          </div>

          {result.data?.error && (
            <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap mb-3">
              {result.data.error}
            </p>
          )}

          {resultUrl && isVideoResult && (
            <video
              controls
              src={resultUrl}
              className="w-full max-h-[420px] bg-ink border border-ink"
            />
          )}

          {resultUrl && !isVideoResult && (
            <div className="space-y-2 border border-ink p-4">
              <audio controls src={resultUrl} className="w-full" />
              <a
                href={resultUrl}
                download
                className="inline-flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink hover:text-ink-muted transition-colors"
              >
                Download audio ↓
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function CreateTtsPage() {
  return (
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-center py-2.5">
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Narration Booth
        </span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Headline */}
      <Reveal>
        <div className="pt-8 pb-8 border-b border-rule-soft">
          <p className="kicker mb-3">voice synthesis</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
            Synthesise a{" "}
            <span className="display-italic text-[var(--color-mark)]">voice</span>.
          </h1>
          <p className="mt-4 font-mono text-[12px] text-ink-muted max-w-md leading-relaxed">
            Write a script or generate one from a summary. Pick a voice preset, then render audio or lay it behind a video.
          </p>
        </div>
      </Reveal>

      {/* Form — inside Suspense because CreateTtsForm uses useSearchParams */}
      <Suspense fallback={null}>
        <CreateTtsForm />
      </Suspense>
    </div>
  );
}
