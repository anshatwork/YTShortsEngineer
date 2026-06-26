import type { Metadata } from "next";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { ClipShowcase } from "@/components/landing/ClipShowcase";
import { AboutSection } from "@/components/landing/AboutSection";
import { LandingFooter } from "@/components/landing/LandingFooter";

export const metadata: Metadata = {
  title: "YT Shorts Engineer · Long-form video, reframed into shorts",
  description:
    "Paste a YouTube link and an autonomous LangGraph pipeline finds the best moments, reframes them to 9:16, writes the hooks, voices them, and burns the captions — a feed of publish-ready verticals from one source.",
};

export default function LandingPage() {
  return (
    <div className="-mt-2">
      <Hero />
      <HowItWorks />
      <ClipShowcase />
      <AboutSection />
      <LandingFooter />
    </div>
  );
}
