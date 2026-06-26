import { Play } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A stylized 9:16 "specimen well" — the marketing stand-in for a real
 * `ClipCard` thumbnail. Pure CSS: a warm ink→sepia duotone, a faint grain
 * overlay, a top vignette, plate/duration chrome, a play glyph, and a
 * Hormozi-style burned caption. No images, no network, no API.
 */

const TONES = [
  "linear-gradient(157deg, #14110B 0%, #2E2417 50%, #6E2A1A 100%)",
  "linear-gradient(157deg, #1B1710 0%, #46371F 58%, #8A6A38 100%)",
  "linear-gradient(157deg, #131316 0%, #2C2D33 55%, #565A64 100%)",
  "linear-gradient(157deg, #21130E 0%, #5A2418 55%, #9A4A2A 100%)",
  "linear-gradient(157deg, #11140F 0%, #25342A 55%, #3E5A45 100%)",
  "linear-gradient(157deg, #1A140C 0%, #3C2F1D 55%, #6E5A2A 100%)",
];

// Inline fractal-noise grain so the duotone doesn't read as a flat fill.
const NOISE =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>";

interface ClipPlateProps {
  tone?: number;
  plate: string;
  duration: string;
  caption?: string;
  highlight?: string;
  big?: boolean;
  className?: string;
}

export function ClipPlate({
  tone = 0,
  plate,
  duration,
  caption,
  highlight,
  big = false,
  className,
}: ClipPlateProps) {
  return (
    <div
      className={cn(
        "group relative w-full aspect-[9/16] overflow-hidden border border-ink bg-ink select-none",
        className,
      )}
    >
      {/* Duotone field */}
      <div
        className="absolute inset-0"
        style={{ backgroundImage: TONES[tone % TONES.length] }}
      />
      {/* Grain */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.14] mix-blend-overlay"
        style={{ backgroundImage: `url("${NOISE}")`, backgroundSize: "150px 150px" }}
      />
      {/* Top-down vignette to seat the chrome */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(125% 85% at 50% 12%, transparent 42%, rgba(20,17,11,0.55) 100%)",
        }}
      />

      {/* Plate number */}
      <span className="absolute top-2 left-2 font-mono text-[10px] tracking-[0.18em] uppercase text-paper/75">
        plate&nbsp;{plate}
      </span>
      {/* Duration chip */}
      <span className="absolute top-2 right-2 px-1.5 py-0.5 border border-paper/35 font-mono text-[10px] tracking-[0.06em] text-paper/85 num-tabular">
        {duration}
      </span>

      {/* Play glyph */}
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className={cn(
            "flex items-center justify-center rounded-full border border-paper/55 bg-paper/10 text-paper backdrop-blur-[1px] transition-all duration-300 group-hover:bg-paper group-hover:text-ink",
            big ? "w-16 h-16" : "w-11 h-11",
          )}
        >
          <Play
            size={big ? 22 : 15}
            strokeWidth={1.2}
            className="translate-x-[1px]"
          />
        </span>
      </div>

      {/* Burned caption — Hormozi-style, one word knocked out in the mark hue */}
      {caption && (
        <div className="absolute inset-x-0 bottom-0 px-3 pb-4 flex justify-center text-center">
          <p
            className={cn(
              "font-display font-black uppercase leading-[1.05] tracking-tight text-paper",
              big ? "text-[clamp(1rem,2.2vw,1.6rem)]" : "text-[12px]",
            )}
            style={{ textShadow: "0 1px 0 rgba(0,0,0,0.55)" }}
          >
            {caption}{" "}
            {highlight && (
              <span className="box-decoration-clone bg-[var(--color-mark)] px-1 text-paper">
                {highlight}
              </span>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
