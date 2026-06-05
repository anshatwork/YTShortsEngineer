"use client";

import { useState } from "react";
import Link from "next/link";
import { Download, Play, Copy, Wand2, Upload } from "lucide-react";
import type { ClipResult } from "@/types/api";
import { formatDuration, cn, pathToStaticUrl } from "@/lib/utils";
import { useJobStore } from "@/store/jobStore";
import { PublishDialog } from "./PublishDialog";

interface ClipCardProps {
  clip: ClipResult;
  index: number;
  jobId?: string;
}

/**
 * Media-asset card. Thumbnail well on top, dense metadata in the middle,
 * always-visible action bar at the bottom. Designed for scanning in a
 * grid of 3–5 across.
 *
 * Preview is opt-in click-to-play: the well shows a static placeholder
 * until the user clicks `Play`, at which point an inline `<video>` is
 * mounted with `preload="metadata"`. Idle cards pay zero network cost.
 * Range-request streaming is handled by FastAPI's StaticFiles mount.
 */
export function ClipCard({ clip, index, jobId }: ClipCardProps) {
  const score = clip.hook_score.toFixed(2);
  const duration = formatDuration(clip.timestamp_range[0], clip.timestamp_range[1]);
  const plateNo = String(index + 1).padStart(2, "0");

  const addToast = useJobStore((s) => s.addToast);
  const staticUrl = pathToStaticUrl(clip.path);
  const [playing, setPlaying] = useState(false);
  const [showPublish, setShowPublish] = useState(false);

  const handlePlay = () => {
    if (!staticUrl) {
      addToast("No file path for this clip yet.", "error");
      return;
    }
    setPlaying(true);
  };

  const handleSaveClick = (e: React.MouseEvent) => {
    if (!staticUrl) {
      e.preventDefault();
      addToast("No file path for this clip yet.", "error");
    }
  };

  const onCopyId = async () => {
    try {
      await navigator.clipboard.writeText(clip.clip_id);
      addToast(`Copied ${clip.clip_id} to clipboard.`, "success");
    } catch {
      addToast("Could not copy to clipboard.", "error");
    }
  };

  return (
    <article className="border border-ink bg-paper flex flex-col">
      {/* Specimen well — placeholder until Play is clicked, then inline video */}
      <div className="relative aspect-[9/16] bg-paper-2 border-b border-ink overflow-hidden">
        {playing && staticUrl ? (
          <>
            <video
              src={staticUrl}
              className="absolute inset-0 w-full h-full object-contain bg-ink"
              controls
              autoPlay
              preload="metadata"
              playsInline
            />
            <button
              type="button"
              onClick={() => setPlaying(false)}
              aria-label="Close preview"
              className="absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center bg-paper border border-ink font-mono text-[11px] leading-none text-ink hover:bg-ink hover:text-paper transition-colors"
            >
              ✕
            </button>
          </>
        ) : (
          <>
            {/* Plate number — top-left */}
            <span className="absolute top-2 left-2 font-mono text-[10px] tracking-[0.18em] text-ink-muted uppercase">
              plate&nbsp;{plateNo}
            </span>

            {/* Duration chip — top-right */}
            <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-paper border border-ink font-mono text-[10px] tracking-[0.08em] text-ink num-tabular">
              {duration}
            </span>

            {/* Play glyph — centred */}
            <button
              type="button"
              onClick={handlePlay}
              className="absolute inset-0 flex items-center justify-center group"
              aria-label={`Preview clip ${clip.clip_id}`}
            >
              <span className="flex items-center justify-center w-12 h-12 rounded-full border border-ink bg-paper/80 transition-all group-hover:bg-ink group-hover:text-paper">
                <Play size={16} strokeWidth={1.2} className="translate-x-[1px]" />
              </span>
            </button>
          </>
        )}
      </div>

      {/* Metadata */}
      <div className="px-3 pt-2.5 pb-2 flex-1 space-y-1.5">
        {/* Tech line — mono ID · dur · score */}
        <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.06em] text-ink-muted">
          <span className="text-ink truncate">{clip.clip_id}</span>
          <span aria-hidden className="text-ink-soft">·</span>
          <span className="num-tabular">{duration}</span>
          <span aria-hidden className="text-ink-soft">·</span>
          <span className="num-tabular">{score}</span>
        </div>

        {/* Title */}
        {clip.title && (
          <p className="text-[13px] text-ink leading-snug line-clamp-2">
            {clip.title}
          </p>
        )}

        {/* Hook */}
        {clip.hook_text && (
          <p className="text-[11px] text-ink-muted leading-snug line-clamp-1 italic">
            &ldquo;{clip.hook_text}&rdquo;
          </p>
        )}
      </div>

      {/* Action bar — always visible */}
      <div className={cn(
        "grid border-t border-ink font-mono text-[10px] tracking-[0.16em] uppercase",
        jobId ? "grid-cols-5" : "grid-cols-3",
      )}>
        {/* Save — a real anchor so right-click "Save as" and browser-managed
            download semantics work for free; no JS in the hot path. */}
        <a
          href={staticUrl ?? "#"}
          download={`${clip.clip_id}.mp4`}
          onClick={handleSaveClick}
          aria-label="Save"
          title="Save"
          className={cn(
            "flex items-center justify-center h-9 min-w-0 hover:bg-paper-2 transition-colors text-ink",
            !staticUrl && "opacity-60 cursor-not-allowed",
          )}
          aria-disabled={!staticUrl}
        >
          <Download size={11} strokeWidth={1.4} />
        </a>

        <div className="border-l border-ink">
          <ActionButton onClick={handlePlay} icon={<Play size={11} strokeWidth={1.4} />} label="Play" />
        </div>
        <div className="border-l border-ink">
          <ActionButton onClick={onCopyId} icon={<Copy size={11} strokeWidth={1.4} />} label="Copy ID" />
        </div>
        {jobId && (
          <div className="border-l border-ink">
            <Link
              href={`/jobs/${jobId}/clips/${clip.clip_id}/edit`}
              aria-label="Edit"
              title="Edit"
              className="flex items-center justify-center h-9 min-w-0 hover:bg-paper-2 transition-colors text-ink"
            >
              <Wand2 size={11} strokeWidth={1.4} />
            </Link>
          </div>
        )}
        {jobId && (
          <div className="border-l border-ink">
            <ActionButton
              onClick={() => setShowPublish(true)}
              icon={<Upload size={11} strokeWidth={1.4} />}
              label="Publish"
            />
          </div>
        )}
      </div>

      {showPublish && jobId && (
        <PublishDialog
          clip={clip}
          jobId={jobId}
          onClose={() => setShowPublish(false)}
        />
      )}
    </article>
  );
}

function ActionButton({
  onClick,
  icon,
  label,
}: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex items-center justify-center h-9 min-w-0 w-full hover:bg-paper-2 transition-colors text-ink"
    >
      {icon}
    </button>
  );
}
