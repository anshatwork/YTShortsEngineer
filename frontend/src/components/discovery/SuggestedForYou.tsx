"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import {
  useDiscoverSuggestions,
  useMarkSuggestionsSeen,
} from "@/hooks/useDiscoverSuggestions";
import { cn } from "@/lib/utils";
import { DiscoverCard } from "./DiscoverCard";
import { Reveal } from "@/components/landing/Reveal";

/**
 * "Suggested for you" — personalized trending picks the crawler surfaced based
 * on the user's clip history. Renders nothing when there's nothing to show.
 * Opening the section marks the suggestions as seen, clearing the navbar badge.
 */
export function SuggestedForYou() {
  const { data } = useDiscoverSuggestions();
  const markSeen = useMarkSuggestionsSeen();
  const seenSent = useRef(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("discover:panel:suggested") ?? "false");
    } catch {
      return false;
    }
  });

  const suggestions = data?.suggestions ?? [];
  const hasNew = (data?.new_count ?? 0) > 0;

  const toggle = () =>
    setCollapsed((v: boolean) => {
      const next = !v;
      try {
        localStorage.setItem("discover:panel:suggested", JSON.stringify(next));
      } catch {}
      return next;
    });

  useEffect(() => {
    if (hasNew && !seenSent.current) {
      seenSent.current = true;
      markSeen.mutate();
    }
  }, [hasNew, markSeen]);

  if (suggestions.length === 0) return null;

  return (
    <section>
      <Reveal>
        <div className="flex items-end justify-between border-b border-ink pb-3">
          <div>
            <p className="kicker mb-2">Curated for you</p>
            <div className="flex items-baseline gap-3">
              <h2 className="font-display text-[clamp(1.5rem,3vw,2.25rem)] leading-tight">
                Suggested picks
              </h2>
              {data?.new_count ? (
                <span className="font-mono text-[10px] tracking-[0.16em] px-2 py-0.5 bg-[var(--color-mark)] text-paper">
                  {data.new_count} new
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={toggle}
            className="hidden sm:flex items-center gap-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted hover:text-ink transition-colors mb-1"
          >
            {collapsed ? "Show" : "Hide"}
            <ChevronDown
              size={11}
              strokeWidth={1.6}
              className={cn("transition-transform", collapsed && "rotate-180")}
            />
          </button>
        </div>
      </Reveal>

      {!collapsed && data?.interest_summary && (
        <Reveal delay={0.05}>
          <blockquote className="mt-5 pl-4 border-l-2 border-ink">
            <p className="text-[16px] sm:text-[17px] leading-relaxed text-ink-muted display-italic">
              {data.interest_summary}
            </p>
          </blockquote>
        </Reveal>
      )}

      {!collapsed && (
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {suggestions.map((s, i) => (
            <div key={s.video.video_id} className="flex flex-col gap-1.5">
              <DiscoverCard video={s.video} index={i} />
              {s.reason && <p className="kicker mt-0.5">{s.reason}</p>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
