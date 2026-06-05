import Link from "next/link";
import { JobForm } from "@/components/submission/JobForm";

export const metadata = {
  title: "New Job · YT Shorts Engineer",
  description: "Submit a YouTube URL with full pipeline options.",
};

export default function NewJobPage() {
  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-5">
        <span className="font-mono text-[11px] tracking-[0.2em] text-ink uppercase">
          New job
        </span>
        <Link
          href="/"
          className="font-mono text-[10px] tracking-[0.18em] text-ink-muted hover:text-ink uppercase transition-colors"
        >
          ← workspace
        </Link>
      </div>

      <JobForm />
    </div>
  );
}
