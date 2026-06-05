import type { PipelineNodeName } from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Backend host without the /api/v1 prefix — used by /health which lives at the root.
export const API_HOST_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");

// Ordered pipeline stages shown in the tracker
export const PIPELINE_NODES: PipelineNodeName[] = [
  "Downloading",
  "Transcribing",
  "Analyzing",
  "Scoring",
  "Rendering",
  "Done",
];

// Polling intervals (ms)
export const POLL_INTERVAL_RUNNING = 3_000;
export const POLL_INTERVAL_LIST    = 10_000;
