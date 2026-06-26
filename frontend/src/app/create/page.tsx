import Link from "next/link";

export const metadata = {
  title: "Create · YT Shorts Engineer",
  description: "Standalone tools — generate TTS voiceovers and split-screen videos.",
};

const TOOLS = [
  {
    href: "/create/tts",
    label: "TTS voiceover",
    blurb:
      "Type a script or give a summary and let Claude/Qwen write one, then synthesize narration audio.",
  },
  {
    href: "/create/split-screen",
    label: "Split-screen",
    blurb:
      "Upload a foreground video and pair it with a gameplay background to compose a 9:16 split-screen short.",
  },
];

export default function CreatePage() {
  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-5">
        <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
          Create
        </span>
        <Link
          href="/workspace"
          className="font-mono text-[10px] tracking-[0.18em] text-ink-muted hover:text-ink uppercase transition-colors"
        >
          ← workspace
        </Link>
      </div>

      <p className="font-mono text-[11px] text-ink-muted mb-4">
        Standalone tools — no source video required.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        {TOOLS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="group border border-ink bg-paper p-4 space-y-2 hover:bg-paper-2 transition-colors"
          >
            <p className="font-mono text-[11px] tracking-[0.18em] uppercase text-ink group-hover:text-ink">
              {t.label}
            </p>
            <p className="text-[12px] text-ink-muted leading-snug">{t.blurb}</p>
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft group-hover:text-ink transition-colors">
              open →
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
