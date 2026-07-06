"use client";

import { use, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useJob } from "@/hooks/useJob";
import {
  useEditJobsForClip,
  useGenerateTtsScript,
  useSubmitMusicEdit,
  useSubmitSplitScreenEdit,
  useSubmitThumbnailEdit,
  useSubmitTtsEdit,
  useUploadAsset,
} from "@/hooks/useEditJob";
import { useMusicTracks } from "@/hooks/useMusicLibrary";
import { useEditCompletionToasts } from "@/hooks/useEditCompletionToasts";
import { Reveal } from "@/components/landing/Reveal";
import { Masthead } from "@/components/ui/Masthead";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { TextArea, TextInput, fieldClass } from "@/components/ui/Field";
import { API_HOST_URL } from "@/lib/constants";
import { cn, pathToStaticUrl } from "@/lib/utils";
import {
  AUDIO_THEMES,
  type AudioTheme,
  type EditJob,
  type EditOperation,
  type SplitScreenAudioMode,
  type ThumbnailFont,
  type ThumbnailStyle,
  type VoicePreset,
} from "@/types/api";

interface Props {
  params: Promise<{ jobId: string; clipId: string }>;
}

const VOICE_PRESETS: VoicePreset[] = ["default", "finance", "finance_energetic"];
const VOICE_PRESET_LABELS: Record<VoicePreset, string> = {
  default: "Neutral",
  finance: "Finance",
  finance_energetic: "Energetic",
};

const EDIT_OP_LABELS: Record<EditOperation, string> = {
  tts: "voiceover",
  music: "music",
  split_screen: "split-screen",
  thumbnail: "thumbnail",
};

/**
 * Render a media URL as video / audio / image. `kind="video"` forces a video
 * player (used for the source clip, which has no extension hint); otherwise the
 * player is chosen from the URL extension (same logic as the edit-history row).
 */
function MediaPreview({
  url,
  kind,
}: {
  url: string | null;
  kind?: "video" | "audio" | "image";
}) {
  if (!url) {
    return (
      <p className="font-mono text-[11px] text-ink-muted">No file available.</p>
    );
  }
  const isVideo = kind === "video" || /\.(mp4|webm|mov)$/i.test(url);
  const isAudio = kind === "audio" || /\.(mp3|wav|m4a|ogg)$/i.test(url);
  const isImage = kind === "image" || /\.(jpg|jpeg|png|webp)$/i.test(url);

  if (isVideo) {
    return (
      <video
        controls
        preload="metadata"
        playsInline
        src={url}
        className="w-full max-h-[400px] aspect-[9/16] bg-black object-contain border border-rule-soft"
      />
    );
  }
  if (isAudio) {
    return <audio controls src={url} className="w-full" />;
  }
  if (isImage) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt="Edited output"
        className="w-full max-h-[400px] aspect-[9/16] object-contain bg-black border border-rule-soft"
      />
    );
  }
  return (
    <p className="font-mono text-[11px] text-ink-muted">Unsupported media.</p>
  );
}

export default function ClipEditPage({ params }: Props) {
  const { jobId, clipId } = use(params);

  const { data: job, isLoading: jobLoading } = useJob(jobId);
  const clip = useMemo(
    () => job?.clips?.find((c) => c.clip_id === clipId) ?? null,
    [job, clipId],
  );

  const editJobs = useEditJobsForClip(jobId, clipId);

  // Toast when any edit on this clip finishes (success or failure).
  useEditCompletionToasts(editJobs.data?.edit_jobs);

  // Latest completed edit (list is newest-first) — drives the Before/After view.
  const latestEdit = editJobs.data?.edit_jobs.find(
    (j) => j.status === "done" && j.output_url,
  );
  const sourceUrl = clip ? pathToStaticUrl(clip.path) : null;
  const editedUrl = latestEdit ? `${API_HOST_URL}${latestEdit.output_url}` : null;

  return (
    <div className="-mt-2 space-y-6">
      {/* Masthead */}
      <Masthead
        left={
          <>
            <Link href="/workspace" className="hover:text-ink transition-colors">
              workspace
            </Link>
            <span aria-hidden>/</span>
            <Link
              href={`/jobs/${jobId}`}
              className="hover:text-ink transition-colors"
            >
              job · {jobId.slice(0, 8)}
            </Link>
          </>
        }
        title="The Edit Suite"
        right={<span>clip · {clipId.slice(0, 8)}</span>}
      />

      {/* Clip headline */}
      <Reveal>
        <div className="pb-6 border-b border-rule-soft">
          <p className="kicker mb-3">editing clip</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(1.5rem,3.5vw,2.5rem)]">
            {clip?.title ?? (
              <span className="font-mono text-[1.3rem] text-ink-muted">
                {clipId.slice(0, 16)}…
              </span>
            )}
          </h1>
        </div>
      </Reveal>

      {/* Source clip preview */}
      <Panel label="Source material">
        {clip ? (
          (() => {
            const url = pathToStaticUrl(clip.path);
            return url ? (
              <video
                controls
                preload="metadata"
                playsInline
                src={url}
                className="max-h-[400px] aspect-[9/16] bg-black border border-rule-soft"
              />
            ) : (
              <p className="font-mono text-[11px] text-ink-muted">
                No file path available.
              </p>
            );
          })()
        ) : jobLoading ? (
          <LoadingCanvas label="Loading clip" />
        ) : (
          <p className="font-mono text-[11px] text-ink-muted">
            Clip not found in job.
          </p>
        )}
      </Panel>

      {/* Before / After — latest completed edit vs. the source clip */}
      <Panel
        label="Before / After"
        right={
          latestEdit && (
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted">
              {EDIT_OP_LABELS[latestEdit.operation] ?? latestEdit.operation}
            </span>
          )
        }
      >
        {editedUrl ? (
            <div className="grid gap-5 md:grid-cols-2">
              <div className="space-y-2">
                <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-soft">
                  ○ Before — source
                </p>
                <MediaPreview url={sourceUrl} kind="video" />
              </div>
              <div className="space-y-2">
                <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink">
                  ◆ After — edited
                </p>
                <MediaPreview url={editedUrl} />
              </div>
            </div>
          ) : (
            <p className="font-mono text-[11px] text-ink-muted">
              No completed edits yet. Apply an edit below — the result appears
              here next to the original.
            </p>
          )}
      </Panel>

      {/* Tool sections — cascade in on load */}
      <Reveal delay={0.04}>
        <TtsSection
          jobId={jobId}
          clipId={clipId}
          hasClip={!!clip?.path}
          clipDurationSec={
            clip ? clip.timestamp_range[1] - clip.timestamp_range[0] : undefined
          }
        />
      </Reveal>

      <Reveal delay={0.08}>
        <MusicSection
          jobId={jobId}
          clipId={clipId}
          hasClip={!!clip?.path}
          clipDurationSec={
            clip ? clip.timestamp_range[1] - clip.timestamp_range[0] : undefined
          }
        />
      </Reveal>

      <Reveal delay={0.12}>
        <SplitScreenSection jobId={jobId} clipId={clipId} hasClip={!!clip?.path} />
      </Reveal>

      <Reveal delay={0.16}>
        <ThumbnailSection jobId={jobId} clipId={clipId} hasClip={!!clip?.path} />
      </Reveal>

      {/* Edit history */}
      <Reveal delay={0.2}>
        <Panel label="Edit history">
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
        </Panel>
      </Reveal>
    </div>
  );
}

// ─── TTS form ────────────────────────────────────────────────────────────────

function TtsSection({
  jobId,
  clipId,
  hasClip,
  clipDurationSec,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
  clipDurationSec?: number;
}) {
  const [text, setText] = useState("");
  const [preset, setPreset] = useState<VoicePreset>("default");
  const [attach, setAttach] = useState(true);
  const submit = useSubmitTtsEdit();

  // "Write with AI" — reuses the generate_tts_script endpoint. Target length
  // defaults to the clip's duration so the narration fits the clip.
  const [showWriter, setShowWriter] = useState(false);
  const [summary, setSummary] = useState("");
  const [targetSeconds, setTargetSeconds] = useState(
    clipDurationSec ? Math.round(clipDurationSec) : 30,
  );
  const genScript = useGenerateTtsScript();

  // ~150 wpm / 2.5 words per sec — matches the word budget used server-side
  // in edit_runner.py's generate_tts_script().
  const estimatedSec = useMemo(() => {
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    return words / 2.5;
  }, [text]);

  const onGenerateScript = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;
    const r = await genScript.mutateAsync({
      summary,
      target_seconds: targetSeconds,
    });
    setText(r.script);
  };

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
    <Panel label="Voice synthesis" bodyClassName="space-y-4">
        {/* Write with AI — LLM-generated narration from a short summary */}
        <div className="border border-rule-soft">
          <button
            type="button"
            onClick={() => setShowWriter((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-2 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted hover:text-ink transition-colors focus-ink"
            aria-expanded={showWriter}
          >
            <span>✎ Write with AI</span>
            <span aria-hidden>{showWriter ? "−" : "+"}</span>
          </button>
          {showWriter && (
            <form onSubmit={onGenerateScript} className="px-3 pb-3 space-y-3">
              <TextArea
                rows={3}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="A short summary of what the voiceover should say…"
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
                    className={cn(fieldClass, "w-16 px-2 py-1 text-[11px]")}
                  />
                  <span className="text-ink-muted">sec</span>
                </label>
                <Button
                  type="submit"
                  disabled={!summary.trim()}
                  pending={genScript.isPending}
                  pendingLabel="Writing"
                  withArrow
                  className="ml-auto"
                >
                  Generate script
                </Button>
              </div>
            </form>
          )}
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <TextArea
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Narration text…"
          />

          {text.trim() && (
            <p className="font-mono text-[11px] text-ink-muted">
              Est. speech length: ~{formatSeconds(estimatedSec)}
              {clipDurationSec != null && attach && hasClip && (
                <>
                  {" "}
                  / clip: {formatSeconds(clipDurationSec)}
                  {estimatedSec > clipDurationSec * 1.1 && (
                    <span className="text-ink"> — longer than the clip</span>
                  )}
                </>
              )}
            </p>
          )}

          {/* Voice preset segmented */}
          <div>
            <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted mb-2">
              Voice preset
            </p>
            <SegmentedControl
              className="max-w-xs"
              value={preset}
              onChange={setPreset}
              options={VOICE_PRESETS.map((p) => ({
                value: p,
                label: VOICE_PRESET_LABELS[p],
              }))}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
              <input
                type="checkbox"
                checked={attach}
                disabled={!hasClip}
                onChange={(e) => setAttach(e.target.checked)}
              />
              <span>Attach as intro to this clip</span>
            </label>
            <Button
              type="submit"
              disabled={!text.trim()}
              pending={submit.isPending}
              pendingLabel="Generating"
              withArrow
              className="ml-auto"
            >
              Generate
            </Button>
          </div>
        </form>
    </Panel>
  );
}

// ─── Music section ───────────────────────────────────────────────────────────

function MusicSection({
  jobId,
  clipId,
  hasClip,
  clipDurationSec,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
  clipDurationSec?: number;
}) {
  type SourceMode = "theme" | "library" | "upload" | "path";
  const [mode, setMode] = useState<SourceMode>("library");
  const [theme, setTheme] = useState<AudioTheme>("professional");
  const [libFilter, setLibFilter] = useState<AudioTheme | "songs">("songs");
  const [musicPath, setMusicPath] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [pickedPath, setPickedPath] = useState<string | null>(null);
  const [pickedDuration, setPickedDuration] = useState<number | null>(null);
  const [musicStartSec, setMusicStartSec] = useState(0);
  const [volumeDb, setVolumeDb] = useState(-18);
  const previewRef = useRef<HTMLAudioElement>(null);
  const submit = useSubmitMusicEdit();
  const upload = useUploadAsset();

  const tracks = useMusicTracks(libFilter);

  const maxStart =
    pickedDuration != null
      ? Math.max(0, Math.floor(pickedDuration - (clipDurationSec ?? 0)))
      : null;

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
      (mode === "library" && !!pickedPath) ||
      (mode === "upload" && !!uploadedId) ||
      (mode === "path" && !!musicPath.trim()));

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate({
      parent_job_id: jobId,
      clip_id: clipId,
      volume_db: volumeDb,
      music_start_sec: musicStartSec > 0 ? musicStartSec : undefined,
      ...(mode === "theme" ? { theme } : {}),
      ...(mode === "library" && pickedPath ? { music_path: pickedPath } : {}),
      ...(mode === "upload" && uploadedId ? { music_upload_id: uploadedId } : {}),
      ...(mode === "path" ? { music_path: musicPath } : {}),
    });
  };

  return (
    <Panel label="Background music" bodyClassName="space-y-4">
        <form onSubmit={onSubmit} className="space-y-4">
          {/* Source mode tabs */}
          <SegmentedControl
            value={mode}
            onChange={setMode}
            options={(["theme", "library", "upload", "path"] as SourceMode[]).map(
              (m) => ({
                value: m,
                label:
                  m === "path"
                    ? "Server path"
                    : m.charAt(0).toUpperCase() + m.slice(1),
              }),
            )}
          />

          {/* Mode-specific input */}
          {mode === "theme" && (
            <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
              <span>Theme</span>
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value as AudioTheme)}
                className={cn(fieldClass, "px-2 py-1 text-[11px]")}
              >
                {AUDIO_THEMES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
          )}

          {mode === "library" && (
            <div className="space-y-3">
              <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
                <span>From</span>
                <select
                  value={libFilter}
                  onChange={(e) => {
                    setLibFilter(e.target.value as AudioTheme | "songs");
                    setPickedPath(null);
                  }}
                  className={cn(fieldClass, "px-2 py-1 text-[11px]")}
                >
                  <option value="songs">songs (your library)</option>
                  {AUDIO_THEMES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </label>

              {tracks.isLoading ? (
                <p className="font-mono text-[11px] text-ink-muted">
                  Loading tracks…
                </p>
              ) : (tracks.data?.tracks.length ?? 0) === 0 ? (
                <p className="font-mono text-[11px] text-ink-muted">
                  {libFilter === "songs"
                    ? "No songs added yet. Search & add them on the Discover page (Songs)."
                    : "No cached tracks for this mood yet. Refresh on the Discover page (needs JAMENDO_CLIENT_ID)."}
                </p>
              ) : (
                <ul className="max-h-72 overflow-y-auto border border-rule-soft divide-y divide-rule-soft">
                  {tracks.data!.tracks.map((t) => {
                    const picked = pickedPath === t.path;
                    return (
                      <li
                        key={t.track_id}
                        className={cn(
                          "p-3 space-y-1.5 cursor-pointer transition-colors",
                          picked ? "bg-paper-2" : "hover:bg-paper-2",
                        )}
                        onClick={() => {
                          setPickedPath(t.path);
                          setPickedDuration(t.duration ?? null);
                          setMusicStartSec(0);
                        }}
                      >
                        <div className="flex items-center gap-2 font-mono text-[11px] text-ink">
                          <input
                            type="radio"
                            name="music-library-pick"
                            checked={picked}
                            onChange={() => {
                              setPickedPath(t.path);
                              setPickedDuration(t.duration ?? null);
                              setMusicStartSec(0);
                            }}
                          />
                          <span className="truncate flex-1">{t.title}</span>
                          {t.duration != null && (
                            <span className="num-tabular text-ink-muted">
                              {formatSeconds(t.duration)}
                            </span>
                          )}
                          <span className="text-ink-soft uppercase tracking-[0.12em]">
                            {t.source}
                          </span>
                        </div>
                        <audio
                          ref={picked ? previewRef : undefined}
                          controls
                          preload="none"
                          src={`${API_HOST_URL}${t.preview_url}`}
                          className="w-full h-8"
                          onClick={(e) => e.stopPropagation()}
                        />
                        {t.attribution && (
                          <p className="font-mono text-[9px] text-ink-soft truncate">
                            {t.attribution}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          {mode === "upload" && (
            <div className="flex items-center gap-3 font-mono text-[11px] text-ink">
              <input
                type="file"
                accept="audio/*"
                onChange={onUpload}
                className="font-mono text-[11px]"
              />
              {upload.isPending && (
                <span className="text-ink-muted">Uploading…</span>
              )}
              {uploadedId && (
                <span className="text-ink-soft truncate max-w-[12rem]">
                  ✓ {uploadFile?.name}
                </span>
              )}
            </div>
          )}

          {mode === "path" && (
            <TextInput
              type="text"
              value={musicPath}
              onChange={(e) => setMusicPath(e.target.value)}
              placeholder="e.g. assets/audio_cache/professional/track.mp3"
            />
          )}

          {/* Start-at */}
          {mode === "library" &&
            pickedPath &&
            pickedDuration != null &&
            maxStart != null &&
            (maxStart === 0 ? (
              <p className="font-mono text-[11px] text-ink-muted">
                Track ({formatSeconds(pickedDuration)}) is shorter than the clip
                {clipDurationSec ? ` (${formatSeconds(clipDurationSec)})` : ""}{" "}
                — it will loop from the start.
              </p>
            ) : (
              <div className="space-y-1.5">
                <label className="flex items-center gap-3 font-mono text-[11px] text-ink">
                  <span className="whitespace-nowrap">Start at</span>
                  <input
                    type="range"
                    min={0}
                    max={maxStart}
                    step={1}
                    value={Math.min(musicStartSec, maxStart)}
                    onChange={(e) =>
                      setMusicStartSec(parseInt(e.target.value, 10))
                    }
                    className="flex-1 max-w-[18rem]"
                  />
                  <span className="num-tabular text-ink-muted whitespace-nowrap">
                    {formatSeconds(musicStartSec)}
                    {clipDurationSec
                      ? `–${formatSeconds(musicStartSec + clipDurationSec)}`
                      : ""}{" "}
                    / {formatSeconds(pickedDuration)}
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => {
                    const t = Math.floor(
                      previewRef.current?.currentTime ?? 0,
                    );
                    setMusicStartSec(Math.max(0, Math.min(t, maxStart)));
                  }}
                  className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted hover:text-ink transition-colors"
                >
                  ⤓ use preview position
                </button>
              </div>
            ))}

          {((mode === "library" && pickedPath && pickedDuration == null) ||
            mode === "theme" ||
            (mode === "upload" && uploadedId) ||
            (mode === "path" && !!musicPath.trim())) && (
            <label className="flex items-center gap-3 font-mono text-[11px] text-ink">
              <span className="whitespace-nowrap">Start at (sec)</span>
              <input
                type="number"
                min={0}
                step={1}
                value={musicStartSec}
                onChange={(e) =>
                  setMusicStartSec(
                    Math.max(0, parseInt(e.target.value || "0", 10)),
                  )
                }
                className={cn(fieldClass, "w-24 px-2 py-1 text-[11px]")}
              />
              <span className="text-ink-soft">
                into the song (0 = from the start)
              </span>
            </label>
          )}

          {/* Volume */}
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
            <Button
              type="submit"
              disabled={!canSubmit}
              pending={submit.isPending}
              pendingLabel="Adding"
              withArrow
            >
              Add music
            </Button>
          </div>
        </form>
    </Panel>
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
    (mode === "default" ||
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
      ...(mode === "upload" && uploadedId
        ? { background_upload_id: uploadedId }
        : {}),
      ...(mode === "url" ? { background_url: bgUrl.trim() } : {}),
    });
  };

  return (
    <Panel label="Split format" bodyClassName="space-y-4">
        <form onSubmit={onSubmit} className="space-y-4">
          {/* Background source tabs */}
          <SegmentedControl
            value={mode}
            onChange={setMode}
            options={(["default", "upload", "url"] as BgMode[]).map((m) => ({
              value: m,
              label:
                m === "url"
                  ? "YouTube URL"
                  : m.charAt(0).toUpperCase() + m.slice(1),
            }))}
          />

          {mode === "default" && (
            <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
              Uses the server&apos;s <code className="text-ink">BACKGROUND_VIDEO_PATH</code> env (e.g. a Minecraft / GTA parkour loop).
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
              {upload.isPending && (
                <span className="text-ink-muted">Uploading…</span>
              )}
              {uploadedId && (
                <span className="text-ink-soft truncate max-w-[12rem]">
                  ✓ {uploadFile?.name}
                </span>
              )}
            </div>
          )}
          {mode === "url" && (
            <TextInput
              type="url"
              value={bgUrl}
              onChange={(e) => setBgUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=…"
            />
          )}

          {/* Audio source segmented */}
          <div>
            <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted mb-2">
              Audio
            </p>
            <SegmentedControl
              className="max-w-xs"
              value={audioMode}
              onChange={setAudioMode}
              options={[
                { value: "fetched_video", label: "Source clip" },
                { value: "bg_video", label: "Background" },
              ]}
            />
          </div>

          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={!canSubmit}
              pending={submit.isPending}
              pendingLabel="Rendering"
              withArrow
            >
              Render split-screen
            </Button>
          </div>
        </form>
    </Panel>
  );
}

// ─── Thumbnail section ───────────────────────────────────────────────────────

function ThumbnailSection({
  jobId,
  clipId,
  hasClip,
}: {
  jobId: string;
  clipId: string;
  hasClip: boolean;
}) {
  const [headline, setHeadline] = useState("");
  const [accent, setAccent] = useState("");
  const [textColor, setTextColor] = useState("");
  const [style, setStyle] = useState<ThumbnailStyle>("auto");
  const [font, setFont] = useState<ThumbnailFont>("auto");
  const submit = useSubmitThumbnailEdit();

  const canSubmit = hasClip && !submit.isPending;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    submit.mutate({
      parent_job_id: jobId,
      clip_id: clipId,
      style,
      font,
      ...(headline.trim() ? { headline: headline.trim() } : {}),
      ...(accent.trim() ? { accent_color: accent.trim() } : {}),
      ...(textColor.trim() ? { text_color: textColor.trim() } : {}),
    });
  };

  const STYLES: { value: ThumbnailStyle; label: string }[] = [
    { value: "auto", label: "AUTO" },
    { value: "bubble", label: "BUBBLE" },
    { value: "highlight", label: "HIGHLIGHT" },
    { value: "box", label: "BOX" },
    { value: "plain", label: "PLAIN" },
  ];

  return (
    <Panel label="Thumbnail" bodyClassName="space-y-4">
        <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
          The model writes the headline and picks the styling from the clip&apos;s
          topic. Leave fields on AUTO / blank to let it decide, or override below.
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          {/* Style selector */}
          <div>
            <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted mb-2">
              Style
            </p>
            <SegmentedControl
              wrap
              itemClassName="text-[10px] normal-case"
              value={style}
              onChange={setStyle}
              options={STYLES}
            />
          </div>

          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span className="w-20 shrink-0">Headline</span>
            <TextInput
              type="text"
              value={headline}
              maxLength={30}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="(optional) override, ≤30 chars"
              className="flex-1"
            />
          </label>

          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span className="w-20 shrink-0">Font</span>
            <select
              value={font}
              onChange={(e) => setFont(e.target.value as ThumbnailFont)}
              className={cn(fieldClass, "px-2 py-1 text-[11px]")}
            >
              <option value="auto">auto (Impact)</option>
              <option value="impact">impact</option>
              <option value="arial">arial</option>
              <option value="condensed">condensed</option>
            </select>
          </label>

          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span className="w-20 shrink-0">Accent</span>
            <TextInput
              type="text"
              value={accent}
              onChange={(e) => setAccent(e.target.value)}
              placeholder="(optional) fill/accent hex, e.g. #FF2D55"
              className="flex-1"
            />
          </label>

          <label className="flex items-center gap-2 font-mono text-[11px] text-ink">
            <span className="w-20 shrink-0">Text color</span>
            <TextInput
              type="text"
              value={textColor}
              onChange={(e) => setTextColor(e.target.value)}
              placeholder="(optional) hex; blank = auto-contrast"
              className="flex-1"
            />
          </label>

          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={!canSubmit}
              pending={submit.isPending}
              pendingLabel="Generating"
              withArrow
            >
              Generate thumbnail
            </Button>
          </div>
        </form>
    </Panel>
  );
}

// ─── Edit history row ────────────────────────────────────────────────────────

function EditJobRow({ job }: { job: EditJob }) {
  const url = job.output_url ? `${API_HOST_URL}${job.output_url}` : null;
  const isVideo = !!url && /\.(mp4|webm|mov)$/i.test(url);
  const isAudio = !!url && /\.(mp3|wav|m4a|ogg)$/i.test(url);
  const isImage = !!url && /\.(jpg|jpeg|png|webp)$/i.test(url);

  return (
    <li className="border border-rule-soft bg-paper-2 overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2 border-b border-rule-soft font-mono text-[10px] tracking-[0.12em] uppercase">
        <span className="text-ink">{job.operation}</span>
        <span aria-hidden className="text-ink-soft">·</span>
        <span className="text-ink-muted">{job.edit_job_id.slice(0, 8)}</span>
        <span
          aria-hidden
          className="ml-auto text-ink-soft"
        />
        <span className={statusColor(job.status)}>{job.status}</span>
      </div>
      {(job.error || url) && (
        <div className="p-3 space-y-2">
          {job.error && (
            <p className="font-mono text-[11px] text-[var(--color-mark)] whitespace-pre-wrap">
              {job.error}
            </p>
          )}
          {url && isVideo && (
            <video
              controls
              src={url}
              className="max-h-[300px] aspect-[9/16] bg-black border border-rule-soft"
            />
          )}
          {url && isAudio && <audio controls src={url} className="w-full" />}
          {url && isImage && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={url}
              alt="Generated thumbnail"
              className="max-h-[300px] aspect-[9/16] object-contain bg-black border border-rule-soft"
            />
          )}
        </div>
      )}
    </li>
  );
}

/**
 * On-theme placeholder shown inside a panel while the parent job is still
 * loading — a pulsing ink dot over the 9:16 media footprint, so a slow fetch
 * reads as "working" rather than an empty frame or a premature "not found".
 */
function LoadingCanvas({ label }: { label: string }) {
  return (
    <div className="w-full max-w-[225px] aspect-[9/16] bg-paper-2 border border-rule-soft flex flex-col items-center justify-center gap-3">
      <span
        aria-hidden
        className="inline-block w-[7px] h-[7px] rounded-full bg-ink ink-pulse"
      />
      <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft">
        {label}
      </p>
    </div>
  );
}

function formatSeconds(total: number): string {
  const s = Math.max(0, Math.round(total));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
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
