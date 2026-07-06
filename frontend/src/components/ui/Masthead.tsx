import type { ReactNode } from "react";

/**
 * The editorial masthead band that opens every page: a double hairline rule,
 * a three-column meta row (breadcrumb · cursive title · meta), and an ink rule
 * beneath — both rules animating in with the staggered `rule-in` entrance.
 *
 * Extracted from the verbatim markup duplicated across the job-detail and
 * clip-edit pages so the band stays pixel-identical everywhere.
 */
export function Masthead({
  left,
  title,
  right,
}: {
  left: ReactNode;
  title: ReactNode;
  right: ReactNode;
}) {
  return (
    <div>
      <div className="rule-double rule-in" />
      <div className="flex items-center justify-between py-2.5">
        <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
          {left}
        </div>
        <span className="script text-[20px] tracking-normal normal-case text-ink leading-none">
          {title}
        </span>
        <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted num-tabular">
          {right}
        </div>
      </div>
      <div className="rule-ink rule-in" style={{ animationDelay: "120ms" }} />
    </div>
  );
}
