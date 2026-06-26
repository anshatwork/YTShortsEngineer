import { Reveal } from "./Reveal";

/**
 * The real pipeline, in order, mirroring `agents/long_to_shorts/graph.py`.
 * `optional` stages are the env/flag-gated nodes (thumbnail, top_text,
 * subtitles, intro, music).
 */
const STAGES: { name: string; node: string; blurb: string; optional?: boolean }[] = [
  {
    name: "Analyze",
    node: "analyze_video",
    blurb:
      "An LLM reads the transcript and hook-scores every segment, surfacing the moments most likely to land.",
  },
  {
    name: "Clip",
    node: "clipping_logic",
    blurb:
      "Winning segments are cut and reframed to 9:16 in parallel with ffmpeg — vertical, fast, lossless.",
  },
  {
    name: "Write",
    node: "content_gen",
    blurb:
      "Each clip gets a viral title, a one-line hook, a summary, and hashtags generated from its own content.",
  },
  {
    name: "Thumbnail",
    node: "thumbnail",
    blurb: "An AI-directed cover frame is rendered per clip.",
    optional: true,
  },
  {
    name: "Hook text",
    node: "top_text",
    blurb: "The hook line is burned across the top of the frame to stop the scroll.",
    optional: true,
  },
  {
    name: "Subtitles",
    node: "subtitles",
    blurb: "Whisper transcribes the audio and word-timed captions are burned in.",
    optional: true,
  },
  {
    name: "Intro",
    node: "intro_attach",
    blurb: "A title-card intro is prepended with a clean crossfade.",
    optional: true,
  },
  {
    name: "Music",
    node: "music_attach",
    blurb: "A recommended background track is mixed underneath.",
    optional: true,
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-16 pt-24">
      <Reveal>
        <div className="flex items-end justify-between border-b border-ink pb-3">
          <div>
            <p className="kicker mb-2">The pipeline</p>
            <h2 className="font-display text-[clamp(1.75rem,4vw,2.75rem)] leading-tight">
              Eight stages, <span className="display-italic">one pass</span>.
            </h2>
          </div>
          <span className="hidden sm:block font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft text-right leading-relaxed">
            START → END
            <br />
            LangGraph StateGraph
          </span>
        </div>
      </Reveal>

      <ol className="mt-2">
        {STAGES.map((stage, i) => (
          <Reveal key={stage.node} delay={(i % 2) * 0.06}>
            <li className="group grid grid-cols-[auto_1fr] sm:grid-cols-[auto_minmax(0,14rem)_1fr] gap-x-5 sm:gap-x-8 items-baseline border-b border-rule-soft py-5 hover:bg-paper-2/50 transition-colors">
              <span className="font-display text-[2rem] sm:text-[2.5rem] leading-none text-ink-soft num-oldstyle tabular-nums group-hover:text-[var(--color-mark)] transition-colors w-12">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="flex items-baseline gap-3">
                <h3 className="font-display text-xl sm:text-2xl text-ink">
                  {stage.name}
                </h3>
                {stage.optional && (
                  <span className="font-mono text-[9px] tracking-[0.18em] uppercase text-ink-soft border border-rule-soft px-1.5 py-0.5">
                    optional
                  </span>
                )}
              </div>
              <div className="col-span-2 sm:col-span-1 mt-2 sm:mt-0">
                <p className="text-[15px] leading-relaxed text-ink-muted max-w-prose">
                  {stage.blurb}
                </p>
                <span className="mt-1 inline-block font-mono text-[10px] tracking-[0.12em] text-ink-soft opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300">
                  {stage.node}
                </span>
              </div>
            </li>
          </Reveal>
        ))}
      </ol>
    </section>
  );
}
