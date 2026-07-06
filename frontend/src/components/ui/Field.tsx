"use client";

import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * The paper & ink form fields: an ink-bordered input/textarea with mono type,
 * soft placeholder, and the shared keyboard focus ring (`focus-ink`) — the a11y
 * treatment the old inline `outline-none` inputs were missing.
 *
 * `fieldClass` is exported for the remaining native controls (selects, number
 * inputs) so they pick up the same border + focus styling without a wrapper.
 */
export const fieldClass =
  "border border-ink bg-paper font-mono text-ink placeholder:text-ink-soft focus-ink";

export function TextArea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={cn(fieldClass, "w-full px-3 py-2 text-[13px] resize-none", className)}
    />
  );
}

export function TextInput({
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={cn(fieldClass, "w-full px-3 py-2 text-[11px]", className)}
    />
  );
}
