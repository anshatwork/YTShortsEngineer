import Link from "next/link";
import { Reveal } from "./Reveal";

export function LandingFooter() {
  return (
    <footer className="pt-24 pb-4">
      <Reveal>
        {/* Closing CTA band */}
        <div className="relative border border-ink bg-ink text-paper overflow-hidden">
          <div
            aria-hidden
            className="absolute inset-0 opacity-[0.06]"
            style={{
              backgroundImage:
                "repeating-linear-gradient(45deg, transparent 0 11px, rgba(251,250,245,0.5) 11px 12px)",
            }}
          />
          <div className="relative px-6 sm:px-10 py-12 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-8">
            <div>
              <p className="kicker !text-paper/60 mb-3">Ready when you are</p>
              <h2 className="font-display text-[clamp(1.75rem,4vw,3rem)] leading-[0.95]">
                Give it one link.
                <br />
                <span className="display-italic">Get back a feed.</span>
              </h2>
            </div>
            <Link
              href="/workspace"
              className="group inline-flex items-center gap-3 h-12 px-6 bg-paper text-ink font-mono text-[11px] tracking-[0.2em] uppercase hover:bg-paper-2 transition-colors shrink-0"
            >
              Open the workspace
              <span aria-hidden className="transition-transform group-hover:translate-x-1">
                →
              </span>
            </Link>
          </div>
        </div>
      </Reveal>

      {/* Byline */}
      <div className="mt-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t border-rule-soft pt-5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
        <span>
          Built by{" "}
          <Link href="/contact" className="text-ink ink-underline-hover hover:text-ink-muted transition-colors">
            Ansh Chawla
          </Link>{" "}
          · Software Engineer 1, Adobe
        </span>
        <span className="flex items-center gap-4">
          <Link href="/contact" className="hover:text-ink transition-colors">
            Contact
          </Link>
          <span aria-hidden className="text-ink-soft">·</span>
          <span className="num-tabular">© MMXXVI</span>
        </span>
      </div>
    </footer>
  );
}
