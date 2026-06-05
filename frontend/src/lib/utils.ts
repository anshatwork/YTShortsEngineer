import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { API_HOST_URL } from "@/lib/constants";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Resolve a backend filesystem path under output/ to a /static URL.
 *
 * The backend stores ``clip.path`` as whatever ``Path("output") / …`` produced,
 * which is **relative** on Windows (``output\jobs\<id>\clips\<id>.mp4``).
 * Absolute paths are also possible if OUTPUT_DIR is set to an absolute root.
 * We normalise both forms by prepending a leading slash before searching for
 * the ``/output/`` segment — that way ``output/jobs/…`` becomes
 * ``/output/jobs/…`` and matches the same lookup as a truly absolute path.
 *
 * Returns ``null`` when the path doesn't sit under any ``output/`` segment,
 * so callers can fall back to a "no file yet" UI state.
 */
export function pathToStaticUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  const normalized = "/" + path.replace(/\\/g, "/").replace(/^\/+/, "");
  const idx = normalized.toLowerCase().lastIndexOf("/output/");
  if (idx < 0) return null;
  const rel = normalized.slice(idx + "/output/".length);
  return `${API_HOST_URL}/static/${rel}`;
}

export function formatDate(iso: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function formatDuration(start: number, end: number) {
  const secs = Math.round(end - start);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function isValidYouTubeUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return (
      (u.hostname === "www.youtube.com" ||
        u.hostname === "youtube.com" ||
        u.hostname === "youtu.be") &&
      (u.searchParams.has("v") || u.hostname === "youtu.be")
    );
  } catch {
    return false;
  }
}

/**
 * Compact relative-time format for data-grids — "now", "37s", "4m", "2h",
 * "3d". Goes back to an absolute "MMM d" once a week has passed.
 */
export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 5) return "now";
  if (diffSec < 60) return `${diffSec}s`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d`;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}
