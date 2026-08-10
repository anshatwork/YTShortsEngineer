"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { Reveal } from "@/components/landing/Reveal";
import { usePublishingList, useStartPublishing } from "@/hooks/usePublishing";
import { formatDate } from "@/lib/utils";
import type { PublishingStatus } from "@/types/api";

const STATUS_LABEL: Record<PublishingStatus, string> = {
  discovering: "Discovering",
  waiting_for_source_approval: "Needs source approval",
  waiting_for_context_review: "Needs context review",
  generating: "Generating clips",
  scoring: "Scoring",
  evaluating: "Evaluating",
  revising: "Revising",
  waiting_for_upload_approval: "Needs upload approval",
  uploading: "Uploading",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function PublishingPage() {
  const router = useRouter();
  const { data, isLoading } = usePublishingList();
  const start = useStartPublishing();

  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState(5);
  const [clips, setClips] = useState(3);
  const [addThumbnail, setAddThumbnail] = useState(true);

  const onStart = () => {
    if (!query.trim()) return;
    start.mutate(
      {
        query: query.trim(),
        top_n_candidates: candidates,
        top_n_clips: clips,
        add_thumbnail: addThumbnail,
      },
      { onSuccess: (job) => router.push(`/publishing/${job.publishing_job_id}`) },
    );
  };

  const jobs = data?.jobs ?? [];

  return (
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span className="hidden sm:inline">Autonomous · Publishing</span>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          The Publisher
        </span>
        <span className="num-tabular">
          {data ? `${String(data.total).padStart(2, "0")} runs` : "—"}
        </span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      <Reveal>
        <div className="pt-8 pb-8 border-b border-rule-soft">
          <p className="kicker mb-3">Two decisions, fully autonomous otherwise</p>
          <h1 className="font-display fraunces-soft text-ink leading-[0.92] tracking-[-0.01em] text-[clamp(2rem,5vw,3.5rem)]">
            Publish{" "}
            <span className="display-italic text-[var(--color-mark)]">today&apos;s</span> clips.
          </h1>
          <p className="mt-4 max-w-xl text-ink-muted text-sm leading-relaxed">
            Describe what you want. The agent searches YouTube, ranks candidates, and asks you to
            approve one. It then generates, scores and evaluates clips automatically, and asks you to
            approve the final upload. That&apos;s it.
          </p>
        </div>
      </Reveal>

      {/* Start form */}
      <Reveal>
        <div className="pt-8">
          <Panel label="New publishing run">
            <div className="space-y-4">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={2}
                placeholder="e.g. today's best AI agent explainers under an hour"
                className="w-full bg-paper border border-ink px-4 py-3 text-sm text-ink placeholder:text-ink-soft focus-ink resize-none"
              />
              <div className="flex flex-wrap items-end gap-6">
                <label className="flex flex-col gap-1">
                  <span className="kicker">Candidates</span>
                  <input
                    type="number" min={1} max={20} value={candidates}
                    onChange={(e) => setCandidates(Number(e.target.value))}
                    className="w-20 bg-paper border border-ink px-2 py-1.5 text-sm num-tabular focus-ink"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="kicker">Clips</span>
                  <input
                    type="number" min={1} max={20} value={clips}
                    onChange={(e) => setClips(Number(e.target.value))}
                    className="w-20 bg-paper border border-ink px-2 py-1.5 text-sm num-tabular focus-ink"
                  />
                </label>
                <label className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-ink-muted">
                  <input
                    type="checkbox" checked={addThumbnail}
                    onChange={(e) => setAddThumbnail(e.target.checked)}
                  />
                  Thumbnails
                </label>
                <div className="flex-1" />
                <Button
                  onClick={onStart}
                  disabled={!query.trim()}
                  pending={start.isPending}
                  pendingLabel="Starting"
                  withArrow
                  className="h-11 px-6"
                >
                  Start run
                </Button>
              </div>
            </div>
          </Panel>
        </div>
      </Reveal>

      {/* Recent runs */}
      <Reveal>
        <div className="pt-10">
          <p className="kicker mb-4">Recent runs</p>
          {isLoading ? (
            <div className="flex items-center gap-3 text-ink-soft text-sm">
              <span className="w-4 h-4 rounded-full border border-ink border-t-transparent animate-spin" />
              Loading…
            </div>
          ) : jobs.length === 0 ? (
            <p className="text-ink-soft text-sm">No runs yet.</p>
          ) : (
            <ul className="divide-y divide-rule-soft border-y border-rule-soft">
              {jobs.map((j) => (
                <li key={j.publishing_job_id}>
                  <Link
                    href={`/publishing/${j.publishing_job_id}`}
                    className="flex items-center justify-between gap-4 py-3 hover:bg-paper-2/40 px-1 transition-colors"
                  >
                    <span className="truncate text-sm text-ink">{j.query || j.publishing_job_id}</span>
                    <span className="flex items-center gap-4 shrink-0">
                      <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-muted">
                        {STATUS_LABEL[j.status]}
                      </span>
                      <span className="font-mono text-[10px] text-ink-soft num-tabular hidden sm:inline">
                        {formatDate(j.created_at)}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Reveal>
    </div>
  );
}
