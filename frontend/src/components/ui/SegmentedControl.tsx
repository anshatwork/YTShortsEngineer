"use client";

import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
}

/**
 * The ink-bordered segmented toggle: a row of equal-width buttons, the active
 * one filled ink-on-paper, dividers between segments. Used for voice presets,
 * music/background source modes, split-screen audio, and thumbnail style.
 *
 * Pass `wrap` for the multi-row thumbnail-style variant and `itemClassName`
 * (e.g. `"text-[10px]"`) to tune the segment typography.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className,
  itemClassName,
  wrap = false,
}: {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  itemClassName?: string;
  wrap?: boolean;
}) {
  return (
    <div
      className={cn(
        wrap ? "flex flex-wrap border border-ink" : "flex border border-ink h-9",
        className,
      )}
    >
      {options.map((opt, i) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={cn(
            "flex-1 font-mono text-[11px] tracking-[0.12em] uppercase transition-colors focus-ink",
            wrap && "h-9 px-2",
            i > 0 && "border-l border-ink",
            value === opt.value
              ? "bg-ink text-paper"
              : "bg-paper text-ink-soft hover:text-ink",
            itemClassName,
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
