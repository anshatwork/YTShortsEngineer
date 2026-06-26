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
// Slow safety-net poll used while SSE is the primary update channel. If the
// event stream drops entirely, state still advances at this cadence.
export const POLL_INTERVAL_FALLBACK = 30_000;

// Real-time updates via Server-Sent Events. Set NEXT_PUBLIC_SSE_ENABLED=0 to
// fall back to pure polling (instant rollback, no code change).
export const SSE_ENABLED = !["0", "false", "off"].includes(
  (process.env.NEXT_PUBLIC_SSE_ENABLED ?? "1").toLowerCase(),
);
