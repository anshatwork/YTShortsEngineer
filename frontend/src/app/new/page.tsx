import { Suspense } from "react";
import Link from "next/link";
import { JobForm } from "@/components/submission/JobForm";
import { Reveal } from "@/components/landing/Reveal";

export const metadata = {
  title: "New Job · YT Shorts Engineer",
  description: "Submit a YouTube URL with full pipeline options.",
};

export default function NewJobPage() {
  return (
    <div className="-mt-2">
      {/* Masthead — matches Discover / Workspace editorial pattern */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span className="hidden sm:inline">Submission · Form</span>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Commission
        </span>
        <Link href="/workspace" className="hover:text-ink transition-colors">
          ← workspace
        </Link>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      {/* Editorial headline */}
      <Reveal>
        <div className="pt-8 pb-10 border-b border-rule-soft">
          <p className="kicker mb-3">Pipeline entry</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
            Submit a{" "}
            <span className="display-italic text-[var(--color-mark)]">source video</span>.
          </h1>
          <p className="mt-4 text-[16px] leading-relaxed text-ink-muted max-w-lg">
            Paste a YouTube link or upload a local file. Configure the pipeline stages, then
            dispatch — the engine handles the rest.
          </p>
        </div>
      </Reveal>

      {/* Form — constrained width for readability */}
      <div className="mt-8 max-w-2xl">
        <Suspense fallback={null}>
          <JobForm />
        </Suspense>
      </div>
    </div>
  );
}
