import { Reveal } from "@/components/landing/Reveal";

export function ContactHero() {
  return (
    <Reveal>
      <section>
        <div className="rule-double rule-in" />
        <div className="flex items-center justify-between py-2.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted">
          <span>Correspondence</span>
          <span className="num-tabular">No. 02</span>
        </div>
        <div className="rule-ink" />
      </section>
    </Reveal>
  );
}
