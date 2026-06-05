// ─── API Types ────────────────────────────────────────────────────────────────
// Mirrors agents/long_to_shorts/api/models.py exactly

export type JobStatus = "queued" | "running" | "done" | "failed";
export type ClipMode = "portrait" | "fullscreen";

export interface ClipResult {
  clip_id: string;
  path: string | null;
  timestamp_range: [number, number];
  hook_score: number;
  title: string | null;
  summary: string | null;
  hook_text: string | null;
  hashtags: string[] | null;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  created_at: string; // ISO 8601
  updated_at: string;
  clips: ClipResult[] | null;
  error: string | null;
  current_node: string | null; // backend-reported pipeline stage while running
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
}

export interface JobRequest {
  youtube_url?: string;
  video_path?: string;    // local-upload mode: path returned by POST /edit/uploads
  srt_path?: string;      // local-upload mode: optional .srt path (else Whisper)
  transcript?: string;
  top_n: number;          // 1–20, default 3
  add_subtitles: boolean; // default false
  add_top_text: boolean;  // default false
  add_intro: boolean;     // default true
  clip_mode: ClipMode;    // default "portrait"
}

// ─── Edit API Types ───────────────────────────────────────────────────────────
// Mirrors the Phase-1+ /api/v1/edit/* surface in the FastAPI backend.

export type EditOperation = "tts" | "music" | "split_screen";
export type VoicePreset = "default" | "finance" | "finance_energetic";

// Mirrors core/audio_themes.py::AudioTheme
export type AudioTheme =
  | "eerie"
  | "mysterious"
  | "peaceful"
  | "energetic"
  | "professional"
  | "contemplative"
  | "inspiring"
  | "neutral";

export const AUDIO_THEMES: AudioTheme[] = [
  "professional",
  "energetic",
  "peaceful",
  "inspiring",
  "contemplative",
  "mysterious",
  "eerie",
  "neutral",
];

export interface TTSEditRequest {
  text: string;
  voice_preset: VoicePreset;
  parent_job_id?: string;
  attach_to_clip_id?: string;
}

export interface MusicEditRequest {
  parent_job_id: string;
  clip_id: string;
  theme?: AudioTheme;
  music_path?: string;
  music_upload_id?: string;
  volume_db?: number;
}

export type SplitScreenAudioMode = "fetched_video" | "bg_video";

export interface SplitScreenEditRequest {
  parent_job_id: string;
  clip_id: string;
  background_default?: boolean;
  background_path?: string;
  background_url?: string;
  background_upload_id?: string;
  audio_mode?: SplitScreenAudioMode;
}

export interface UploadResponse {
  upload_id: string;
  path: string;
  size: number;
}

export interface EditJob {
  edit_job_id: string;
  operation: EditOperation;
  parent_job_id: string | null;
  clip_id: string | null;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  output_path: string | null;
  output_url: string | null;
  error: string | null;
}

export interface EditJobListResponse {
  edit_jobs: EditJob[];
  total: number;
}

// ─── YouTube direct-upload Types ──────────────────────────────────────────────
// Mirrors the /api/v1/youtube/* surface in the FastAPI backend.

export type PrivacyStatus = "private" | "unlisted" | "public";

export interface YouTubeAuthStatus {
  connected: boolean;
  channel_id: string | null;
  channel_title: string | null;
}

export interface YouTubeUploadRequest {
  parent_job_id: string;
  clip_id: string;
  title: string;
  description?: string;
  tags?: string[];
  privacy_status?: PrivacyStatus; // default "private"
  category_id?: string; // default "22"
  made_for_kids?: boolean;
}

export interface YouTubeUploadJob {
  upload_id: string;
  parent_job_id: string | null;
  clip_id: string | null;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  title: string | null;
  privacy_status: PrivacyStatus | null;
  video_id: string | null;
  video_url: string | null;
  error: string | null;
}

export interface YouTubeUploadListResponse {
  uploads: YouTubeUploadJob[];
  total: number;
}

// ─── UI-only Types (not from API) ─────────────────────────────────────────────

export type PipelineNodeName =
  | "Downloading"
  | "Transcribing"
  | "Analyzing"
  | "Scoring"
  | "Rendering"
  | "Done";

export type NodeStatus = "idle" | "running" | "done" | "error";

export interface NodeState {
  node: PipelineNodeName;
  status: NodeStatus;
}

export interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}
