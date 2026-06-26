import { ClipPlate } from "./ClipPlate";
import { Reveal } from "./Reveal";

interface ShowcaseClip {
  id: string;
  tone: number;
  duration: string;
  score: string;
  title: string;
  hook: string;
  caption: string;
  highlight: string;
}

// Curated, hard-coded specimens — no API, always looks full.
const showcaseClips: ShowcaseClip[] = [
  {
    id: "clip_03f",
    tone: 0,
    duration: "0:41",
    score: "0.94",
    title: "The one habit that quietly compounds for a decade",
    hook: "Nobody tells you this in your twenties.",
    caption: "this quietly",
    highlight: "compounds",
  },
  {
    id: "clip_07b",
    tone: 1,
    duration: "0:33",
    score: "0.91",
    title: "Why your first draft is supposed to be bad",
    hook: "Stop editing while you write.",
    caption: "your first draft",
    highlight: "is bad",
  },
  {
    id: "clip_01a",
    tone: 3,
    duration: "0:52",
    score: "0.89",
    title: "The negotiation line that flips the whole room",
    hook: "Say this and watch them lean in.",
    caption: "flips the",
    highlight: "room",
  },
  {
    id: "clip_05c",
    tone: 4,
    duration: "0:28",
    score: "0.88",
    title: "A two-minute morning routine that actually sticks",
    hook: "Forget the 5am cold plunge.",
    caption: "this actually",
    highlight: "sticks",
  },
  {
    id: "clip_09e",
    tone: 2,
    duration: "0:46",
    score: "0.86",
    title: "The pricing mistake almost every founder makes",
    hook: "You're charging far too little.",
    caption: "charging too",
    highlight: "little",
  },
  {
    id: "clip_02d",
    tone: 5,
    duration: "0:37",
    score: "0.84",
    title: "How to learn anything twice as fast, backed by research",
    hook: "Re-reading is a trap.",
    caption: "twice as",
    highlight: "fast",
  },
];

export function ClipShowcase() {
  return (
    <section className="pt-24">
      <Reveal>
        <div className="flex items-end justify-between border-b border-ink pb-3">
          <div>
            <p className="kicker mb-2">Specimen sheet</p>
            <h2 className="font-display text-[clamp(1.75rem,4vw,2.75rem)] leading-tight">
              One upload, <span className="display-italic">a whole reel</span>.
            </h2>
          </div>
          <span className="hidden sm:block font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft num-tabular">
            06 of 14 shown
          </span>
        </div>
      </Reveal>

      <div className="mt-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-x-5 gap-y-8">
        {showcaseClips.map((clip, i) => (
          <Reveal key={clip.id} delay={i * 0.05}>
            <figure className="group">
              <div className="transition-transform duration-300 group-hover:-translate-y-1.5">
                <ClipPlate
                  tone={clip.tone}
                  plate={String(i + 1).padStart(2, "0")}
                  duration={clip.duration}
                  caption={clip.caption}
                  highlight={clip.highlight}
                />
              </div>
              <figcaption className="mt-2.5 space-y-1.5">
                <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.06em] text-ink-muted">
                  <span className="text-ink truncate">{clip.id}</span>
                  <span aria-hidden className="text-ink-soft">·</span>
                  <span className="num-tabular">{clip.duration}</span>
                  <span aria-hidden className="text-ink-soft">·</span>
                  <span className="num-tabular">{clip.score}</span>
                </div>
                <p className="text-[13px] leading-snug text-ink line-clamp-2 min-h-[2.25rem]">
                  {clip.title}
                </p>
                <p className="text-[11px] leading-snug italic text-ink-muted line-clamp-1">
                  “{clip.hook}”
                </p>
              </figcaption>
            </figure>
          </Reveal>
        ))}
      </div>

      <Reveal delay={0.1}>
        <p className="mt-6 font-mono text-[10px] tracking-[0.16em] uppercase text-ink-soft">
          Illustrative specimens — generated output varies by source video.
        </p>
      </Reveal>
    </section>
  );
}
