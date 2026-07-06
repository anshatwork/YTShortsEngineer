"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Show a spinner + `pendingLabel` and keep the solid style (reads as "working"). */
  pending?: boolean;
  pendingLabel?: ReactNode;
  /** Append the trailing `→` that nudges right on hover (the CTA affordance). */
  withArrow?: boolean;
  variant?: "solid" | "outline";
}

/**
 * The recurring arrow-CTA button: solid ink on paper with a hover shift, a
 * spinner-driven pending state, and a unified disabled treatment
 * (`bg-paper-2 text-ink-soft`). Consolidates the button markup copy-pasted
 * across the Edit Suite forms and the job-detail actions.
 *
 * Height/width come from `className` (defaults to `h-9 px-4`), so callers can
 * pass e.g. `className="h-12 px-6"` and tailwind-merge overrides the default.
 */
export function Button({
  pending = false,
  pendingLabel,
  withArrow = false,
  variant = "solid",
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  // During `pending` the button keeps its active (solid) look so the spinner
  // stays legible; only a true `disabled` (not busy) shows the muted style.
  const showDisabled = disabled && !pending;

  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={cn(
        "group inline-flex items-center justify-center gap-2 h-9 px-4 border border-ink font-mono text-[11px] tracking-[0.18em] uppercase transition-colors focus-ink",
        variant === "solid"
          ? showDisabled
            ? "bg-paper-2 text-ink-soft cursor-not-allowed"
            : "bg-ink text-paper hover:bg-ink-muted"
          : showDisabled
            ? "text-ink-soft cursor-not-allowed"
            : "text-ink hover:bg-paper-2/40",
        className,
      )}
    >
      {pending ? (
        <>
          <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
          {pendingLabel ?? children}
        </>
      ) : (
        <>
          {children}
          {withArrow && (
            <span className="transition-transform duration-200 group-hover:translate-x-0.5">
              →
            </span>
          )}
        </>
      )}
    </button>
  );
}
