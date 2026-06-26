import { Reveal } from "@/components/landing/Reveal";

export function Bio() {
  return (
    <Reveal>
      <section>
        {/* Name plate */}
        <div className="flex items-start gap-4">
          <span
            aria-hidden
            className="shrink-0 w-14 h-14 border border-ink bg-ink text-paper flex items-center justify-center font-display text-2xl font-black select-none"
          >
            AC
          </span>
          <div>
            <h1 className="font-display text-[clamp(1.9rem,4vw,2.6rem)] leading-tight">
              Ansh Chawla
            </h1>
            <p className="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-muted mt-1">
              Software Engineer 1 · Adobe
            </p>
          </div>
        </div>

        <div className="rule mt-6" />

        <p className="mt-6 text-[16px] leading-[1.75] text-ink-muted max-w-prose">
          I&apos;m a software engineer at Adobe who likes building agentic tools
          that take a messy, manual workflow and hand it to a graph of small,
          focused steps. The Shorts Engineer is one of those experiments — a
          self-contained pipeline that turns a long video into a feed of
          publish-ready verticals.
        </p>
        <p className="mt-4 text-[16px] leading-[1.75] text-ink-muted max-w-prose">
          It pairs a LangGraph state machine with Whisper, ElevenLabs, and
          ffmpeg behind a FastAPI backend and a Next.js workspace. If you want to
          talk shop about agents, media tooling, or this project, the door&apos;s
          open below.
        </p>
      </section>
    </Reveal>
  );
}
