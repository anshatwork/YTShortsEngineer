import Link from "next/link";
import { DiscoverPanel } from "@/components/discovery/DiscoverPanel";
import { MusicPanel } from "@/components/discovery/MusicPanel";
import { SuggestedForYou } from "@/components/discovery/SuggestedForYou";
import { AudioPreviewProvider } from "@/components/discovery/AudioPreview";
import { Reveal } from "@/components/landing/Reveal";

export const metadata = {
  title: "Discover · YT Shorts Engineer",
  description: "Find trending long-form videos to clip into shorts.",
};

export default function DiscoverPage() {
  return (
    <div className="-mt-2">
      {/* Masthead — mirrors the landing Hero's edition-line pattern */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span className="hidden sm:inline">Archive · Vol. II</span>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Source Room
        </span>
        <Link
          href="/workspace"
          className="hover:text-ink transition-colors"
        >
          ← workspace
        </Link>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Editorial headline */}
      <Reveal>
        <div className="pt-8 pb-10 border-b border-rule-soft">
          <p className="kicker mb-3">Trending signals</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
            Find the video{" "}
            <span className="display-italic text-[var(--color-mark)]">worth clipping</span>.
          </h1>
          <p className="mt-4 text-[16px] leading-relaxed text-ink-muted max-w-xl">
            Search by topic, keyword, or describe what you&apos;re after — an LLM reads the
            signal and surfaces long-form content ready to clip.
          </p>
        </div>
      </Reveal>

      <div className="mt-10 space-y-10">
        <SuggestedForYou />
        <AudioPreviewProvider>
          <DiscoverPanel />
          <MusicPanel />
        </AudioPreviewProvider>
      </div>
    </div>
  );
}
