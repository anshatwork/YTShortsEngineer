"use client";

import type { ClipMode, SubtitlePosition, SubtitleSize, ThumbnailStyle } from "@/types/api";
import { cn } from "@/lib/utils";

interface ConfigPanelProps {
  topN: number; setTopN: (v: number) => void;
  clipMode: ClipMode; setClipMode: (v: ClipMode) => void;
  addSubtitles: boolean; setAddSubtitles: (v: boolean) => void;
  subtitlePosition: SubtitlePosition; setSubtitlePosition: (v: SubtitlePosition) => void;
  subtitleSize: SubtitleSize; setSubtitleSize: (v: SubtitleSize) => void;
  addTopText: boolean; setAddTopText: (v: boolean) => void;
  addThumbnail: boolean; setAddThumbnail: (v: boolean) => void;
  thumbnailStyle: ThumbnailStyle; setThumbnailStyle: (v: ThumbnailStyle) => void;
  addIntro: boolean; setAddIntro: (v: boolean) => void;
  disabled?: boolean;
}

/**
 * Dense two-column option panel for the full-form route. Left column holds
 * sliders and segmented controls; right column holds the three feature
 * toggles. Visually tight, mono labels, no editorial copy.
 */
export function ConfigPanel({
  topN, setTopN,
  clipMode, setClipMode,
  addSubtitles, setAddSubtitles,
  subtitlePosition, setSubtitlePosition,
  subtitleSize, setSubtitleSize,
  addTopText, setAddTopText,
  addThumbnail, setAddThumbnail,
  thumbnailStyle, setThumbnailStyle,
  addIntro, setAddIntro,
  disabled,
}: ConfigPanelProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 border border-ink bg-paper">
      {/* LEFT — numeric & framing */}
      <div className="p-4 sm:p-5 sm:border-r border-ink space-y-5">
        {/* TOP_N */}
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <span className="font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase">
              Top_n clips
            </span>
            <span className="font-mono text-[20px] text-ink num-tabular leading-none">
              {String(topN).padStart(2, "0")}
            </span>
          </div>
          <input
            type="range"
            min={1} max={20} step={1}
            value={topN}
            disabled={disabled}
            onChange={(e) => setTopN(Number(e.target.value))}
            className="w-full disabled:opacity-50"
          />
          <div className="flex justify-between font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase mt-1.5">
            <span>01</span><span>20</span>
          </div>
        </div>

        {/* FRAME */}
        <div>
          <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-2">
            Frame
          </span>
          <div className="grid grid-cols-2 border border-ink">
            {([
              { value: "portrait", label: "9:16",  hint: "shorts"  },
              { value: "fullscreen", label: "NATIVE", hint: "as-shot" },
            ] as { value: ClipMode; label: string; hint: string }[]).map((opt, i) => {
              const active = clipMode === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  disabled={disabled}
                  onClick={() => setClipMode(opt.value)}
                  className={cn(
                    "px-3 py-3 flex flex-col items-start gap-1 transition-colors",
                    i === 0 && "border-r border-ink",
                    active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                  )}
                >
                  <span className="font-mono text-[12px] tracking-[0.12em]">{opt.label}</span>
                  <span
                    className={cn(
                      "font-mono text-[10px] tracking-[0.18em] uppercase",
                      active ? "text-paper/70" : "text-ink-soft",
                    )}
                  >
                    {opt.hint}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* RIGHT — feature toggles */}
      <div className="p-4 sm:p-5 space-y-1">
        <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-3">
          Stages
        </span>
        <InkSwitch
          checked={addIntro} onChange={setAddIntro}
          label="INTRO"
          hint="2-second title card with crossfade"
          disabled={disabled}
        />
        <InkSwitch
          checked={addTopText} onChange={setAddTopText}
          label="HOOK_TEXT"
          hint="Persistent overlay at top of frame"
          disabled={disabled}
        />
        <InkSwitch
          checked={addThumbnail} onChange={setAddThumbnail}
          label="THUMBNAIL"
          hint="AI-designed thumbnail per clip"
          disabled={disabled}
        />

        {/* Thumbnail caption style — only relevant when thumbnails are on */}
        {addThumbnail && (
          <div className="pl-[26px] pt-1 pb-2">
            <Segmented
              label="Style"
              value={thumbnailStyle}
              onChange={setThumbnailStyle}
              options={[
                { value: "auto", label: "AUTO" },
                { value: "bubble", label: "BUBBLE" },
                { value: "highlight", label: "HILITE" },
                { value: "box", label: "BOX" },
                { value: "plain", label: "PLAIN" },
              ]}
              disabled={disabled}
            />
          </div>
        )}
        <InkSwitch
          checked={addSubtitles} onChange={setAddSubtitles}
          label="SUBTITLES"
          hint="Burn captions in, active word highlighted"
          disabled={disabled}
        />

        {/* Subtitle styling — only relevant when captions are on */}
        {addSubtitles && (
          <div className="pl-[26px] pt-1 pb-2 space-y-3">
            <Segmented
              label="Position"
              value={subtitlePosition}
              onChange={setSubtitlePosition}
              options={[
                { value: "top", label: "TOP" },
                { value: "middle", label: "MID" },
                { value: "bottom", label: "BOT" },
              ]}
              disabled={disabled}
            />
            <Segmented
              label="Size"
              value={subtitleSize}
              onChange={setSubtitleSize}
              options={[
                { value: "small", label: "S" },
                { value: "medium", label: "M" },
                { value: "large", label: "L" },
              ]}
              disabled={disabled}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Compact 3-up segmented control matching the FRAME selector styling.
 * Generic over the option value so it stays type-safe for each setter.
 */
function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  disabled?: boolean;
}) {
  return (
    <div>
      <span className="block font-mono text-[10px] tracking-[0.2em] text-ink-muted uppercase mb-1.5">
        {label}
      </span>
      <div
        className="grid border border-ink"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map((opt, i) => {
          const active = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(opt.value)}
              className={cn(
                "px-2 py-2 font-mono text-[11px] tracking-[0.12em] transition-colors",
                i !== options.length - 1 && "border-r border-ink",
                active ? "bg-ink text-paper" : "bg-transparent text-ink hover:bg-paper-2",
                disabled && "opacity-50 cursor-not-allowed",
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function InkSwitch({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "w-full grid grid-cols-[auto_1fr] gap-3 items-baseline py-2.5 text-left",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "relative mt-0.5 inline-block w-[14px] h-[14px] border border-ink transition-colors",
          checked ? "bg-ink" : "bg-transparent",
        )}
      >
        {checked && (
          <span className="absolute inset-0 flex items-center justify-center text-paper text-[10px] leading-none">
            ✓
          </span>
        )}
      </span>
      <span className="flex flex-col leading-tight">
        <span className="font-mono text-[11px] tracking-[0.18em] text-ink">
          {label}
        </span>
        <span className="text-[11px] text-ink-muted mt-0.5">
          {hint}
        </span>
      </span>
    </button>
  );
}
