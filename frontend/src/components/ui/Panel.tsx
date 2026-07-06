import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A framed content section: the `border border-ink bg-paper` card with an
 * optional `.kicker`-labelled header (and an optional right-aligned slot for a
 * badge). Reproduces the section pattern repeated ~7× in the Edit Suite and by
 * the job-detail output/log/failure panels.
 */
export function Panel({
  label,
  right,
  children,
  className,
  bodyClassName,
}: {
  label?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn("border border-ink bg-paper overflow-hidden", className)}
    >
      {label != null && (
        <div
          className={cn(
            "px-5 py-3 border-b border-ink",
            right != null && "flex items-center justify-between",
          )}
        >
          <p className="kicker">{label}</p>
          {right}
        </div>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}
