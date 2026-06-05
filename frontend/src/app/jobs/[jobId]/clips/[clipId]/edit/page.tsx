"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useJob } from "@/hooks/useJob";
import {
  useEditJobsForClip,
  useSubmitMusicEdit,
  useSubmitSplitScreenEdit,
  useSubmitTtsEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { API_HOST_URL } from "@/lib/constants";
import { pathToStaticUrl } from "@/lib/utils";
import {
  AUDIO_THEMES,
  type AudioTheme,
  type EditJob,
  type SplitScreenAudioMode,
  type VoicePreset,
} from "@/types/api";

interface Props {
  // Next.js 16: dynamic route params are a Promise that must be unwrapped.
  params: Promise<{ jobId: string; clipId: string }>;
}

const VOICE_PRESETS: VoicePreset[] = ["default", "finance", "finance_energetic"];

export default function ClipEditPage({ params }: Props) {
  const { jobId, clipId } = use(params);

  const { data: job } = useJob(jobId);
  const clip = useMemo(
    () => job?.clips?.find((c) => c.clip_id === clipId) ?? null,
    [job, clipId],
  );

  const editJobs = useEditJobsForClip(jobId, clipId);

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <Link href="/" className="hover:text-ink transition-colors">
          ← workspace
        </Link>
        <span aria-hidden className="text-ink-soft">/</span>
        <Link href={`/jobs/${jobId}`} className="hover:text-ink transition-colors">
          job · {jobId.slice(0, 8)}
        </Link>
        <span aria-hidden className="text-ink-soft">/</span>
        <span>clip · {clipId.slice(0, 12)}</span>
        <span aria-hidden className="text-ink-soft">/</span>
        <span className="text-ink">edit</span>
      </div>

      {/* Source clip preview */}
      <section className="border border-ink bg-paper p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
          Source clip
        </p>
        {clip ? (
          <div className="flex flex-col gap-2">
            <p className="text-[13px] text-ink">{clip.title ?? clip.clip_id}</p>
            {(() => {
              const url = pathToStaticUrl(clip.path);
              return url ? (
                <video
                  controls
                  preload="metadata"
                  playsInline
                  src={url}
                  className="max-h-[400px] aspect-[9/16] bg-black"
                />
              ) : (
                <p className="font-mono text-[11px] text-ink-muted">No file path available.</p>
              );
            })()}
          </div>
        ) : (
          <p className="font-mono text-[11px] text-ink-muted">Clip not found in job.</p>
        )}
      </section>

      {/* TTS section (Phase 1) */}
      <TtsSection jobId={jobId} clipId={clipId} hasClip={!!clip?.path} />

      {/* Phase 2 — Background music */}
      <MusicSection jobId={jobId} clipId={clipId} hasClip={!!clip?.path} />
      {/* Phase 3 — Split-screen */}
      <SplitScreenSection jobId={jobId} clipId={clipId} hasClip={!!clip?.path} />

      {/* Edit history */}
      <section className="border border-ink bg-paper p-4 space-y-3">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
          Edit history
        </p>
        {editJobs.data && editJobs.data.edit_jobs.length > 0 ? (
          <ul className="space-y-2">
            {editJobs.data.edit_jobs.map((j) => (
              <EditJobRow key={j.edit_job_id} job={j} />
            ))}
          </ul>
        ) : (
          <p className="font-mono text-[11px] text-ink-muted">
            No edits on this clip yet.
          </p>
        )}
      </section>
    </div>
  );
}

// ─── TTS form ────────────────────────────────────────────────────────────────

function TtsSection({
  jobId,
  clipId,
  hasClip,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
}) {
  const [text, setText] = useState("");
  const [preset, setPreset] = useState<VoicePreset>("default");
  const [attach, setAttach] = useState(true);
  const submit = useSubmitTtsEdit();

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    submit.mutate({
      text,
      voice_preset: preset,
      parent_job_id: jobId,
      attach_to_clip_id: attach && hasClip ? clipId : undefined,
    });
  };

  return (
    <section className="border border-ink bg-paper p-4 space-y-3">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
        Generate TTS (Chatterbox)
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Narration text…"
          className="w-full border border-ink bg-paper-2 p-2 font-mono text-[12px] text-ink focus:outline-none focus:border-ink"
        />
        <div className="flex flex-wrap items-center gap-4">
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
          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <input
              type="checkbox"
              checked={attach}
              disabled={!hasClip}
              onChange={(e) => setAttach(e.target.checked)}
            />
            <span>Attach as intro to this clip</span>
          </label>
          <button
            type="submit"
            disabled={submit.isPending || !text.trim()}
            className="ml-auto border border-ink px-3 py-1 font-mono text-[11px] tracking-[0.18em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
          >
            {submit.isPending ? "submitting…" : "generate"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ─── Music section ───────────────────────────────────────────────────────────

function MusicSection({
  jobId,
  clipId,
  hasClip,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
}) {
  type SourceMode = "theme" | "upload" | "path";
  const [mode, setMode] = useState<SourceMode>("theme");
  const [theme, setTheme] = useState<AudioTheme>("professional");
  const [musicPath, setMusicPath] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [volumeDb, setVolumeDb] = useState(-18);
  const submit = useSubmitMusicEdit();
  const upload = useUploadAsset();

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setUploadFile(f);
    setUploadedId(null);
    if (f) {
      const r = await upload.mutateAsync(f);
      setUploadedId(r.upload_id);
    }
  };

  const canSubmit =
    hasClip &&
    !submit.isPending &&
    ((mode === "theme" && !!theme) ||
      (mode === "upload" && !!uploadedId) ||
      (mode === "path" && !!musicPath.trim()));

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate({
      parent_job_id: jobId,
      clip_id: clipId,
      volume_db: volumeDb,
      ...(mode === "theme" ? { theme } : {}),
      ...(mode === "upload" && uploadedId ? { music_upload_id: uploadedId } : {}),
      ...(mode === "path" ? { music_path: musicPath } : {}),
    });
  };

  return (
    <section className="border border-ink bg-paper p-4 space-y-3">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
        Add background music
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        {/* Source mode tabs */}
        <div className="flex border border-ink font-mono text-[10px] tracking-[0.18em] uppercase">
          {(["theme", "upload", "path"] as SourceMode[]).map((m, i) => (
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
              {m === "path" ? "server path" : m}
            </button>
          ))}
        </div>

        {/* Mode-specific input */}
        {mode === "theme" && (
          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span>Theme</span>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as AudioTheme)}
              className="border border-ink bg-paper px-2 py-1 font-mono text-[11px]"
            >
              {AUDIO_THEMES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
        )}
        {mode === "upload" && (
          <div className="flex items-center gap-3 font-mono text-[11px] text-ink">
            <input
              type="file"
              accept="audio/*"
              onChange={onUpload}
              className="font-mono text-[11px]"
            />
            {upload.isPending && <span className="text-ink-muted">uploading…</span>}
            {uploadedId && (
              <span className="text-ink-soft truncate max-w-[12rem]">
                ✓ {uploadFile?.name}
              </span>
            )}
          </div>
        )}
        {mode === "path" && (
          <input
            type="text"
            value={musicPath}
            onChange={(e) => setMusicPath(e.target.value)}
            placeholder="e.g. assets/audio_cache/professional/track.mp3"
            className="w-full border border-ink bg-paper-2 p-2 font-mono text-[11px] text-ink"
          />
        )}

        {/* Volume slider */}
        <label className="flex items-center gap-3 font-mono text-[11px] text-ink">
          <span>Volume</span>
          <input
            type="range"
            min={-40}
            max={6}
            step={1}
            value={volumeDb}
            onChange={(e) => setVolumeDb(parseInt(e.target.value, 10))}
            className="flex-1 max-w-[18rem]"
          />
          <span className="num-tabular text-ink-muted w-12 text-right">
            {volumeDb} dB
          </span>
        </label>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!canSubmit}
            className="border border-ink px-3 py-1 font-mono text-[11px] tracking-[0.18em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
          >
            {submit.isPending ? "submitting…" : "add music"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ─── Split-screen section ────────────────────────────────────────────────────

function SplitScreenSection({
  jobId,
  clipId,
  hasClip,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
}) {
  type BgMode = "default" | "upload" | "url";
  const [mode, setMode] = useState<BgMode>("default");
  const [bgUrl, setBgUrl] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [audioMode, setAudioMode] =
    useState<SplitScreenAudioMode>("fetched_video");
  const submit = useSubmitSplitScreenEdit();
  const upload = useUploadAsset();

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setUploadFile(f);
    setUploadedId(null);
    if (f) {
      const r = await upload.mutateAsync(f);
      setUploadedId(r.upload_id);
    }
  };

  const canSubmit =
    hasClip &&
    !submit.isPending &&
    ((mode === "default") ||
      (mode === "upload" && !!uploadedId) ||
      (mode === "url" && /^https?:\/\//.test(bgUrl.trim())));

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate({
      parent_job_id: jobId,
      clip_id: clipId,
      audio_mode: audioMode,
      ...(mode === "default" ? { background_default: true } : {}),
      ...(mode === "upload" && uploadedId ? { background_upload_id: uploadedId } : {}),
      ...(mode === "url" ? { background_url: bgUrl.trim() } : {}),
    });
  };

  return (
    <section className="border border-ink bg-paper p-4 space-y-3">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
        Convert to split-screen
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        {/* Background source tabs */}
        <div className="flex border border-ink font-mono text-[10px] tracking-[0.18em] uppercase">
          {(["default", "upload", "url"] as BgMode[]).map((m, i) => (
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
              {m === "url" ? "youtube url" : m}
            </button>
          ))}
        </div>

        {/* Mode-specific input */}
        {mode === "default" && (
          <p className="font-mono text-[11px] text-ink-muted">
            Uses the server's <code>BACKGROUND_VIDEO_PATH</code> env (e.g. a
            Minecraft / GTA parkour loop).
          </p>
        )}
        {mode === "upload" && (
          <div className="flex items-center gap-3 font-mono text-[11px] text-ink">
            <input
              type="file"
              accept="video/*"
              onChange={onUpload}
              className="font-mono text-[11px]"
            />
            {upload.isPending && <span className="text-ink-muted">uploading…</span>}
            {uploadedId && (
              <span className="text-ink-soft truncate max-w-[12rem]">
                ✓ {uploadFile?.name}
              </span>
            )}
          </div>
        )}
        {mode === "url" && (
          <input
            type="url"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
            className="w-full border border-ink bg-paper-2 p-2 font-mono text-[11px] text-ink"
          />
        )}

        {/* Audio source radio */}
        <fieldset className="flex flex-wrap items-center gap-4 font-mono text-[11px] text-ink">
          <legend className="text-ink-soft">Audio</legend>
          {(
            [
              ["fetched_video", "source clip"],
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
      </form>
    </section>
  );
}

// ─── Edit history row ────────────────────────────────────────────────────────

function EditJobRow({ job }: { job: EditJob }) {
  const url = job.output_url ? `${API_HOST_URL}${job.output_url}` : null;
  const isVideo = !!url && /\.(mp4|webm|mov)$/i.test(url);
  const isAudio = !!url && /\.(mp3|wav|m4a|ogg)$/i.test(url);

  return (
    <li className="border border-rule-soft bg-paper-2 p-3 space-y-2">
      <div className="flex items-center gap-3 font-mono text-[10px] tracking-[0.12em] uppercase">
        <span className="text-ink">{job.operation}</span>
        <span aria-hidden className="text-ink-soft">·</span>
        <span className="text-ink-muted">{job.edit_job_id.slice(0, 8)}</span>
        <span aria-hidden className="text-ink-soft">·</span>
        <span className={statusColor(job.status)}>{job.status}</span>
      </div>
      {job.error && (
        <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap">
          {job.error}
        </p>
      )}
      {url && isVideo && (
        <video controls src={url} className="max-h-[300px] aspect-[9/16] bg-black" />
      )}
      {url && isAudio && (
        <audio controls src={url} className="w-full" />
      )}
    </li>
  );
}

function statusColor(s: string): string {
  switch (s) {
    case "done":
      return "text-ink";
    case "failed":
      return "text-[var(--color-mark)]";
    case "running":
    case "queued":
      return "text-ink-muted";
    default:
      return "text-ink-muted";
  }
}

