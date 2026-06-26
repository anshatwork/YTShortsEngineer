"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ClipPlate } from "./ClipPlate";

// Edition line — a static masthead date so the page reads like a front page.
const EDITION_DATE = new Date().toLocaleDateString("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

const ease = [0.22, 1, 0.36, 1] as const;
const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.75, ease } },
};

export function Hero() {
  return (
    <section className="relative">
      {/* Masthead / edition line */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span className="hidden sm:inline">Est. MMXXVI</span>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Shorts Engineer
        </span>
        <span className="num-tabular">{EDITION_DATE}</span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Hero body */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid lg:grid-cols-12 gap-x-10 gap-y-10 pt-10 sm:pt-14 items-start"
      >
        {/* Left — headline column */}
        <div className="lg:col-span-7 xl:col-span-7">
          <motion.p variants={item} className="kicker mb-5">
            A workspace for long-form video
          </motion.p>

          <motion.h1
            variants={item}
            className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2.75rem,8vw,5.75rem)]"
          >
            Turn the long cut
            <br />
            into a feed of{" "}
            <span className="display-italic text-[var(--color-mark)] relative inline-block">
              shorts
              <svg
                aria-hidden
                className="absolute -bottom-1 left-0 w-full overflow-visible"
                viewBox="0 0 100 8"
                preserveAspectRatio="none"
                fill="none"
              >
                <path
                  d="M 2 6 Q 30 1 55 5.5 Q 78 9.5 98 3.5"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                />
              </svg>
            </span>.
          </motion.h1>

          <motion.p
            variants={item}
            className="mt-7 max-w-xl text-[17px] sm:text-[18px] leading-relaxed text-ink-muted"
          >
            Paste a YouTube link and an autonomous{" "}
            <span className="text-ink">LangGraph</span> pipeline hunts the most
            compelling moments, reframes them to 9:16, writes the hooks, voices
            them, and burns the captions — a reel of publish-ready verticals
            from a single source.
          </motion.p>

          {/* CTA row */}
          <motion.div variants={item} className="mt-9 flex flex-wrap items-center gap-4">
            <Link
              href="/workspace"
              className="group inline-flex items-center gap-3 h-12 px-6 bg-ink text-paper font-mono text-[11px] tracking-[0.2em] uppercase hover:bg-ink-muted transition-colors"
            >
              Enter the workspace
              <span aria-hidden className="transition-transform group-hover:translate-x-1">
                →
              </span>
            </Link>
            <a
              href="#how"
              className="inline-flex items-center gap-2 h-12 px-2 font-mono text-[11px] tracking-[0.2em] uppercase text-ink-muted hover:text-ink transition-colors"
            >
              <span aria-hidden className="cmd-cursor !w-[6px] !h-[0.9em]" />
              See how it works
            </a>
          </motion.div>

          {/* Spec strip */}
          <motion.div
            variants={item}
            className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft border-t border-rule-soft pt-4"
          >
            <span className="num-tabular">08 pipeline stages</span>
            <span aria-hidden>·</span>
            <span>9:16 native</span>
            <span aria-hidden>·</span>
            <span>whisper captions</span>
            <span aria-hidden>·</span>
            <span>one-click publish</span>
          </motion.div>
        </div>

        {/* Right — clip mock, slightly raised + rotated for an off-grid feel */}
        <motion.div
          variants={item}
          className="lg:col-span-5 xl:col-span-5 lg:pl-6"
        >
          <div className="relative mx-auto max-w-[320px]">
            {/* Tertiary plate — furthest back, most rotated */}
            <div
              aria-hidden
              className="absolute -right-6 -bottom-6 w-full h-full border border-rule-soft bg-paper-3 rotate-2"
              style={{ opacity: 0.55 }}
            />
            {/* Secondary plate — middle depth */}
            <div
              aria-hidden
              className="absolute -right-3 -bottom-3 w-full h-full border border-rule-soft bg-paper-2 rotate-1"
              style={{ opacity: 0.8 }}
            />
            <ClipPlate
              tone={0}
              plate="01"
              duration="0:38"
              caption="the part nobody"
              highlight="clips"
              big
              className="relative -rotate-1 shadow-[0_24px_60px_-30px_rgba(20,17,11,0.55)]"
            />
            <div className="relative mt-2 flex items-center justify-between font-mono text-[10px] tracking-[0.14em] uppercase text-ink-muted">
              <span className="text-ink">clip_01a · 0:38</span>
              <span className="num-tabular">hook 0.94</span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </section>
  );
}
