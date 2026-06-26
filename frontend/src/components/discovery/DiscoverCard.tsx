"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import type { DiscoverVideo } from "@/types/api";

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
}

export function DiscoverCard({
  video,
  index = 0,
}: {
  video: DiscoverVideo;
  index?: number;
}) {
  const href = `/new?youtube_url=${encodeURIComponent(video.url)}`;
  const voiceoverHref = `/create/tts?youtube_url=${encodeURIComponent(video.url)}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.55, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className="group border border-ink bg-paper flex flex-col discover-card"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-paper-2 border-b border-ink overflow-hidden">
        {video.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={video.thumbnail}
            alt=""
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full bg-paper-3" />
        )}
        {/* Bottom gradient — appears on hover to seat metadata */}
        <div className="absolute inset-0 bg-gradient-to-t from-ink/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
        {video.duration_label && (
          <span className="absolute bottom-2 right-2 bg-ink/90 backdrop-blur-sm text-paper font-mono text-[10px] tracking-[0.12em] px-1.5 py-0.5">
            {video.duration_label}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-3 flex flex-col gap-2 flex-1">
        <h3
          className="font-display text-[14px] leading-snug text-ink line-clamp-2"
          title={video.title}
        >
          {video.title}
        </h3>

        <div className="flex items-center justify-between font-mono text-[10px] tracking-[0.12em] text-ink-soft uppercase border-t border-rule-soft pt-2">
          <span className="truncate pr-2" title={video.channel}>
            {video.channel}
          </span>
          <span className="shrink-0 num-tabular">{formatCount(video.view_count)} views</span>
        </div>

        <div className="mt-auto pt-1 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Link
              href={href}
              className="flex-1 h-9 flex items-center justify-center gap-2 border border-ink bg-ink text-paper font-mono text-[10px] tracking-[0.2em] uppercase hover:bg-ink-muted transition-colors group/btn"
            >
              Use this video
              <span className="transition-transform duration-200 group-hover/btn:translate-x-1">
                →
              </span>
            </Link>
            <a
              href={video.url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-9 w-9 flex items-center justify-center border border-ink font-mono text-[11px] text-ink-soft hover:text-ink hover:bg-paper-2 transition-colors"
              title="Open on YouTube"
            >
              ↗
            </a>
          </div>
          <Link
            href={voiceoverHref}
            className="h-9 flex items-center justify-center gap-2 border border-ink bg-paper text-ink font-mono text-[10px] tracking-[0.2em] uppercase hover:bg-paper-2 transition-colors group/vo"
            title="Add a TTS voiceover behind this video"
          >
            Voiceover
            <span className="transition-transform duration-200 group-hover/vo:translate-x-1">
              →
            </span>
          </Link>
        </div>
      </div>
    </motion.div>
  );
}
