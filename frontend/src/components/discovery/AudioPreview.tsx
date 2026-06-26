"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Pause, Play } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Shared single-instance audio preview.
 *
 * The whole Discover music surface drives ONE `HTMLAudioElement` through this
 * context, so starting any preview implicitly stops whatever was playing —
 * there is no way for two tracks to sound at once. Track rows render the
 * `<AudioPreview>` control, which is a mono/paper/ink play-button + seekable
 * progress bar replacing the off-brand native `<audio controls>` widget.
 */

interface AudioPreviewState {
  /** The src currently loaded into the single audio element (playing or paused). */
  currentSrc: string | null;
  playing: boolean;
  currentTime: number;
  duration: number;
  /** Play `src`; if it's already the loaded track, toggle play/pause. */
  toggle: (src: string) => void;
  /** Seek the active track to `seconds`. No-op if `src` isn't the active one. */
  seek: (src: string, seconds: number) => void;
}

const AudioPreviewContext = createContext<AudioPreviewState | null>(null);

export function AudioPreviewProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [currentSrc, setCurrentSrc] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Lazily create the one shared element on the client and wire its events.
  const getAudio = useCallback((): HTMLAudioElement => {
    if (!audioRef.current) {
      const el = new Audio();
      el.preload = "none";
      el.addEventListener("timeupdate", () => setCurrentTime(el.currentTime));
      el.addEventListener("loadedmetadata", () =>
        setDuration(Number.isFinite(el.duration) ? el.duration : 0),
      );
      el.addEventListener("play", () => setPlaying(true));
      el.addEventListener("pause", () => setPlaying(false));
      el.addEventListener("ended", () => {
        setPlaying(false);
        setCurrentTime(0);
      });
      audioRef.current = el;
    }
    return audioRef.current;
  }, []);

  const toggle = useCallback(
    (src: string) => {
      const el = getAudio();
      if (currentSrc === src) {
        if (el.paused) void el.play().catch(() => setPlaying(false));
        else el.pause();
        return;
      }
      // Switching tracks: loading a new src on the single element stops the old.
      el.src = src;
      setCurrentSrc(src);
      setCurrentTime(0);
      setDuration(0);
      void el.play().catch(() => setPlaying(false));
    },
    [currentSrc, getAudio],
  );

  const seek = useCallback(
    (src: string, seconds: number) => {
      if (currentSrc !== src) return;
      const el = getAudio();
      el.currentTime = Math.max(0, Math.min(seconds, el.duration || seconds));
      setCurrentTime(el.currentTime);
    },
    [currentSrc, getAudio],
  );

  // Tear the element down on unmount so audio never outlives the page.
  useEffect(() => {
    return () => {
      const el = audioRef.current;
      if (el) {
        el.pause();
        el.src = "";
      }
    };
  }, []);

  const value = useMemo<AudioPreviewState>(
    () => ({ currentSrc, playing, currentTime, duration, toggle, seek }),
    [currentSrc, playing, currentTime, duration, toggle, seek],
  );

  return (
    <AudioPreviewContext.Provider value={value}>
      {children}
    </AudioPreviewContext.Provider>
  );
}

function useAudioPreview(): AudioPreviewState {
  const ctx = useContext(AudioPreviewContext);
  if (!ctx) {
    throw new Error("useAudioPreview must be used within an AudioPreviewProvider");
  }
  return ctx;
}

function formatSeconds(total: number): string {
  if (!Number.isFinite(total) || total <= 0) return "0:00";
  const s = Math.round(total);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * A single track's preview control: play/pause toggle + seekable progress bar +
 * `m:ss / m:ss` readout. All instances share one audio element via context, so
 * only one ever plays. `fallbackDuration` (the catalog-reported length) renders
 * the total before the track has been loaded/played.
 */
export function AudioPreview({
  src,
  fallbackDuration,
}: {
  src: string;
  fallbackDuration?: number | null;
}) {
  const { currentSrc, playing, currentTime, duration, toggle, seek } =
    useAudioPreview();

  const isActive = currentSrc === src;
  const isPlaying = isActive && playing;
  const total = isActive && duration > 0 ? duration : fallbackDuration ?? 0;
  const elapsed = isActive ? currentTime : 0;
  const pct = total > 0 ? Math.min(100, (elapsed / total) * 100) : 0;

  const onScrub = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isActive || total <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    seek(src, ratio * total);
  };

  return (
    <div className="flex items-center gap-2.5">
      <button
        type="button"
        onClick={() => toggle(src)}
        aria-label={isPlaying ? "Pause preview" : "Play preview"}
        className={cn(
          "shrink-0 flex items-center justify-center w-7 h-7 border border-ink transition-colors",
          isActive
            ? "bg-ink text-paper"
            : "bg-paper text-ink hover:bg-ink hover:text-paper",
        )}
      >
        {isPlaying ? (
          <Pause size={12} strokeWidth={2} />
        ) : (
          <Play size={12} strokeWidth={2} className="translate-x-[1px]" />
        )}
      </button>

      <div
        onClick={onScrub}
        className={cn(
          "relative flex-1 h-1.5 bg-paper border border-rule-soft",
          isActive && total > 0 ? "cursor-pointer" : "cursor-default",
        )}
      >
        <div
          className="absolute inset-y-0 left-0 bg-ink"
          style={{ width: `${pct}%` }}
        />
      </div>

      <span className="num-tabular shrink-0 font-mono text-[10px] text-ink-muted tracking-[0.04em]">
        {formatSeconds(elapsed)} / {formatSeconds(total)}
      </span>
    </div>
  );
}
