/**
 * lib/debugLog.ts
 * ~~~~~~~~~~~~~~~~
 * A tiny in-memory ring buffer of client-side diagnostic events (API calls,
 * SSE activity, React-Query failures, error-boundary catches). It is the
 * frontend analog of the backend's per-job log file: a single correlated,
 * copy-pasteable trace you can hand over when debugging.
 *
 * - Always records (not dev-gated) so production issues are reproducible.
 * - Also mirrors to the browser console in development.
 * - `getDebugDump()` returns the buffer as newline-joined text ready to paste.
 */

export type DebugLevel = "info" | "warn" | "error";

export interface DebugEntry {
  ts: string; // ISO timestamp
  level: DebugLevel;
  scope: string; // e.g. "api" | "sse" | "query" | "boundary"
  message: string;
  data?: unknown;
}

const MAX_ENTRIES = 500;
const IS_DEV = process.env.NODE_ENV !== "production";

const buffer: DebugEntry[] = [];

/** Append a diagnostic entry to the ring buffer (and console in dev). */
export function pushDebug(
  level: DebugLevel,
  scope: string,
  message: string,
  data?: unknown,
): void {
  const entry: DebugEntry = {
    ts: new Date().toISOString(),
    level,
    scope,
    message,
    data,
  };

  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) buffer.splice(0, buffer.length - MAX_ENTRIES);

  if (IS_DEV && typeof console !== "undefined") {
    const fn =
      level === "error" ? console.error : level === "warn" ? console.warn : console.info;
    fn(`[${scope}] ${message}`, data ?? "");
  }
}

/** Return the current buffer (most recent last). */
export function getDebugEntries(): readonly DebugEntry[] {
  return buffer;
}

/** Serialize the buffer to a single paste-ready string. */
export function getDebugDump(): string {
  if (buffer.length === 0) return "(debug log empty)";
  return buffer
    .map((e) => {
      const base = `${e.ts} ${e.level.toUpperCase().padEnd(5)} [${e.scope}] ${e.message}`;
      if (e.data === undefined) return base;
      let dataStr: string;
      try {
        dataStr =
          typeof e.data === "string" ? e.data : JSON.stringify(e.data, replacer, 2);
      } catch {
        dataStr = String(e.data);
      }
      return `${base}\n  ${dataStr.replace(/\n/g, "\n  ")}`;
    })
    .join("\n");
}

/** Clear the buffer (e.g. when starting a fresh job). */
export function clearDebug(): void {
  buffer.length = 0;
}

/** JSON.stringify replacer that unwraps Error objects (message + stack). */
function replacer(_key: string, value: unknown): unknown {
  if (value instanceof Error) {
    return { name: value.name, message: value.message, stack: value.stack };
  }
  return value;
}
