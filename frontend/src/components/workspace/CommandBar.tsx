"use client";

import { useState } from "react";
import { useSubmitJob } from "@/hooks/useSubmitJob";
import { isValidYouTubeUrl } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { ClipMode, JobRequest, SubtitlePosition, SubtitleSize } from "@/types/api";

type Status = "idle" | "typing" | "invalid" | "submitting";

/**
 * The focal element of the workspace. A terminal-prompt-styled bar — paste
 * a YouTube link, hit Enter, and a job is dispatched. A second row holds
 * the most-touched options inline so the whole flow is one keystroke long.
 */
export function CommandBar() {
  const [url, setUrl] = useState("");
  const [topN, setTopN] = useState(3);
  const [clipMode, setClipMode] = useState<ClipMode>("portrait");
  const [addIntro, setAddIntro] = useState(true);
  const [addTopText, setAddTopText] = useState(false);
  const [addSubtitles, setAddSubtitles] = useState(false);
  const [subtitlePosition, setSubtitlePosition] = useState<SubtitlePosition>("bottom");
  const [subtitleSize, setSubtitleSize] = useState<SubtitleSize>("medium");

  const { mutate, isPending } = useSubmitJob();

  const status: Status = isPending
    ? "submitting"
    : url.length === 0
      ? "idle"
      : isValidYouTubeUrl(url)
        ? "typing"
        : "invalid";

  const canSubmit = status === "typing";

  const submit = () => {
    if (!canSubmit) return;
    const body: JobRequest = {
      youtube_url: url,
      top_n: topN,
      clip_mode: clipMode,
      add_subtitles: addSubtitles,
      subtitle_position: subtitlePosition,
      subtitle_size: subtitleSize,
      add_top_text: addTopText,
      add_intro: addIntro,
    };
    mutate(body);
  };

  return (
    <section className="border border-ink bg-paper">
      {/* Prompt row */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex items-stretch h-14 border-b border-rule-soft"
      >
        <div className="flex items-center pl-4 pr-3 text-ink font-mono text-[15px] select-none">
          ❯
        </div>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="paste a youtube link or video id…"
          autoComplete="off"
          spellCheck={false}
          disabled={isPending}
          className="flex-1 bg-transparent border-0 outline-none font-mono text-[14px] sm:text-[15px] text-ink placeholder:text-ink-soft py-0"
        />
        <StatusLabel status={status} />
        <button
          type="submit"
          disabled={!canSubmit}
          className={cn(
            "h-full px-4 sm:px-5 font-mono text-[11px] tracking-[0.18em] border-l border-ink transition-colors flex items-center gap-2",
            canSubmit
              ? "bg-ink text-paper hover:bg-ink-muted"
              : "bg-paper-2 text-ink-soft cursor-not-allowed"
          )}
        >
          {isPending ? "DISPATCHING…" : (
            <>
              SUBMIT <span className="opacity-70">↵</span>
            </>
          )}
        </button>
      </form>

      {/* Inline config row */}
      <div className="flex flex-wrap items-stretch divide-x divide-rule-soft text-[11px] font-mono tracking-[0.14em]">
        <Stepper
          label="TOP_N"
          value={topN}
          min={1}
          max={20}
          onChange={setTopN}
          disabled={isPending}
        />

        <Segmented
          label="FRAME"
          options={[
            { value: "portrait", label: "9:16" },
            { value: "fullscreen", label: "NATIVE" },
          ]}
          value={clipMode}
          onChange={(v) => setClipMode(v as ClipMode)}
          disabled={isPending}
        />

        <ChipToggle
          label="INTRO"
          checked={addIntro}
          onChange={setAddIntro}
          disabled={isPending}
        />
        <ChipToggle
          label="HOOK"
          checked={addTopText}
          onChange={setAddTopText}
          disabled={isPending}
        />
        <ChipToggle
          label="SUBS"
          checked={addSubtitles}
          onChange={setAddSubtitles}
          disabled={isPending}
        />

        {/* Subtitle placement/size — only relevant when captions are on */}
        {addSubtitles && (
          <>
            <Segmented
              label="POS"
              options={[
                { value: "top", label: "TOP" },
                { value: "middle", label: "MID" },
                { value: "bottom", label: "BOT" },
              ]}
              value={subtitlePosition}
              onChange={setSubtitlePosition}
              disabled={isPending}
            />
            <Segmented
              label="SIZE"
              options={[
                { value: "small", label: "S" },
                { value: "medium", label: "M" },
                { value: "large", label: "L" },
              ]}
              value={subtitleSize}
              onChange={setSubtitleSize}
              disabled={isPending}
            />
          </>
        )}
      </div>
    </section>
  );
}

function StatusLabel({ status }: { status: Status }) {
  const cfg = {
    idle:       { dot: "border border-ink-soft",        color: "text-ink-soft", label: "READY" },
    typing:     { dot: "bg-ink",                         color: "text-ink",      label: "READY ↵" },
    invalid:    { dot: "bg-[var(--color-mark)]",         color: "text-[var(--color-mark)]", label: "INVALID URL" },
    submitting: { dot: "bg-ink ink-pulse",               color: "text-ink",      label: "DISPATCHING" },
  }[status];

  return (
    <div className="hidden sm:flex items-center gap-2 px-4 font-mono text-[11px] tracking-[0.18em] border-l border-rule-soft">
      <span
        aria-hidden
        className={cn("inline-block w-[7px] h-[7px] rounded-full", cfg.dot)}
      />
      <span className={cfg.color}>{cfg.label}</span>
    </div>
  );
}

function Stepper({
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 text-ink">
      <span className="text-ink-muted">{label}</span>
      <div className="flex items-stretch border border-ink">
        <button
          type="button"
          onClick={() => onChange(Math.max(min, value - 1))}
          disabled={disabled || value <= min}
          className="w-7 h-6 leading-none hover:bg-paper-2 disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label={`${label} decrement`}
        >
          −
        </button>
        <span className="w-8 h-6 flex items-center justify-center border-x border-ink num-tabular text-ink text-[12px]">
          {String(value).padStart(2, "0")}
        </span>
        <button
          type="button"
          onClick={() => onChange(Math.min(max, value + 1))}
          disabled={disabled || value >= max}
          className="w-7 h-6 leading-none hover:bg-paper-2 disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label={`${label} increment`}
        >
          +
        </button>
      </div>
    </div>
  );
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center px-4 py-2.5 gap-3 text-ink">
      <span className="text-ink-muted">{label}</span>
      <div className="flex border border-ink">
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(o.value)}
              disabled={disabled}
              className={cn(
                "px-3 h-6 transition-colors text-[11px]",
                active ? "bg-ink text-paper" : "hover:bg-paper-2",
                disabled && "opacity-50 cursor-not-allowed",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChipToggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={cn(
        "flex items-center gap-2 px-4 py-2.5 transition-colors",
        checked ? "text-ink" : "text-ink-soft hover:text-ink",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block w-[12px] h-[12px] border border-ink",
          checked ? "bg-ink" : "bg-transparent",
        )}
      />
      {label}
    </button>
  );
}
