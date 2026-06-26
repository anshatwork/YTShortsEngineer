import { Reveal } from "./Reveal";

const STACK: { label: string; value: string }[] = [
  { label: "Orchestration", value: "LangGraph StateGraph" },
  { label: "Transcription", value: "OpenAI Whisper" },
  { label: "Voiceover", value: "ElevenLabs TTS" },
  { label: "Media", value: "ffmpeg · 9:16" },
  { label: "Backend", value: "FastAPI · Python" },
  { label: "Frontend", value: "Next.js · React" },
];

export function AboutSection() {
  return (
    <section className="pt-24">
      <Reveal>
        <p className="kicker mb-2">Colophon</p>
        <div className="rule-ink" />
      </Reveal>

      <div className="mt-8 grid lg:grid-cols-[1.6fr_1fr] gap-x-14 gap-y-10">
        {/* Prose column with drop-cap */}
        <Reveal>
          <div className="max-w-prose">
            <p className="text-[18px] leading-[1.7] text-ink first-letter:float-left first-letter:font-display first-letter:text-[5.5rem] first-letter:leading-[0.72] first-letter:pr-3 first-letter:pt-1 first-letter:font-black">
              The Shorts Engineer was built to kill the most tedious part of
              short-form: watching a long video end to end just to find the
              thirty seconds worth posting. Drop in a link and an autonomous
              pipeline does the scouting, cutting, and dressing for you.
            </p>
            <p className="mt-5 text-[16px] leading-[1.75] text-ink-muted">
              Under the hood it&apos;s a linear LangGraph state machine. Each
              node owns one job — score the transcript, extract and reframe the
              clips, write the copy, then optionally generate thumbnails, burn
              hook text and Whisper captions, attach an intro, and mix music.
              Everything renders to vertical, publish-ready video you can push
              straight to YouTube from the workspace.
            </p>
            <p className="mt-5 text-[16px] leading-[1.75] text-ink-muted">
              It started as a personal experiment in agentic media tooling — how
              far a single, well-orchestrated graph could carry a creator from
              raw footage to a finished feed.
            </p>
          </div>
        </Reveal>

        {/* Colophon / stack list */}
        <Reveal delay={0.08}>
          <dl className="border-t border-ink">
            {STACK.map((row) => (
              <div
                key={row.label}
                className="flex items-baseline justify-between gap-4 border-b border-rule-soft py-3"
              >
                <dt className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft">
                  {row.label}
                </dt>
                <dd className="text-[15px] text-ink text-right">{row.value}</dd>
              </div>
            ))}
          </dl>
        </Reveal>
      </div>
    </section>
  );
}
