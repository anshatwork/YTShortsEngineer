import { API_BASE_URL, API_HOST_URL } from "@/lib/constants";
import type {
  EditJob,
  EditJobListResponse,
  Job,
  JobListResponse,
  JobRequest,
  MusicEditRequest,
  SplitScreenEditRequest,
  TTSEditRequest,
  UploadResponse,
  YouTubeAuthStatus,
  YouTubeUploadJob,
  YouTubeUploadListResponse,
  YouTubeUploadRequest,
} from "@/types/api";

const IS_DEV = process.env.NODE_ENV !== "production";

/**
 * Typed API failure. Carries the HTTP status so callers can branch — e.g.
 * useJob refuses to retry 4xx and the job-detail page renders a
 * "not found" state on 404 instead of toasting forever.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`API ${status}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/**
 * Retrieve the current Supabase access token from the browser client.
 * Returns null when Supabase is not configured or the user is not signed in
 * (e.g. during SSR or when AUTH_DISABLED=true on the backend).
 */
async function getAccessToken(): Promise<string | null> {
  try {
    const { createClient } = await import("@/lib/supabase/client");
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  } catch {
    return null;
  }
}

/**
 * Generic fetch wrapper.
 * - Automatically attaches `Authorization: Bearer <token>` from the current
 *   Supabase session when available.
 * - Throws ApiError on non-OK responses.
 * - Logs every request as `[api] METHOD PATH -> STATUS (Xms)` in development.
 * - On 401: the browser is redirected to /login so the user can re-authenticate.
 */
async function apiFetch<T>(
  url: string,
  init?: RequestInit,
  label?: string,
): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const display = label ?? url;
  const t0 = performance.now();

  if (IS_DEV) console.info(`[api] → ${method} ${display}`);

  // Build headers: start with any caller-supplied headers, add auth on top.
  const token = await getAccessToken();
  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) baseHeaders["Authorization"] = `Bearer ${token}`;

  const headers: Record<string, string> = {
    ...baseHeaders,
    ...(init?.headers as Record<string, string> | undefined),
  };

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (err) {
    const ms = (performance.now() - t0).toFixed(0);
    console.error(`[api] ✗ ${method} ${display} — network error after ${ms}ms`, err);
    throw err;
  }

  const ms = (performance.now() - t0).toFixed(0);

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    console.error(`[api] ✗ ${method} ${display} -> ${res.status} (${ms}ms): ${text}`);

    if (res.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }

    throw new ApiError(res.status, text);
  }

  if (IS_DEV) console.info(`[api] ← ${method} ${display} -> ${res.status} (${ms}ms)`);
  return res.json() as Promise<T>;
}

// ─── Jobs ──────────────────────────────────────────────────────────────────────

export const api = {
  listJobs: (): Promise<JobListResponse> =>
    apiFetch<JobListResponse>(`${API_BASE_URL}/jobs`, undefined, "/jobs"),

  getJob: (jobId: string): Promise<Job> =>
    apiFetch<Job>(`${API_BASE_URL}/jobs/${jobId}`, undefined, `/jobs/${jobId}`),

  submitJob: (body: JobRequest): Promise<Job> =>
    apiFetch<Job>(
      `${API_BASE_URL}/jobs`,
      { method: "POST", body: JSON.stringify(body) },
      "/jobs",
    ),

  // /health lives at the host root, NOT under /api/v1.
  health: () =>
    apiFetch<{ status: string; service: string }>(
      `${API_HOST_URL}/health`,
      undefined,
      "/health",
    ),

  // ─── Edit operations ────────────────────────────────────────────────────
  submitTtsEdit: (body: TTSEditRequest): Promise<EditJob> =>
    apiFetch<EditJob>(
      `${API_BASE_URL}/edit/tts`,
      { method: "POST", body: JSON.stringify(body) },
      "/edit/tts",
    ),

  getEditJob: (editJobId: string): Promise<EditJob> =>
    apiFetch<EditJob>(
      `${API_BASE_URL}/edit/jobs/${editJobId}`,
      undefined,
      `/edit/jobs/${editJobId}`,
    ),

  listEditJobs: (params?: {
    parent_job_id?: string;
    clip_id?: string;
  }): Promise<EditJobListResponse> => {
    const qs = new URLSearchParams();
    if (params?.parent_job_id) qs.set("parent_job_id", params.parent_job_id);
    if (params?.clip_id) qs.set("clip_id", params.clip_id);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<EditJobListResponse>(
      `${API_BASE_URL}/edit/jobs${query}`,
      undefined,
      `/edit/jobs${query}`,
    );
  },

  submitMusicEdit: (body: MusicEditRequest): Promise<EditJob> =>
    apiFetch<EditJob>(
      `${API_BASE_URL}/edit/add-music`,
      { method: "POST", body: JSON.stringify(body) },
      "/edit/add-music",
    ),

  submitSplitScreenEdit: (body: SplitScreenEditRequest): Promise<EditJob> =>
    apiFetch<EditJob>(
      `${API_BASE_URL}/edit/split-screen`,
      { method: "POST", body: JSON.stringify(body) },
      "/edit/split-screen",
    ),

  // ─── YouTube direct upload ──────────────────────────────────────────────
  getYouTubeAuthStatus: (): Promise<YouTubeAuthStatus> =>
    apiFetch<YouTubeAuthStatus>(
      `${API_BASE_URL}/youtube/auth/status`,
      undefined,
      "/youtube/auth/status",
    ),

  getYouTubeLoginUrl: (): Promise<{ authorization_url: string }> =>
    apiFetch<{ authorization_url: string }>(
      `${API_BASE_URL}/youtube/auth/login`,
      undefined,
      "/youtube/auth/login",
    ),

  // DELETE returns 204 No Content — don't parse a JSON body.
  disconnectYouTube: async (): Promise<void> => {
    const token = await getAccessToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE_URL}/youtube/auth`, {
      method: "DELETE",
      headers,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new ApiError(res.status, text);
    }
  },

  submitYouTubeUpload: (body: YouTubeUploadRequest): Promise<YouTubeUploadJob> =>
    apiFetch<YouTubeUploadJob>(
      `${API_BASE_URL}/youtube/upload`,
      { method: "POST", body: JSON.stringify(body) },
      "/youtube/upload",
    ),

  getYouTubeUpload: (uploadId: string): Promise<YouTubeUploadJob> =>
    apiFetch<YouTubeUploadJob>(
      `${API_BASE_URL}/youtube/uploads/${uploadId}`,
      undefined,
      `/youtube/uploads/${uploadId}`,
    ),

  listYouTubeUploads: (params?: {
    parent_job_id?: string;
    clip_id?: string;
  }): Promise<YouTubeUploadListResponse> => {
    const qs = new URLSearchParams();
    if (params?.parent_job_id) qs.set("parent_job_id", params.parent_job_id);
    if (params?.clip_id) qs.set("clip_id", params.clip_id);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<YouTubeUploadListResponse>(
      `${API_BASE_URL}/youtube/uploads${query}`,
      undefined,
      `/youtube/uploads${query}`,
    );
  },

  // Multipart upload — file body, not JSON.
  uploadAsset: async (file: File): Promise<UploadResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const token = await getAccessToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE_URL}/edit/uploads`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new ApiError(res.status, text);
    }
    return res.json() as Promise<UploadResponse>;
  },
};
