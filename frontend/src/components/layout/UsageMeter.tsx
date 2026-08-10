"use client";

import { useUsage } from "@/hooks/useUsage";

/**
 * Compact navbar meter showing what the user has left this period. Two gates can
 * apply (mirrors the backend): the per-operation credit meter (primary) and the
 * monthly job-cap quota (secondary). We surface whichever is enforced, credits
 * first; when neither is enforced (dev / unmetered) we say so instead of showing
 * a misleading number. Renders nothing until the first fetch resolves.
 */
export function UsageMeter() {
  const { data } = useUsage();
  if (!data) return null;

  const { credits } = data;
  let label: string;
  let value: string;
  let low = false;

  if (credits.enforced) {
    label = "CREDITS";
    value = `${credits.remaining}/${credits.granted}`;
    low = credits.granted > 0 && credits.remaining <= credits.granted * 0.1;
  } else if (data.enforced && data.limit != null && data.remaining != null) {
    label = "JOBS";
    value = `${data.remaining}/${data.limit}`;
    low = data.remaining <= 0;
  } else {
    label = data.plan.toUpperCase();
    value = "UNMETERED";
  }

  const title = [
    `Plan: ${data.plan}`,
    credits.enforced
      ? `Credits: ${credits.remaining} left of ${credits.granted} (${credits.used} used)`
      : "Credits: not enforced",
    data.enforced && data.limit != null
      ? `Jobs this month: ${data.used}/${data.limit}`
      : "Job cap: not enforced",
  ].join("\n");

  return (
    <span
      title={title}
      className="hidden sm:inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.15em] text-ink-muted"
    >
      <span className="text-ink-soft">{label}</span>
      <span className={low ? "text-[var(--color-mark)] font-bold" : "text-ink"}>
        {value}
      </span>
    </span>
  );
}
