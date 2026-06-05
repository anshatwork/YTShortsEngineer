"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useJobStore } from "@/store/jobStore";
import { cn } from "@/lib/utils";

const KICKER: Record<"success" | "error" | "info", string> = {
  success: "Posted",
  error:   "Spiked",
  info:    "Note",
};

export function ToastContainer() {
  const { toasts, dismissToast } = useJobStore();

  useEffect(() => {
    if (toasts.length === 0) return;
    const last = toasts[toasts.length - 1];
    const timer = setTimeout(() => dismissToast(last.id), 5000);
    return () => clearTimeout(timer);
  }, [toasts, dismissToast]);

  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 max-w-sm w-full pointer-events-none">
      <AnimatePresence>
        {toasts.map((toast) => {
          const isError = toast.type === "error";
          return (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className={cn(
                "pointer-events-auto bg-paper border-l-2 border-ink pl-4 pr-5 py-3 shadow-none",
                isError && "border-l-[var(--color-mark)]"
              )}
            >
              <div className="flex items-baseline justify-between gap-4">
                <span className={cn(
                  "kicker",
                  isError && "text-[var(--color-mark)]"
                )}>
                  {KICKER[toast.type]}
                </span>
                <button
                  type="button"
                  onClick={() => dismissToast(toast.id)}
                  className="text-ink-soft hover:text-ink transition-colors text-xs leading-none"
                  aria-label="Dismiss"
                >
                  ✕
                </button>
              </div>
              <p className="mt-1 display-italic text-[15px] text-ink leading-snug">
                {toast.message}
              </p>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
