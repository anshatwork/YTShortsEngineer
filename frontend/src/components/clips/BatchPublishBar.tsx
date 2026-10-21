"use client";

import { useState } from "react";
import { Upload } from "lucide-react";
import type { ClipResult, PrivacyStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import { BatchPublishDialog } from "./BatchPublishDialog";

interface Props {
  jobId: string;
  selectedClips: ClipResult[];
  uploadableCount: number;
  allSelected: boolean;
  onSelectAll: () => void;
  onClear: () => void;
}

const PRIVACY_OPTIONS: { value: PrivacyStatus; label: string }[] = [
  { value: "private", label: "PRIVATE" },
  { value: "unlisted", label: "UNLISTED" },
  { value: "public", label: "PUBLIC" },
];

/**
 * Batch-upload control strip above the clip rail: pick clips, choose a shared
 * privacy, and publish them all to YouTube in one action. (Fire-and-forget
 * auto-upload of *every* clip is chosen before the run, on the job form.)
 */
export function BatchPublishBar({
  jobId,
  selectedClips,
  uploadableCount,
  allSelected,
  onSelectAll,
  onClear,
}: Props) {
  const [privacy, setPrivacy] = useState<PrivacyStatus>("private");
  const [open, setOpen] = useState(false);

  const count = selectedClips.length;
  const canPublish = count > 0;

  return (
    <div className="mb-4 border border-ink bg-paper">
      {/* Row 1 — selection + privacy + publish */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink num-tabular">
          {String(count).padStart(2, "0")} selected
        </span>

        <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] uppercase">
          <button
            type="button"
            onClick={onSelectAll}
            disabled={allSelected}
            className="text-ink-soft hover:text-ink disabled:opacity-30 disabled:pointer-events-none transition-colors"
          >
            Select all ({uploadableCount})
          </button>
          <span aria-hidden className="text-ink-soft">/</span>
          <button
            type="button"
            onClick={onClear}
            disabled={count === 0}
            className="text-ink-soft hover:text-ink disabled:opacity-30 disabled:pointer-events-none transition-colors"
          >
            Clear
          </button>
        </div>

        <div className="flex-1" />

        {/* Shared privacy for the batch */}
        <label className="flex items-center gap-2 font-mono text-[10px] tracking-[0.16em] uppercase text-ink-muted">
          Privacy
          <select
            value={privacy}
            onChange={(e) => setPrivacy(e.target.value as PrivacyStatus)}
            className="h-8 px-2 border border-ink bg-paper text-ink font-mono text-[10px] tracking-[0.16em] uppercase focus:outline-none focus:bg-paper-2"
          >
            {PRIVACY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => setOpen(true)}
          disabled={!canPublish}
          className={cn(
            "h-8 px-4 flex items-center gap-2 border border-ink font-mono text-[10px] tracking-[0.18em] uppercase transition-colors",
            canPublish
              ? "bg-ink text-paper hover:bg-paper hover:text-ink"
              : "bg-paper text-ink-soft opacity-50 cursor-not-allowed",
          )}
        >
          <Upload size={12} strokeWidth={1.5} />
          <span>Publish{count > 0 ? ` ${count}` : ""}</span>
        </button>
      </div>

      {/* Row 2 — hint */}
      <div className="border-t border-rule-soft px-3 py-2">
        <span className="font-mono text-[10px] leading-relaxed tracking-[0.04em] text-ink-soft">
          Select clips to publish them together with their generated titles,
          descriptions &amp; tags. Want every clip uploaded automatically? Turn on
          Auto-publish when you start the job.
        </span>
      </div>

      {open && (
        <BatchPublishDialog
          jobId={jobId}
          clips={selectedClips}
          privacy={privacy}
          autoStart={false}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}
