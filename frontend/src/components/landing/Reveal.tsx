"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Scroll-triggered entrance. Wraps server-rendered content in a client motion
 * boundary so the editorial sections fade + rise into view once, matching the
 * paper's quiet, deliberate cadence (same easing as the `.rule-in` keyframe).
 */
export function Reveal({
  children,
  delay = 0,
  y = 18,
  className,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
