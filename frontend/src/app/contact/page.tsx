import type { Metadata } from "next";
import { ContactHero } from "@/components/contact/ContactHero";
import { Bio } from "@/components/contact/Bio";
import { ContactLinks } from "@/components/contact/ContactLinks";
import { ContactForm } from "@/components/contact/ContactForm";
import { Reveal } from "@/components/landing/Reveal";

export const metadata: Metadata = {
  title: "Contact · YT Shorts Engineer",
  description:
    "Get in touch with Ansh Chawla, Software Engineer 1 at Adobe, about the Shorts Engineer, agentic media tooling, or anything else.",
};

export default function ContactPage() {
  return (
    <div className="-mt-2 pb-8">
      <ContactHero />

      <div className="mt-12 grid lg:grid-cols-[1fr_1fr] gap-x-14 gap-y-12 items-start">
        {/* Left — bio + direct lines */}
        <div>
          <Bio />
          <ContactLinks />
        </div>

        {/* Right — compose form */}
        <Reveal delay={0.1}>
          <div className="lg:sticky lg:top-16">
            <p className="kicker mb-3">Send a note</p>
            <ContactForm />
          </div>
        </Reveal>
      </div>
    </div>
  );
}
