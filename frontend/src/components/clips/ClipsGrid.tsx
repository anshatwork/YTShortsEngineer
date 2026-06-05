"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ClipCard } from "./ClipCard";
import { cn } from "@/lib/utils";
import type { ClipResult } from "@/types/api";

interface Props {
  clips: ClipResult[];
  jobId?: string;
}

// Card width (px) per breakpoint + the flex gap, used to compute the
// per-arrow scroll step and the active dot. Keep in sync with the className
// widths / gap below.
const CARD_W = 210;
const CARD_W_SM = 230;
const GAP = 12; // gap-3
const SM_BP = 640; // Tailwind `sm`
const MAX_DOTS = 8;

export function ClipsGrid({ clips, jobId }: Props) {
  const railRef = useRef<HTMLDivElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);
  const [active, setActive] = useState(0);

  const step = useCallback(() => {
    const w =
      typeof window !== "undefined" && window.innerWidth >= SM_BP
        ? CARD_W_SM
        : CARD_W;
    return w + GAP;
  }, []);

  const updateEdges = useCallback(() => {
    const el = railRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setAtStart(el.scrollLeft <= 1);
    setAtEnd(el.scrollLeft >= max - 1);
    setActive(Math.round(el.scrollLeft / step()));
  }, [step]);

  useEffect(() => {
    updateEdges();
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [updateEdges, clips.length]);

  const scrollBy = (dir: 1 | -1) => {
    railRef.current?.scrollBy({ left: dir * step(), behavior: "smooth" });
  };

  if (clips.length === 0) {
    return (
      <section className="border border-rule-soft bg-paper px-4 py-8">
        <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft mb-1">
          Clips
        </p>
        <p className="text-sm text-ink-muted">
          No clips were produced.
        </p>
      </section>
    );
  }

  const showDots = clips.length <= MAX_DOTS;

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
          Clips
        </span>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => scrollBy(-1)}
              disabled={atStart}
              aria-label="Previous clips"
              className="border border-ink h-7 w-7 flex items-center justify-center hover:bg-ink hover:text-paper transition-colors disabled:opacity-30 disabled:pointer-events-none"
            >
              <ChevronLeft size={14} strokeWidth={1.5} />
            </button>
            <button
              type="button"
              onClick={() => scrollBy(1)}
              disabled={atEnd}
              aria-label="Next clips"
              className="border border-ink h-7 w-7 flex items-center justify-center hover:bg-ink hover:text-paper transition-colors disabled:opacity-30 disabled:pointer-events-none"
            >
              <ChevronRight size={14} strokeWidth={1.5} />
            </button>
          </div>

          <span className="font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase num-tabular">
            {String(clips.length).padStart(2, "0")} rendered
          </span>
        </div>
      </div>

      <div
        ref={railRef}
        onScroll={updateEdges}
        className="flex gap-3 overflow-x-auto snap-x snap-mandatory scroll-smooth pb-1 [-webkit-overflow-scrolling:touch]"
      >
        {clips.map((clip, i) => (
          <div
            key={clip.clip_id}
            className="snap-start shrink-0 w-[210px] sm:w-[230px]"
          >
            <ClipCard clip={clip} index={i} jobId={jobId} />
          </div>
        ))}
      </div>

      {showDots && (
        <div className="flex items-center justify-center gap-1.5 mt-3">
          {clips.map((clip, i) => (
            <span
              key={clip.clip_id}
              aria-hidden
              className={cn(
                "h-1.5 w-1.5 rounded-full transition-colors",
                i === active ? "bg-ink" : "bg-rule-soft",
              )}
            />
          ))}
        </div>
      )}
    </section>
  );
}
