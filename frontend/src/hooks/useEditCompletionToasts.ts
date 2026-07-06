"use client";

import { useEffect, useRef } from "react";
import { useJobStore } from "@/store/jobStore";
import type { EditJob, EditOperation } from "@/types/api";

const EDIT_OP_LABELS: Record<EditOperation, string> = {
  tts: "voiceover",
  music: "music",
  split_screen: "split-screen",
  thumbnail: "thumbnail",
};

/**
 * Fires a toast when an edit job transitions into a terminal state.
 *
 * Mirrors the dedupe-by-ref pattern in `usePipelinePoller`: we remember the
 * last status seen per edit_job_id and only toast on a queued/running → done
 * (or → failed) transition, so re-renders and continued polling don't spam.
 *
 * The first observation of a job is recorded silently — we don't toast for
 * jobs that were already terminal when the component mounted (e.g. old history).
 */
export function useEditCompletionToasts(editJobs: EditJob[] | undefined) {
  const addToast = useJobStore((s) => s.addToast);
  const seenRef = useRef<Map<string, EditJob["status"]>>(new Map());

  useEffect(() => {
    if (!editJobs) return;
    const seen = seenRef.current;

    for (const job of editJobs) {
      const prev = seen.get(job.edit_job_id);
      seen.set(job.edit_job_id, job.status);

      // No transition to act on if we've never seen it (record silently) or
      // the status hasn't changed.
      if (prev === undefined || prev === job.status) continue;

      const wasInFlight = prev === "queued" || prev === "running";
      if (!wasInFlight) continue;

      const label = EDIT_OP_LABELS[job.operation] ?? job.operation;
      if (job.status === "done") {
        addToast(`Edit complete — ${label}`, "success");
      } else if (job.status === "failed") {
        addToast(job.error ?? `Edit failed — ${label}`, "error");
      }
    }
  }, [editJobs, addToast]);
}
