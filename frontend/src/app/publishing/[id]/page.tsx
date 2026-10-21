"use client";

import { use, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { useApproveSource, useApproveUpload, usePublishing, useReviewPublishing } from "@/hooks/usePublishing";
import { usePublishingEvents } from "@/hooks/usePublishingEvents";
import { useYouTubeAuthStatus, useConnectYouTube } from "@/hooks/useYouTube";
import { ApiError } from "@/lib/api";
import { pathToStaticUrl } from "@/lib/utils";
import type { DiscoveryRecommendation, EvalReport, PublishingJob } from "@/types/api";

const STAGES = [
  "discovering", "waiting_for_source_approval", "waiting_for_context_review", "generating", "scoring",
  "evaluating", "waiting_for_upload_approval", "uploading", "complete",
] as const;

interface Props {
  params: Promise<{ id: string }>;
}

export default function PublishingDetailPage({ params }: Props) {
  const { id } = use(params);
  usePublishingEvents(id); // live push into the query cache
  const { data: job, isLoading, error } = usePublishing(id);

  if (isLoading) {
    return (
      <div className="pt-16 flex items-center gap-3 text-ink-soft text-sm">
        <span className="w-4 h-4 rounded-full border border-ink border-t-transparent animate-spin" />
        Loading run…
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 404) {
    return <div className="pt-16 text-ink-soft">Run not found.</div>;
  }
  if (!job) return null;

  return (
    <div className="-mt-2">
      {/* Masthead */}
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <Link href="/publishing" className="hover:text-ink transition-colors">← Publishing</Link>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          {job.query || "Run"}
        </span>
        <span className="num-tabular">{job.publishing_job_id.slice(0, 8)}</span>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />

      <div className="pt-8 space-y-8">
        <StageStrip job={job} />

        {job.status === "waiting_for_source_approval" && <SourceGate id={id} job={job} />}
        {job.status === "waiting_for_context_review" && <ContextGate id={id} job={job} />}
        {job.status === "waiting_for_upload_approval" && <UploadGate id={id} job={job} />}
        {job.status === "complete" && <CompleteView job={job} />}
        {job.status === "failed" && (
          <Panel label="Failed"><p className="text-sm text-[var(--color-mark)]">{job.error}</p></Panel>
        )}
        {job.status === "cancelled" && (
          <Panel label="Cancelled"><p className="text-sm text-ink-muted">This run was cancelled.</p></Panel>
        )}
        {["discovering", "generating", "scoring", "evaluating", "revising", "uploading"].includes(job.status) && (
          <WorkingView job={job} />
        )}
      </div>
    </div>
  );
}

function StageStrip({ job }: { job: PublishingJob }) {
  const idx = STAGES.indexOf(job.status as (typeof STAGES)[number]);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] tracking-[0.14em] uppercase">
      {STAGES.map((s, i) => {
        const active = s === job.status;
        const done = idx >= 0 && i < idx;
        return (
          <span key={s} className="flex items-center gap-2">
            <span className={active ? "text-ink" : done ? "text-ink-muted" : "text-ink-soft"}>
              {s.replace(/_/g, " ")}
            </span>
            {i < STAGES.length - 1 && <span className="text-ink-soft">·</span>}
          </span>
        );
      })}
    </div>
  );
}

function WorkingView({ job }: { job: PublishingJob }) {
  return (
    <Panel label="Working">
      <div className="flex items-center gap-3 text-sm text-ink">
        <span className="w-4 h-4 rounded-full border border-ink border-t-transparent animate-spin" />
        {job.phase_detail || "The agent is working…"}
      </div>
    </Panel>
  );
}

// ─── Human decision #1 — pick a source video ───────────────────────────────────
function ContextGate({ id, job }: { id: string; job: PublishingJob }) {
  const review = useReviewPublishing(id);
  const [instructions, setInstructions] = useState("");
  const context = job.source_context;
  return (
    <div className="space-y-6">
      <Panel label="Video context">
        <div className="space-y-4 text-[13px] text-ink-muted leading-relaxed">
          <p className="text-sm text-ink font-medium">{context?.title || "Selected source video"}</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.12em]">{context?.channel_title} · {context?.published_at ? new Date(context.published_at).toLocaleDateString() : ""}</p>
          <p className="whitespace-pre-wrap">{context?.description || "No description available."}</p>
          {context?.chapters?.length ? <div><p className="kicker mb-2">Chapters</p><p>{context.chapters.map((c) => `${Math.floor(c.start_seconds / 60)}:${String(c.start_seconds % 60).padStart(2, "0")} ${c.title}`).join(" · ")}</p></div> : null}
          {context?.comments?.length ? <div><p className="kicker mb-2">Audience signals</p><p>{context.comments.slice(0, 3).map((c) => `“${c.text}”`).join("  ")}</p></div> : null}
          {context?.transcript ? <details><summary className="kicker cursor-pointer">Transcript</summary><p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap">{context.transcript}</p></details> : null}
          {context?.related_videos?.length ? <div><p className="kicker mb-2">Related material</p><div className="grid sm:grid-cols-2 gap-2">{context.related_videos.map((v) => <a key={v.video_id} href={v.url} target="_blank" rel="noreferrer" className="border border-rule-soft p-2 hover:border-ink">{v.title}</a>)}</div></div> : null}
        </div>
      </Panel>
      <Panel label="Instructions for the clips">
        <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={4} placeholder="e.g. Focus on the strongest reaction and preserve enough context for a viewer who has not seen the full video." className="w-full bg-paper border border-ink px-3 py-2 text-sm resize-none focus-ink" />
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-soft">The existing clip pipeline will render and score several options.</p>
          <Button onClick={() => review.mutate({ user_context: instructions || undefined, regenerate: true })} pending={review.isPending} pendingLabel="Starting" withArrow>Generate clips</Button>
        </div>
      </Panel>
    </div>
  );
}

function SourceGate({ id, job }: { id: string; job: PublishingJob }) {
  const approve = useApproveSource(id);
  const busy = approve.isPending;
  const recs = job.candidates ?? [];

  return (
    <Panel
      label="Approve a source video"
      right={
        <button
          onClick={() => approve.mutate({ action: "refresh" })}
          disabled={busy}
          className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-soft hover:text-ink transition-colors"
        >
          ↻ Refresh
        </button>
      }
    >
      {recs.length === 0 ? (
        <p className="text-sm text-ink-soft">
          {job.phase_detail || "No candidates. Try Refresh with a different request."}
        </p>
      ) : (
        <ul className="space-y-4">
          {recs.map((r) => (
            <CandidateCard
              key={r.video.video_id}
              rec={r}
              busy={busy}
              onApprove={() => approve.mutate({ action: "approve", video_url: r.video.url })}
            />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function CandidateCard({
  rec, busy, onApprove,
}: { rec: DiscoveryRecommendation; busy: boolean; onApprove: () => void }) {
  const v = rec.video;
  return (
    <li className="border border-rule-soft p-4 flex flex-col sm:flex-row gap-4">
      {v.thumbnail && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={v.thumbnail} alt="" className="w-40 aspect-video object-cover border border-rule-soft shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-ink font-medium leading-snug">{v.title}</p>
        <p className="mt-1 font-mono text-[10px] tracking-[0.12em] uppercase text-ink-muted">
          {v.channel} · {v.duration_label || `${Math.round(v.duration_seconds / 60)}m`} ·{" "}
          {v.view_count.toLocaleString()} views
        </p>
        <p className="mt-2 text-[13px] text-ink-muted leading-relaxed">{rec.why_selected}</p>
        <div className="mt-2 flex items-center gap-4 font-mono text-[10px] tracking-[0.12em] uppercase text-ink-soft">
          <span>Quality {rec.expected_clip_quality}</span>
          <span>Hook {rec.hook_potential}/10</span>
          <span>Relevance {rec.topic_relevance}/10</span>
        </div>
      </div>
      <div className="flex sm:flex-col items-end gap-2 shrink-0">
        <Button onClick={onApprove} pending={busy} pendingLabel="…" className="h-8 px-3">
          Approve
        </Button>
        <a
          href={v.url} target="_blank" rel="noreferrer"
          className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-soft hover:text-ink transition-colors"
        >
          Preview ↗
        </a>
      </div>
    </li>
  );
}

// ─── Human decision #2 — approve the upload ────────────────────────────────────
function UploadGate({ id, job }: { id: string; job: PublishingJob }) {
  const approve = useApproveUpload(id);
  const review = useReviewPublishing(id);
  const { data: ytAuth } = useYouTubeAuthStatus();
  const connectYT = useConnectYouTube();
  const busy = approve.isPending;
  const clip = job.selected_clip;
  const connected = ytAuth?.connected ?? false;
  const generated = job.generated_clips ?? (clip ? [clip] : []);

  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(clip?.title ?? "");
  const [description, setDescription] = useState(clip?.summary ?? "");
  const [reviewNotes, setReviewNotes] = useState("");

  const videoUrl = pathToStaticUrl(clip?.path);

  return (
    <div className="space-y-6">
      {job.source_context && <SourceContextPanel context={job.source_context} />}
      <Panel label="Refine the angle">
        <textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} rows={3} placeholder="Adjust what the clips should emphasize, then regenerate." className="w-full bg-paper border border-ink px-3 py-2 text-sm resize-none focus-ink" />
        <div className="mt-3 flex justify-end"><Button variant="outline" onClick={() => review.mutate({ user_context: reviewNotes, regenerate: true })} pending={review.isPending} pendingLabel="Regenerating">Regenerate with instructions</Button></div>
      </Panel>
      {generated.length > 1 && (
        <Panel label="Choose a Short">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {generated.map((candidate) => {
              const selected = candidate.clip_id === job.selected_clip_id;
              const url = pathToStaticUrl(candidate.path);
              return (
                <div key={candidate.clip_id} className={`border p-3 ${selected ? "border-ink" : "border-rule-soft"}`}>
                  {url && <video src={url} controls className="w-full aspect-[9/16] max-h-64 bg-black" />}
                  <p className="mt-2 text-sm text-ink">{candidate.title || candidate.clip_id}</p>
                  <p className="mt-1 font-mono text-[10px] text-ink-soft">Hook {candidate.hook_score.toFixed(1)}</p>
                  <Button variant={selected ? "solid" : "outline"} className="mt-3 h-8 px-3" disabled={selected || approve.isPending} onClick={() => approve.mutate({ action: "select_clip", clip_id: candidate.clip_id })}>
                    {selected ? "Selected" : "Select"}
                  </Button>
                </div>
              );
            })}
          </div>
        </Panel>
      )}
      <Panel label="Selected clip" right={
        job.eval_report ? <EvalBadge report={job.eval_report} /> : undefined
      }>
        <div className="flex flex-col md:flex-row gap-6">
          {videoUrl && (
            <video src={videoUrl} controls className="w-full md:w-64 aspect-[9/16] bg-black border border-ink shrink-0" />
          )}
          <div className="flex-1 min-w-0 space-y-3">
            {editing ? (
              <>
                <input
                  value={title} onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-paper border border-ink px-3 py-2 text-sm focus-ink" placeholder="Title"
                />
                <textarea
                  value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
                  className="w-full bg-paper border border-ink px-3 py-2 text-sm resize-none focus-ink" placeholder="Description"
                />
                <div className="flex gap-2">
                  <Button
                    className="h-8 px-3"
                    pending={busy}
                    onClick={() =>
                      approve.mutate(
                        { action: "edit_metadata", metadata: { title, description } },
                        { onSuccess: () => setEditing(false) },
                      )
                    }
                  >
                    Save
                  </Button>
                  <Button variant="outline" className="h-8 px-3" onClick={() => setEditing(false)}>Cancel</Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-ink font-medium">{clip?.title || "(untitled)"}</p>
                <p className="text-[13px] text-ink-muted leading-relaxed">{clip?.summary}</p>
                {clip?.hashtags && clip.hashtags.length > 0 && (
                  <p className="font-mono text-[11px] text-ink-soft">
                    {clip.hashtags.map((h) => `#${h}`).join("  ")}
                  </p>
                )}
                <button
                  onClick={() => { setTitle(clip?.title ?? ""); setDescription(clip?.summary ?? ""); setEditing(true); }}
                  className="font-mono text-[10px] tracking-[0.16em] uppercase text-ink-soft hover:text-ink transition-colors"
                >
                  ✎ Edit metadata
                </button>
              </>
            )}
          </div>
        </div>
      </Panel>

      {job.eval_report && <EvalPanel report={job.eval_report} />}

      <Panel label="Publish">
        {!connected ? (
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-ink-muted">
              Connect a YouTube account before publishing.
            </p>
            <Button onClick={() => connectYT.mutate()} pending={connectYT.isPending} pendingLabel="Opening…">
              Connect YouTube
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => approve.mutate({ action: "approve" })}
              pending={busy} pendingLabel="Publishing" withArrow className="h-11 px-6"
            >
              Approve &amp; upload
            </Button>
            <Button
              variant="outline" className="h-11 px-4"
              onClick={() => approve.mutate({ action: "regenerate" })}
              disabled={busy}
            >
              Regenerate clips
            </Button>
            <Button
              variant="outline" className="h-11 px-4"
              onClick={() => approve.mutate({ action: "reject" })}
              disabled={busy}
            >
              Reject
            </Button>
            <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-soft">
              Uploads are private until your Google app is verified.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}

function SourceContextPanel({ context }: { context: NonNullable<PublishingJob["source_context"]> }) {
  return (
    <Panel label="Source context">
      <div className="space-y-3 text-[13px] text-ink-muted leading-relaxed">
        <p className="text-sm text-ink font-medium">{context.title}</p>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em]">{context.channel_title} · {context.published_at ? new Date(context.published_at).toLocaleDateString() : ""}</p>
        <p className="whitespace-pre-wrap">{context.description || "No description available."}</p>
        {context.chapters.length > 0 && <p><span className="kicker">Chapters · </span>{context.chapters.map((c) => `${Math.floor(c.start_seconds / 60)}:${String(c.start_seconds % 60).padStart(2, "0")} ${c.title}`).join(" · ")}</p>}
        {context.comments.length > 0 && <details><summary className="kicker cursor-pointer">Audience comments</summary><div className="mt-2 space-y-1">{context.comments.slice(0, 5).map((c, i) => <p key={i}>“{c.text}”</p>)}</div></details>}
        {context.transcript && <details><summary className="kicker cursor-pointer">Transcript</summary><p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap">{context.transcript}</p></details>}
        {context.related_videos.length > 0 && <div><p className="kicker mb-2">Related material</p><div className="grid sm:grid-cols-2 gap-2">{context.related_videos.map((v) => <a key={v.video_id} href={v.url} target="_blank" rel="noreferrer" className="border border-rule-soft p-2 hover:border-ink">{v.title}</a>)}</div></div>}
      </div>
    </Panel>
  );
}

function EvalBadge({ report }: { report: EvalReport }) {
  return (
    <span className={`font-mono text-[11px] tracking-[0.14em] ${report.passed ? "text-ink" : "text-[var(--color-mark)]"}`}>
      {report.overall_score}/100 {report.passed ? "· passed" : report.best_effort ? "· best-effort" : ""}
    </span>
  );
}

function EvalPanel({ report }: { report: EvalReport }) {
  return (
    <Panel label="Evaluation">
      <div className="grid sm:grid-cols-2 gap-6">
        <div>
          <p className="kicker mb-2">Strengths</p>
          <ul className="list-disc pl-4 text-[13px] text-ink-muted space-y-1">
            {report.strengths.length ? report.strengths.map((s, i) => <li key={i}>{s}</li>) : <li>—</li>}
          </ul>
        </div>
        <div>
          <p className="kicker mb-2">Weaknesses &amp; fixes</p>
          <ul className="list-disc pl-4 text-[13px] text-ink-muted space-y-1">
            {[...report.weaknesses, ...report.recommendations].length
              ? [...report.weaknesses, ...report.recommendations].map((s, i) => <li key={i}>{s}</li>)
              : <li>—</li>}
          </ul>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] tracking-[0.1em] uppercase text-ink-soft">
        {report.dimensions.map((d) => (
          <span key={d.name}>{d.name.replace(/_/g, " ")} {d.score}/10</span>
        ))}
      </div>
    </Panel>
  );
}

function CompleteView({ job }: { job: PublishingJob }) {
  return (
    <Panel label="Published">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-ink">Your Short is live on YouTube.</p>
        {job.video_url && (
          <a
            href={job.video_url} target="_blank" rel="noreferrer"
            className="font-mono text-[11px] tracking-[0.16em] uppercase text-ink hover:text-[var(--color-mark)] transition-colors"
          >
            Watch ↗
          </a>
        )}
      </div>
    </Panel>
  );
}
