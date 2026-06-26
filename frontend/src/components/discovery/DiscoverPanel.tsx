"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useDiscover, useDiscoverTopics } from "@/hooks/useDiscover";
import { cn } from "@/lib/utils";
import { DiscoverCard } from "./DiscoverCard";
import { Reveal } from "@/components/landing/Reveal";
import type { DiscoverInterpretation, DiscoverOrder } from "@/types/api";

const ORDER_OPTIONS: { value: DiscoverOrder; label: string }[] = [
  { value: "relevance", label: "RELEVANT" },
  { value: "viewCount", label: "TRENDING" },
  { value: "date", label: "NEWEST" },
];

const DAYS_OPTIONS = [7, 30, 90, 365];

// Preset duration windows in minutes. `undefined` means unbounded on that side.
// The server floors the lower bound at the 20-minute long-form invariant.
const DURATION_OPTIONS: { label: string; min?: number; max?: number }[] = [
  { label: "ANY" },
  { label: "20–40M", min: 20, max: 40 },
  { label: "40–60M", min: 40, max: 60 },
  { label: "60M+", min: 60 },
];

/** Find the preset bucket matching an inferred min/max window (else ANY). */
function durationIndexFor(
  min: number | null | undefined,
  max: number | null | undefined,
): number {
  const m = min ?? undefined;
  const x = max ?? undefined;
  const idx = DURATION_OPTIONS.findIndex((o) => o.min === m && o.max === x);
  return idx === -1 ? 0 : idx;
}

/**
 * Content-sourcing surface. Drive discovery either by typing a natural-language
 * request in the hero box (LLM-interpreted server-side into the filters below) or
 * by setting the curated topic / keyword / sort / duration controls directly.
 */
export function DiscoverPanel() {
  const topicsQuery = useDiscoverTopics();
  const search = useDiscover();
  const [collapsed, setCollapsed] = useState(() => {
    try { return JSON.parse(localStorage.getItem("discover:panel:videos") ?? "false"); } catch { return false; }
  });

  const [conversation, setConversation] = useState("");
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [queries, setQueries] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [order, setOrder] = useState<DiscoverOrder>("relevance");
  const [daysAgo, setDaysAgo] = useState(30);
  const [durationIdx, setDurationIdx] = useState(0);

  const toggleTopic = (t: string) =>
    setSelectedTopics((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );

  const addQuery = () => {
    const q = draft.trim();
    if (q && !queries.includes(q)) setQueries((prev) => [...prev, q]);
    setDraft("");
  };

  const removeQuery = (q: string) =>
    setQueries((prev) => prev.filter((x) => x !== q));

  const canSearch =
    !search.isPending &&
    (conversation.trim().length > 0 ||
      selectedTopics.length > 0 ||
      queries.length > 0 ||
      draft.trim().length > 0);

  // After a conversational search, reflect what the LLM understood back into the
  // manual controls so the user can see and tweak the inferred filters.
  const syncFromInterpretation = (interp?: DiscoverInterpretation | null) => {
    if (!interp) return;
    setSelectedTopics(interp.topics);
    setQueries(interp.custom_queries);
    setOrder(interp.order);
    // null recency = "any time" — show the widest manual window as the closest match.
    setDaysAgo(interp.days_ago ?? 365);
    setDurationIdx(
      durationIndexFor(interp.min_duration_minutes, interp.max_duration_minutes),
    );
  };

  // The conversational box is authoritative for the scalar controls (sort /
  // length / recency). When the user overrides one of those directly, drop the
  // box text so the next search runs in manual mode with their chosen values.
  const overrideScalar = (apply: () => void) => {
    apply();
    setConversation("");
  };

  const handleSearch = () => {
    // Fold any unsubmitted keyword draft into the query list.
    const finalQueries =
      draft.trim() && !queries.includes(draft.trim())
        ? [...queries, draft.trim()]
        : queries;
    setQueries(finalQueries);
    setDraft("");

    const bucket = DURATION_OPTIONS[durationIdx];
    search.mutate(
      {
        topics: selectedTopics,
        custom_queries: finalQueries,
        conversational_query: conversation.trim() || undefined,
        days_ago: daysAgo,
        max_results_per_query: 8,
        order,
        min_duration_minutes: bucket.min,
        max_duration_minutes: bucket.max,
      },
      { onSuccess: (data) => syncFromInterpretation(data.interpretation) },
    );
  };

  const results = search.data?.videos ?? [];
  const summary = search.data?.interpretation?.summary;

  const toggle = () =>
    setCollapsed((v: boolean) => {
      const next = !v;
      try { localStorage.setItem("discover:panel:videos", JSON.stringify(next)); } catch {}
      return next;
    });

  return (
    <section>
      {/* Editorial section header — matches SuggestedForYou / HowItWorks pattern */}
      <Reveal>
        <div className="flex items-end justify-between border-b border-ink pb-3">
          <div>
            <p className="kicker mb-2">Video search</p>
            <h2 className="font-display text-[clamp(1.5rem,3vw,2.25rem)] leading-tight">
              Source <span className="display-italic">material</span>.
            </h2>
          </div>
          <button
            type="button"
            onClick={toggle}
            className="hidden sm:flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted hover:text-ink transition-colors mb-1"
          >
            {collapsed ? "Expand" : "Collapse"}
            <ChevronDown
              size={11}
              strokeWidth={1.6}
              className={cn("transition-transform", collapsed && "rotate-180")}
            />
          </button>
        </div>
      </Reveal>

      {!collapsed && <div className="mt-5 space-y-6">
      {/* CONTROLS */}
      <Reveal delay={0.04}>
      <div className="border border-ink bg-paper p-4 sm:p-5 space-y-5">
        {/* Hero: conversational search */}
        <div>
          <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-2">
            Ask
          </span>
          <div className="flex items-start border border-ink bg-paper">
            <span
              className="select-none pl-4 pr-3 pt-3 font-mono text-[15px] text-ink"
              aria-hidden
            >
              ❯
            </span>
            <textarea
              value={conversation}
              onChange={(e) => setConversation(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (canSearch) handleSearch();
                }
              }}
              rows={2}
              placeholder="Describe what you're after — e.g. “recent AI agent deep dives under an hour”"
              className="flex-1 resize-none bg-transparent border-0 outline-none py-2.5 pr-4 font-mono text-[13px] leading-relaxed text-ink placeholder:text-ink-soft"
              spellCheck={false}
            />
          </div>
          <span className="block mt-1.5 font-mono text-[10px] tracking-[0.05em] text-ink-soft">
            Enter to search · Shift+Enter for a new line · refine with the filters below
          </span>
        </div>

        {/* Topics */}
        <div>
          <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-2">
            Topics
          </span>
          {topicsQuery.isLoading ? (
            <span className="font-mono text-[11px] text-ink-soft">Loading…</span>
          ) : (
            <div className="flex flex-wrap gap-2">
              {(topicsQuery.data?.topics ?? []).map((t) => {
                const active = selectedTopics.includes(t);
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleTopic(t)}
                    className={cn(
                      "px-3 h-8 border border-ink font-mono text-[11px] tracking-[0.12em] uppercase transition-colors",
                      active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                    )}
                  >
                    {t.replace(/_/g, " ")}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Free-text queries */}
        <div>
          <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-2">
            Keywords
          </span>
          <div className="flex items-center border border-ink bg-paper h-10 px-3">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addQuery();
                }
              }}
              placeholder="Type a keyword, press Enter…"
              className="flex-1 bg-transparent border-0 outline-none font-mono text-[12px] text-ink placeholder:text-ink-soft"
              spellCheck={false}
            />
          </div>
          {queries.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {queries.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => removeQuery(q)}
                  className="px-2.5 h-7 border border-ink bg-paper-2 font-mono text-[10px] tracking-[0.1em] text-ink hover:bg-paper transition-colors flex items-center gap-2"
                  title="Remove"
                >
                  {q} <span className="text-ink-soft">✕</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Sort + duration + recency + search */}
        <div className="flex flex-wrap items-end gap-5">
          <div>
            <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-1.5">
              Sort
            </span>
            <div className="grid grid-cols-3 border border-ink">
              {ORDER_OPTIONS.map((opt, i) => {
                const active = order === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => overrideScalar(() => setOrder(opt.value))}
                    className={cn(
                      "px-3 py-2 font-mono text-[10px] tracking-[0.12em] transition-colors",
                      i !== ORDER_OPTIONS.length - 1 && "border-r border-ink",
                      active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-1.5">
              Length
            </span>
            <div className="grid grid-cols-4 border border-ink">
              {DURATION_OPTIONS.map((opt, i) => {
                const active = durationIdx === i;
                return (
                  <button
                    key={opt.label}
                    type="button"
                    onClick={() => overrideScalar(() => setDurationIdx(i))}
                    className={cn(
                      "px-3 py-2 font-mono text-[10px] tracking-[0.12em] transition-colors whitespace-nowrap",
                      i !== DURATION_OPTIONS.length - 1 && "border-r border-ink",
                      active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-1.5">
              Within
            </span>
            <div className="grid grid-cols-4 border border-ink">
              {DAYS_OPTIONS.map((d, i) => {
                const active = daysAgo === d;
                return (
                  <button
                    key={d}
                    type="button"
                    onClick={() => overrideScalar(() => setDaysAgo(d))}
                    className={cn(
                      "px-3 py-2 font-mono text-[10px] tracking-[0.12em] transition-colors",
                      i !== DAYS_OPTIONS.length - 1 && "border-r border-ink",
                      active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                    )}
                  >
                    {d === 365 ? "1Y" : `${d}D`}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            onClick={handleSearch}
            disabled={!canSearch}
            className={cn(
              "h-10 px-5 ml-auto font-mono text-[11px] tracking-[0.2em] uppercase border border-ink transition-colors flex items-center gap-3",
              !canSearch
                ? "bg-paper-2 text-ink-soft cursor-not-allowed"
                : "bg-ink text-paper hover:bg-ink-muted",
            )}
          >
            {search.isPending ? (
              <>
                <span className="inline-block w-3 h-3 rounded-full border border-paper border-t-transparent animate-spin" />
                Searching
              </>
            ) : (
              <>Search ↵</>
            )}
          </button>
        </div>
      </div>
      </Reveal>

      {/* RESULTS */}
      {search.isPending ? (
        <div className="flex items-center gap-3 py-2">
          <span className="w-4 h-4 rounded-full border border-ink border-t-transparent animate-spin ink-pulse" />
          <span className="font-mono text-[11px] tracking-[0.12em] text-ink-soft uppercase">
            Fetching trending long-form videos…
          </span>
        </div>
      ) : search.isSuccess && results.length === 0 ? (
        <div className="py-8 text-center border border-rule-soft">
          <p className="font-display text-[1.25rem] text-ink-muted">No videos matched.</p>
          <p className="mt-1 font-mono text-[10px] tracking-[0.14em] text-ink-soft uppercase">
            Try different topics, keywords or a wider length range.
          </p>
        </div>
      ) : results.length > 0 ? (
        <>
          {summary && (
            <p className="font-mono text-[11px] tracking-[0.04em] text-ink-muted italic border-l-2 border-ink pl-3">
              · {summary}
            </p>
          )}
          <p className="font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase">
            {results.length} candidate{results.length === 1 ? "" : "s"} ·{" "}
            {(search.data?.queries_used ?? []).join(" · ")}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.map((v, i) => (
              <DiscoverCard key={v.video_id} video={v} index={i} />
            ))}
          </div>
        </>
      ) : null}
    </div>}
    </section>
  );
}
