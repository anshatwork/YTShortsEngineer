import Link from "next/link";
import { Reveal } from "@/components/landing/Reveal";

export const metadata = {
  title: "Create · YT Shorts Engineer",
  description: "Standalone tools — generate TTS voiceovers and split-screen videos.",
};

export default function CreatePage() {
  return (
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-center py-2.5">
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Studio
        </span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Headline */}
      <Reveal>
        <div className="pt-8 pb-8 border-b border-rule-soft">
          <p className="kicker mb-3">standalone tools</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
            Make something{" "}
            <span className="display-italic text-[var(--color-mark)]">from nothing</span>.
          </h1>
          <p className="mt-4 font-mono text-[12px] text-ink-muted max-w-md leading-relaxed">
            No source video required. Pick a tool, write a script or upload footage, and render a short.
          </p>
        </div>
      </Reveal>

      {/* Tool cards */}
      <div className="mt-8 grid gap-6 sm:grid-cols-2">

        {/* TTS Card */}
        <Reveal delay={0.04} className="h-full">
          <Link
            href="/create/tts"
            className="group border border-ink bg-paper flex flex-col overflow-hidden discover-card h-full"
          >
            {/* Specimen mock: waveform */}
            <div className="relative bg-ink overflow-hidden" style={{ height: "180px" }}>
              {/* Grain */}
              <div
                aria-hidden
                className="absolute inset-0 pointer-events-none"
                style={{
                  opacity: 0.04,
                  backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
                }}
              />
              {/* Script fragment */}
              <div className="absolute top-0 inset-x-0 px-5 pt-5 pr-14">
                <p className="font-display display-italic text-paper/75 text-[13px] leading-snug">
                  &ldquo;Most developers ship features. The ones who advance ship understanding.&rdquo;
                </p>
              </div>
              {/* Play button */}
              <div className="absolute right-5 top-5 w-8 h-8 rounded-full border border-paper/30 flex items-center justify-center">
                <svg width="9" height="11" viewBox="0 0 9 11" fill="none" aria-hidden>
                  <path d="M0 0L9 5.5L0 11V0Z" fill="rgba(251,250,245,0.55)" />
                </svg>
              </div>
              {/* Waveform bars — lift on hover */}
              <div className="absolute inset-x-0 bottom-0 flex items-end justify-center gap-[3px] px-5 pb-4 transition-transform duration-300 group-hover:-translate-y-2">
                {[38, 62, 28, 78, 52, 88, 44, 68, 34, 58, 45, 72, 30].map((h, i) => (
                  <div
                    key={i}
                    aria-hidden
                    className="bg-paper/65 rounded-t-[1px] shrink-0"
                    style={{ height: `${h}%`, width: "7px" }}
                  />
                ))}
              </div>
              <div className="absolute bottom-2.5 right-4">
                <span className="font-mono text-[8px] tracking-[0.2em] uppercase text-paper/25">
                  TTS
                </span>
              </div>
            </div>

            {/* Card body */}
            <div className="px-5 pt-4 pb-5 flex flex-col gap-2.5 flex-1">
              <p className="kicker">tool — 001</p>
              <h2 className="font-display text-[clamp(1.2rem,2.5vw,1.5rem)] leading-tight text-ink">
                TTS voiceover
              </h2>
              <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
                Write or generate a script, synthesize narration audio, optionally lay it behind a video.
              </p>
              <div className="mt-auto pt-1 flex items-center gap-1 font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft group-hover:text-ink transition-colors">
                Open studio
                <span className="transition-transform duration-200 group-hover:translate-x-0.5">→</span>
              </div>
            </div>
          </Link>
        </Reveal>

        {/* Split-screen Card */}
        <Reveal delay={0.08} className="h-full">
          <Link
            href="/create/split-screen"
            className="group border border-ink bg-paper flex flex-col overflow-hidden discover-card h-full"
          >
            {/* Specimen mock: 9:16 split format */}
            <div className="relative overflow-hidden bg-paper-2" style={{ height: "180px" }}>
              <div className="absolute inset-0 flex items-stretch">
                {/* Narrow 9:16 format strip */}
                <div
                  className="flex flex-col shrink-0 border-r border-ink/20 transition-transform duration-300 group-hover:-translate-y-1.5"
                  style={{ width: "70px" }}
                >
                  {/* Foreground zone */}
                  <div className="flex-1 bg-ink flex items-center justify-center">
                    <span className="font-mono text-[7px] tracking-[0.15em] uppercase text-paper/40">
                      9:16
                    </span>
                  </div>
                  {/* Hairline */}
                  <div className="h-px bg-paper/20" />
                  {/* Background zone */}
                  <div
                    className="flex-1 flex items-center justify-center"
                    style={{
                      backgroundImage:
                        "repeating-linear-gradient(45deg, transparent 0 6px, rgba(20,17,11,0.12) 6px 7px)",
                    }}
                  >
                    <span className="font-mono text-[7px] tracking-[0.15em] uppercase text-ink/35">
                      BG
                    </span>
                  </div>
                </div>
                {/* Right description panel */}
                <div className="flex-1 px-5 pt-5 pb-4 flex flex-col justify-between">
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.18em] uppercase text-ink-muted mb-2">
                      9:16 format
                    </p>
                    <p className="font-display display-italic text-ink text-[13px] leading-snug">
                      Content above.{" "}
                      <br />
                      Gameplay below.
                    </p>
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <div className="w-[18px] h-[2px] bg-ink" />
                      <span className="font-mono text-[8px] tracking-[0.12em] uppercase text-ink-muted">
                        foreground
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div
                        className="w-[18px] h-[2px]"
                        style={{
                          backgroundImage:
                            "repeating-linear-gradient(90deg, var(--color-ink) 0 3px, transparent 3px 5px)",
                        }}
                      />
                      <span className="font-mono text-[8px] tracking-[0.12em] uppercase text-ink-muted">
                        background
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute bottom-2.5 right-4">
                <span className="font-mono text-[8px] tracking-[0.2em] uppercase text-ink/25">
                  SPLIT
                </span>
              </div>
            </div>

            {/* Card body */}
            <div className="px-5 pt-4 pb-5 flex flex-col gap-2.5 flex-1">
              <p className="kicker">tool — 002</p>
              <h2 className="font-display text-[clamp(1.2rem,2.5vw,1.5rem)] leading-tight text-ink">
                Split-screen
              </h2>
              <p className="font-mono text-[11px] text-ink-muted leading-relaxed">
                Pair a foreground video with gameplay footage to compose a 9:16 split-screen short.
              </p>
              <div className="mt-auto pt-1 flex items-center gap-1 font-mono text-[10px] tracking-[0.2em] uppercase text-ink-soft group-hover:text-ink transition-colors">
                Open studio
                <span className="transition-transform duration-200 group-hover:translate-x-0.5">→</span>
              </div>
            </div>
          </Link>
        </Reveal>
      </div>
    </div>
  );
}
