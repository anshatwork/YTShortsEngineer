"use client";

import { create } from "zustand";
import type { ClipResult, NodeState, PipelineNodeName, Toast } from "@/types/api";
import type { Job } from "@/types/api";
import { PIPELINE_NODES } from "@/lib/constants";

// ─── Initial node states ───────────────────────────────────────────────────────
function initialNodes(): NodeState[] {
  return PIPELINE_NODES.map((node) => ({ node, status: "idle" }));
}

// Maps backend current_node names → pipeline node display names
const NODE_NAME_MAP: Record<string, PipelineNodeName> = {
  analyze_video:  "Analyzing",
  clipping_logic: "Scoring",
  content_gen:    "Analyzing",
  subtitles:      "Rendering",
  top_text:       "Rendering",
  intro_attach:   "Rendering",
  download:       "Downloading",
  transcribe:     "Transcribing",
  done:           "Done",
};

// ─── Derive node states from job status ───────────────────────────────────────
function deriveNodes(job: Job): NodeState[] {
  const nodes = initialNodes();
  if (job.status === "queued") return nodes;
  if (job.status === "failed") {
    nodes[0] = { ...nodes[0], status: "error" };
    return nodes;
  }
  if (job.status === "done") {
    return nodes.map((n) => ({ ...n, status: "done" }));
  }

  // "running": prefer the backend-reported current_node when available.
  if (job.current_node) {
    const activeNodeName =
      NODE_NAME_MAP[job.current_node] ?? (job.current_node as PipelineNodeName);
    const activeIdx = nodes.findIndex((n) => n.node === activeNodeName);
    if (activeIdx >= 0) {
      return nodes.map((n, i) => ({
        ...n,
        status: i < activeIdx ? "done" : i === activeIdx ? "running" : "idle",
      }));
    }
  }

  // Fallback: estimate stage from elapsed time (used when current_node is null)
  const elapsed = (Date.now() - new Date(job.created_at).getTime()) / 1000;
  // Rough stage boundaries in seconds: Download(20), Transcribe(60), Analyze(30), Score(10), Render(60)
  const boundaries = [20, 80, 110, 120, 180];
  let activeIdx = 0;
  for (let i = 0; i < boundaries.length; i++) {
    if (elapsed >= boundaries[i]) activeIdx = i + 1;
  }
  return nodes.map((n, i) => ({
    ...n,
    status: i < activeIdx ? "done" : i === activeIdx ? "running" : "idle",
  }));
}

// ─── Store definition ─────────────────────────────────────────────────────────

interface JobStore {
  // Active job
  jobId: string | null;
  nodes: NodeState[];
  logs: string[];
  clips: ClipResult[];

  // UI
  toasts: Toast[];

  // Actions
  setActiveJob: (jobId: string) => void;
  updateFromPoll: (job: Job) => void;
  addLog: (line: string) => void;
  addToast: (message: string, type?: Toast["type"]) => void;
  dismissToast: (id: string) => void;
  reset: () => void;
}

export const useJobStore = create<JobStore>((set) => ({
  jobId: null,
  nodes: initialNodes(),
  logs: [],
  clips: [],
  toasts: [],

  setActiveJob: (jobId) =>
    set({ jobId, nodes: initialNodes(), logs: [], clips: [] }),

  updateFromPoll: (job) =>
    set((state) => ({
      nodes: deriveNodes(job),
      clips: job.clips ?? state.clips,
      logs:
        job.error
          ? [...state.logs, `[ERROR] ${job.error}`]
          : state.logs,
    })),

  addLog: (line) =>
    set((state) => ({ logs: [...state.logs, line] })),

  addToast: (message, type = "info") =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { id: crypto.randomUUID(), message, type },
      ],
    })),

  dismissToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),

  reset: () =>
    set({ jobId: null, nodes: initialNodes(), logs: [], clips: [], toasts: [] }),
}));
