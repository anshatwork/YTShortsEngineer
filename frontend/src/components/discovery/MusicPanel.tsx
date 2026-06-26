"use client";

import { useRef, useState } from "react";
import { ChevronDown, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  useAddSong,
  useDeleteMusicTrack,
  useMusicTracks,
  useRefreshMusic,
  useSearchMusic,
  useTrendingSongs,
  useUploadMusicTrack,
  useYouTubeSongSearch,
} from "@/hooks/useMusicLibrary";
import { useJobStore } from "@/store/jobStore";
import { API_HOST_URL } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { AUDIO_THEMES, type AudioTheme, type MusicSearchResult } from "@/types/api";
import { AudioPreview } from "./AudioPreview";

type Mode = "search" | "trending" | "youtube";

const ORDERS: { value: string; label: string }[] = [
  { value: "popular", label: "TRENDING" },
  { value: "latest", label: "NEWEST" },
  { value: "relevance", label: "RELEVANT" },
];

function formatSeconds(total?: number | null): string {
  if (total == null) return "—";
  const s = Math.max(0, Math.round(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Unified Discover music surface — merges the former SongLibrary (catalog search)
 * and TrendingMusic (browse-by-mood + upload) into one box. A conversational
 * "vibe" box drives an LLM-interpreted catalog search; a SEARCH / TRENDING toggle
 * switches between search results and mood browsing. Every preview routes through
 * one shared <AudioPreview>, so only a single track ever plays.
 */
export function MusicPanel() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return JSON.parse(localStorage.getItem("discover:panel:music") ?? "false"); } catch { return false; }
  });
  const togglePanel = () =>
    setCollapsed((v: boolean) => {
      const next = !v;
      try { localStorage.setItem("discover:panel:music", JSON.stringify(next)); } catch {}
      return next;
    });

  const [mode, setMode] = useState<Mode>("search");

  // Search state. `term` is what's sent to the API; `conversational` marks it as
  // a natural-language vibe phrase the server distills before searching.
  const [draft, setDraft] = useState("");
  const [term, setTerm] = useState("");
  const [conversational, setConversational] = useState(false);
  const [order, setOrder] = useState("popular");

  // Trending (mood-browse) state.
  const [theme, setTheme] = useState<AudioTheme>("energetic");

  // YouTube songs search term (separate from the royalty-free `term`).
  const [ytTerm, setYtTerm] = useState("");

  // Upload form state.
  const [showUpload, setShowUpload] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadTheme, setUploadTheme] = useState<AudioTheme>("energetic");
  const [title, setTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const search = useSearchMusic(term, order, conversational);
  const trending = useTrendingSongs(mode === "youtube" && !ytTerm.trim());
  const ytSearch = useYouTubeSongSearch(mode === "youtube" ? ytTerm : "");
  const add = useAddSong();
  const songs = useMusicTracks("songs");
  const moodTracks = useMusicTracks(theme);
  const remove = useDeleteMusicTrack();
  const refresh = useRefreshMusic();
  const upload = useUploadMusicTrack();
  const addToast = useJobStore((s) => s.addToast);

  const runVibeSearch = () => {
    const q = draft.trim();
    if (!q) return;
    // In YT mode the box keyword-searches YouTube; otherwise it's a royalty-free
    // conversational "vibe" search.
    if (mode === "youtube") {
      setYtTerm(q);
      return;
    }
    setTerm(q);
    setConversational(true);
    setMode("search");
  };

  // Re-sort: distil the prior conversational result into an exact query so the
  // chosen order is honored (the server lets the LLM pick order for vibe searches).
  const onOrder = (value: string) => {
    setOrder(value);
    if (conversational) {
      const distilled = search.data?.query_used ?? term;
      if (distilled) {
        setTerm(distilled);
        setConversational(false);
      }
    }
  };

  const onAdd = (r: MusicSearchResult) =>
    add.mutate({
      source: r.source,
      source_id: r.source_id,
      title: r.title,
      download_url: r.download_url,
      duration: r.duration,
      attribution: r.attribution,
    });

  const onUpload = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    upload.mutate(
      { file, theme: uploadTheme, title: title.trim() || undefined },
      {
        onSuccess: (track) => {
          setFile(null);
          setTitle("");
          if (fileInputRef.current) fileInputRef.current.value = "";
          setMode("trending");
          setTheme(track.theme as AudioTheme);
          setShowUpload(false);
        },
      },
    );
  };

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      addToast("Track path copied — paste into the editor's library/path tab.", "success");
    } catch {
      addToast("Could not copy to clipboard.", "error");
    }
  };

  const results = search.data?.results ?? [];
  const summary = search.data?.interpretation?.summary;
  const library = songs.data?.tracks ?? [];
  const moods = moodTracks.data?.tracks ?? [];

  return (
    <section className="border border-ink bg-paper mt-6">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <button
          type="button"
          onClick={togglePanel}
          className="flex items-center gap-2 font-mono text-[11px] tracking-[0.2em] text-ink uppercase hover:text-ink-muted transition-colors"
        >
          Music
          <ChevronDown
            size={13}
            strokeWidth={1.6}
            className={cn("transition-transform", collapsed && "rotate-180")}
          />
        </button>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="flex items-center gap-1.5 border border-ink px-2.5 h-7 font-mono text-[10px] tracking-[0.16em] uppercase hover:bg-ink hover:text-paper transition-colors disabled:opacity-40"
        >
          <RefreshCw
            size={12}
            strokeWidth={1.6}
            className={refresh.isPending ? "animate-spin" : ""}
          />
          refresh
        </button>
      </div>

      {!collapsed && <div className="px-4 pb-4 space-y-4 border-t border-ink pt-4">

      <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
        Free, Creative-Commons tracks (Jamendo/Pixabay). Describe a vibe to search,
        or browse trending beds by mood. Preview here, add the ones you want, then
        pick them in a clip&apos;s{" "}
        <span className="text-ink">Add background music → library</span>.
      </p>

      {/* Conversational vibe box */}
      <div>
        <div className="flex items-start border border-ink bg-paper">
          <span
            className="select-none pl-3 pr-2.5 pt-2.5 font-mono text-[14px] text-ink"
            aria-hidden
          >
            ❯
          </span>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                runVibeSearch();
              }
            }}
            rows={2}
            placeholder={
              mode === "youtube"
                ? "Search YouTube for a song or artist — e.g. “espresso sabrina carpenter”"
                : "Describe a vibe — e.g. “upbeat lo-fi for a cooking montage” — or just a song / artist"
            }
            className="flex-1 resize-none bg-transparent border-0 outline-none py-2 pr-3 font-mono text-[12px] leading-relaxed text-ink placeholder:text-ink-soft"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={runVibeSearch}
            disabled={!draft.trim() || search.isFetching || ytSearch.isFetching}
            className="self-stretch border-l border-ink px-4 font-mono text-[10px] tracking-[0.16em] uppercase bg-ink text-paper hover:bg-ink-muted transition-colors disabled:opacity-40"
          >
            {search.isFetching || ytSearch.isFetching ? "…" : "search ↵"}
          </button>
        </div>
        <span className="block mt-1.5 font-mono text-[10px] tracking-[0.04em] text-ink-soft">
          Enter to search · Shift+Enter for a new line
        </span>
      </div>

      {/* Mode toggle */}
      <div className="grid grid-cols-3 border border-ink">
        {(["search", "trending", "youtube"] as Mode[]).map((m, i) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              "px-3 py-2 font-mono text-[10px] tracking-[0.16em] uppercase transition-colors",
              i < 2 && "border-r border-ink",
              mode === m ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-paper-2",
            )}
          >
            {m === "search" ? "Search" : m === "trending" ? "Moods" : "YT Songs"}
          </button>
        ))}
      </div>

      {/* ── SEARCH ─────────────────────────────────────────────── */}
      {mode === "search" && (
        <div className="space-y-3">
          <div className="flex items-center gap-1.5">
            {ORDERS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => onOrder(o.value)}
                className={cn(
                  "border border-ink px-2.5 h-6 font-mono text-[9px] tracking-[0.14em] uppercase transition-colors",
                  order === o.value ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-paper-2",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          {summary && term && (
            <p className="font-mono text-[11px] tracking-[0.02em] text-ink">{summary}</p>
          )}

          {!term ? (
            <p className="font-mono text-[11px] text-ink-muted">
              Describe a vibe above and hit search.
            </p>
          ) : search.isLoading ? (
            <p className="font-mono text-[11px] text-ink-muted">searching…</p>
          ) : results.length === 0 ? (
            <p className="font-mono text-[11px] text-ink-muted">
              No matches. Try a different vibe or song (free catalogs only — no
              major-label hits).
            </p>
          ) : (
            <ul className="space-y-2">
              {results.map((r) => (
                <li
                  key={`${r.source}:${r.source_id}`}
                  className="border border-rule-soft bg-paper-2 p-3 space-y-2"
                >
                  <div className="flex items-center gap-2 font-mono text-[11px] text-ink">
                    <span className="truncate flex-1">
                      {r.title}
                      {r.artist && <span className="text-ink-muted"> — {r.artist}</span>}
                    </span>
                    <span className="text-ink-soft uppercase tracking-[0.12em]">{r.source}</span>
                    <button
                      type="button"
                      onClick={() => onAdd(r)}
                      disabled={r.already_cached || add.isPending}
                      className="shrink-0 flex items-center gap-1 border border-ink px-2 h-6 font-mono text-[9px] tracking-[0.14em] uppercase hover:bg-ink hover:text-paper transition-colors disabled:opacity-40 disabled:hover:bg-paper disabled:hover:text-ink"
                    >
                      <Plus size={11} strokeWidth={1.8} />
                      {r.already_cached ? "added" : "add"}
                    </button>
                  </div>
                  <AudioPreview src={r.preview_url} fallbackDuration={r.duration} />
                </li>
              ))}
            </ul>
          )}

          {/* Your library (songs bucket) */}
          <div className="space-y-2 pt-1">
            <span className="block font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft">
              Your library
            </span>
            {library.length === 0 ? (
              <p className="font-mono text-[11px] text-ink-muted">
                No songs added yet — search above and hit add.
              </p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2">
                {library.map((t) => (
                  <li key={t.track_id} className="border border-rule-soft bg-paper-2 p-3 space-y-2">
                    <div className="flex items-center gap-2 font-mono text-[11px] text-ink">
                      <span className="truncate flex-1">{t.title}</span>
                      <span className="num-tabular text-ink-muted">{formatSeconds(t.duration)}</span>
                      <button
                        type="button"
                        onClick={() => remove.mutate({ trackId: t.track_id, theme: "songs" })}
                        disabled={remove.isPending}
                        aria-label="Delete song"
                        title="Delete song"
                        className="shrink-0 text-ink-soft hover:text-[var(--color-mark)] transition-colors disabled:opacity-40"
                      >
                        <Trash2 size={12} strokeWidth={1.6} />
                      </button>
                    </div>
                    <AudioPreview
                      src={`${API_HOST_URL}${t.preview_url}`}
                      fallbackDuration={t.duration}
                    />
                    <div className="flex items-center gap-3">
                      {t.attribution && (
                        <p className="font-mono text-[9px] text-ink-soft truncate flex-1">
                          {t.attribution}
                        </p>
                      )}
                      <button
                        type="button"
                        onClick={() => copyPath(t.path)}
                        className="ml-auto shrink-0 font-mono text-[9px] tracking-[0.16em] uppercase text-ink-muted hover:text-ink transition-colors"
                      >
                        copy path
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* ── TRENDING ───────────────────────────────────────────── */}
      {mode === "trending" && (
        <div className="space-y-3">
          {/* Mood chips */}
          <div className="flex flex-wrap gap-1.5">
            {AUDIO_THEMES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTheme(t)}
                className={cn(
                  "border border-ink px-2.5 h-7 font-mono text-[10px] tracking-[0.14em] uppercase transition-colors",
                  theme === t ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-paper-2",
                )}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Mood tracks */}
          {moodTracks.isLoading ? (
            <p className="font-mono text-[11px] text-ink-muted">loading tracks…</p>
          ) : moods.length === 0 ? (
            <p className="font-mono text-[11px] text-ink-muted">
              No cached tracks for <span className="text-ink">{theme}</span> yet. Hit
              refresh (needs <code>JAMENDO_CLIENT_ID</code> on the server).
            </p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {moods.map((t) => (
                <li key={t.track_id} className="border border-rule-soft bg-paper-2 p-3 space-y-2">
                  <div className="flex items-center gap-2 font-mono text-[11px] text-ink">
                    <span className="truncate flex-1">{t.title}</span>
                    <span className="num-tabular text-ink-muted">{formatSeconds(t.duration)}</span>
                    <span className="text-ink-soft uppercase tracking-[0.12em]">{t.source}</span>
                    {t.deletable && (
                      <button
                        type="button"
                        onClick={() => remove.mutate({ trackId: t.track_id, theme: t.theme })}
                        disabled={remove.isPending}
                        aria-label="Delete track"
                        title="Delete track"
                        className="shrink-0 text-ink-soft hover:text-[var(--color-mark)] transition-colors disabled:opacity-40"
                      >
                        <Trash2 size={12} strokeWidth={1.6} />
                      </button>
                    )}
                  </div>
                  <AudioPreview
                    src={`${API_HOST_URL}${t.preview_url}`}
                    fallbackDuration={t.duration}
                  />
                  <div className="flex items-center gap-3">
                    {t.attribution && (
                      <p className="font-mono text-[9px] text-ink-soft truncate flex-1">
                        {t.attribution}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => copyPath(t.path)}
                      className="ml-auto shrink-0 font-mono text-[9px] tracking-[0.16em] uppercase text-ink-muted hover:text-ink transition-colors"
                    >
                      copy path
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {/* Add a track (collapsible) */}
          <div className="border border-rule-soft bg-paper-2">
            <button
              type="button"
              onClick={() => setShowUpload((v) => !v)}
              className="flex items-center justify-between w-full px-3 py-2 font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft hover:text-ink transition-colors"
            >
              Add a track
              <ChevronDown
                size={13}
                strokeWidth={1.6}
                className={cn("transition-transform", showUpload && "rotate-180")}
              />
            </button>
            {showUpload && (
              <form onSubmit={onUpload} className="px-3 pb-3 space-y-2">
                <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-ink">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    className="font-mono text-[11px] max-w-[16rem]"
                  />
                  <label className="flex items-center gap-2">
                    <span className="text-ink-soft">mood</span>
                    <select
                      value={uploadTheme}
                      onChange={(e) => setUploadTheme(e.target.value as AudioTheme)}
                      className="border border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                    >
                      {AUDIO_THEMES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="(optional) title"
                    className="flex-1 min-w-[8rem] border border-ink bg-paper px-2 py-1 font-mono text-[11px] text-ink"
                  />
                  <button
                    type="submit"
                    disabled={!file || upload.isPending}
                    className="border border-ink px-3 h-7 font-mono text-[10px] tracking-[0.16em] uppercase bg-ink text-paper hover:bg-paper hover:text-ink transition-colors disabled:opacity-40"
                  >
                    {upload.isPending ? "uploading…" : "add"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── YOUTUBE TRENDING SONGS ─────────────────────────────── */}
      {mode === "youtube" && (
        <div className="space-y-3">
          {/* Copyright notice — always shown for this tab. */}
          <div className="border border-[var(--color-mark)] bg-paper-2 p-3">
            <p className="font-mono text-[11px] leading-relaxed text-ink">
              <span className="text-[var(--color-mark)]">⚠ Copyrighted music.</span>{" "}
              These are real trending songs. Using one as background audio can get your
              Short <span className="text-ink">claimed, muted, demonetized, or struck</span>{" "}
              by Content ID if you upload it to YouTube. Use at your own risk.
            </p>
          </div>

          {(() => {
            const searching = !!ytTerm.trim();
            const activeQuery = searching ? ytSearch : trending;
            const ytResults = activeQuery.data?.results ?? [];
            return (
          <>
          {searching && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] text-ink">
                Results for <span className="text-ink-muted">“{ytTerm.trim()}”</span>
              </span>
              <button
                type="button"
                onClick={() => setYtTerm("")}
                className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-soft hover:text-ink transition-colors"
              >
                ✕ clear → trending
              </button>
            </div>
          )}
          {activeQuery.isLoading ? (
            <p className="font-mono text-[11px] text-ink-muted">
              {searching ? "searching youtube…" : "loading trending songs…"}
            </p>
          ) : activeQuery.isError ? (
            <p className="font-mono text-[11px] text-ink-muted">
              Couldn&apos;t load songs (needs <code>YT_API_KEY</code> on the server).
            </p>
          ) : ytResults.length === 0 ? (
            <p className="font-mono text-[11px] text-ink-muted">
              {searching ? "No songs matched that search." : "No trending songs right now."}
            </p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {ytResults.map((r) => (
                <li
                  key={`${r.source}:${r.source_id}`}
                  className="border border-rule-soft bg-paper-2 p-3 space-y-2"
                >
                  <div className="flex items-center gap-2 font-mono text-[11px] text-ink">
                    <span className="truncate flex-1">
                      {r.title}
                      {r.artist && <span className="text-ink-muted"> — {r.artist}</span>}
                    </span>
                    <span
                      title={r.copyright_warning ?? "Copyrighted"}
                      className="shrink-0 border border-[var(--color-mark)] text-[var(--color-mark)] px-1 leading-tight text-[9px] tracking-[0.1em] uppercase"
                    >
                      ⚠ ©
                    </span>
                    <button
                      type="button"
                      onClick={() => onAdd(r)}
                      disabled={r.already_cached || add.isPending}
                      className="shrink-0 flex items-center gap-1 border border-ink px-2 h-6 font-mono text-[9px] tracking-[0.14em] uppercase hover:bg-ink hover:text-paper transition-colors disabled:opacity-40 disabled:hover:bg-paper disabled:hover:text-ink"
                    >
                      <Plus size={11} strokeWidth={1.8} />
                      {r.already_cached ? "added" : "add"}
                    </button>
                  </div>
                  {/* YouTube embed preview — no direct audio URL, so play in-place. */}
                  <div className="aspect-video w-full border border-rule-soft bg-ink/5">
                    <iframe
                      src={`https://www.youtube.com/embed/${r.source_id}`}
                      title={r.title}
                      loading="lazy"
                      allow="encrypted-media; picture-in-picture"
                      className="h-full w-full"
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}

          <p className="font-mono text-[10px] text-ink-soft leading-relaxed">
            Adding downloads the song&apos;s audio into{" "}
            <span className="text-ink">Your library</span> (on the Search tab) — the
            copyright warning stays attached. Pick it in a clip&apos;s{" "}
            <span className="text-ink">Add background music → library</span>.
          </p>
          </>
            );
          })()}
        </div>
      )}
      </div>}
    </section>
  );
}
