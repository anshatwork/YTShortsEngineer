// ─── API Types ────────────────────────────────────────────────────────────────
// Mirrors agents/long_to_shorts/api/models.py exactly

export type JobStatus = "queued" | "running" | "done" | "failed";
export type ClipMode = "portrait" | "fullscreen";
export type SubtitlePosition = "top" | "middle" | "bottom";
export type SubtitleSize = "small" | "medium" | "large";
export type ThumbnailStyle = "auto" | "bubble" | "highlight" | "box" | "plain";
export type ThumbnailFont = "auto" | "impact" | "arial" | "condensed";

export interface ClipResult {
  clip_id: string;
  path: string | null;
  timestamp_range: [number, number];
  hook_score: number;
  title: string | null;
  summary: string | null;
  hook_text: string | null;
  hashtags: string[] | null;
  thumbnail_path: string | null; // AI-directed thumbnail (ThumbnailNode); convert with pathToStaticUrl
}

export interface Job {
  job_id: string;
  status: JobStatus;
  created_at: string; // ISO 8601
  updated_at: string;
  clips: ClipResult[] | null;
  error: string | null;
  current_node: string | null; // backend-reported pipeline stage while running
  video_title: string | null; // human-readable name (source video title, or derived label)
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
}

export interface JobRequest {
  youtube_url?: string;
  video_path?: string;     // local-upload mode: path returned by POST /edit/uploads
  video_filename?: string; // local-upload mode: original filename, used to label the job
  srt_path?: string;       // local-upload mode: optional .srt path (else Whisper)
  transcript?: string;
  top_n: number;          // 1–20, default 3
  add_subtitles: boolean; // default false
  subtitle_position?: SubtitlePosition; // default "bottom" (only used when add_subtitles)
  subtitle_size?: SubtitleSize;         // default "medium" (only used when add_subtitles)
  add_top_text: boolean;  // default false
  add_thumbnail: boolean; // default false — AI-directed thumbnail per clip
  thumbnail_style?: ThumbnailStyle; // default "auto" — caption style for all clips
  add_intro: boolean;     // default true
  clip_mode: ClipMode;    // default "portrait"
  user_context?: string;  // optional creator guidance steering LLM titles/hooks/thumbnails
}

// ─── Discover API Types ───────────────────────────────────────────────────────
// Mirrors the /api/v1/discover/* surface in models.py

export type DiscoverOrder = "relevance" | "viewCount" | "date";

export interface DiscoverRequest {
  topics: string[];
  custom_queries: string[];
  conversational_query?: string; // natural-language request; LLM-interpreted server-side
  days_ago: number; // 1–365, default 7
  max_results_per_query: number; // 1–10, default 5
  order: DiscoverOrder; // default "relevance"
  min_duration_minutes?: number; // lower duration bound (floored at 20 server-side)
  max_duration_minutes?: number; // upper duration bound; omit for no cap
}

/** What the LLM inferred from a conversational_query (echoed back for the UI). */
export interface DiscoverInterpretation {
  topics: string[];
  custom_queries: string[];
  order: DiscoverOrder;
  days_ago: number | null; // null = no recency constraint (evergreen/historical)
  min_duration_minutes: number | null;
  max_duration_minutes: number | null;
  summary: string;
}

export interface DiscoverVideo {
  video_id: string;
  title: string;
  description: string;
  thumbnail: string;
  url: string;
  channel: string;
  published_at: string;
  duration_seconds: number;
  duration_label: string;
  view_count: number;
  like_count: number;
  comment_count: number;
}

export interface DiscoverResponse {
  videos: DiscoverVideo[];
  queries_used: string[];
  total: number;
  interpretation?: DiscoverInterpretation | null;
}

// Personalized trending suggestion (GET /discover/suggestions).
export interface DiscoverSuggestion {
  video: DiscoverVideo;
  reason: string;
  discovered_at: string;
}

export interface DiscoverSuggestionsResponse {
  suggestions: DiscoverSuggestion[];
  new_count: number;
  generated_at: string;
  last_seen_at?: string | null;
  interest_summary?: string | null;
}

// ─── Edit API Types ───────────────────────────────────────────────────────────
// Mirrors the Phase-1+ /api/v1/edit/* surface in the FastAPI backend.

export type EditOperation = "tts" | "music" | "split_screen" | "thumbnail";
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
  // Lay the narration over a video (the video's own audio is dropped). At most
  // one of these — mutually exclusive with attach_to_clip_id.
  video_upload_id?: string;
  video_url?: string;
}

// POST /edit/tts/script — expand a summary into a narration script (synchronous).
export interface TtsScriptRequest {
  summary: string;
  target_seconds?: number;
  tone?: string;
}

export interface TtsScriptResponse {
  script: string;
}

export interface MusicEditRequest {
  parent_job_id: string;
  clip_id: string;
  theme?: AudioTheme;
  music_path?: string;
  music_upload_id?: string;
  volume_db?: number;
  music_start_sec?: number;
}

// ─── Cached music library (GET/POST /api/v1/music/*) ──────────────────────────
// A self-refreshing cache of free trending music (Jamendo). `path` is fed back
// as MusicEditRequest.music_path to use a track; `preview_url` streams it inline.
export interface MusicTrack {
  track_id: string;
  title: string;
  theme: string;
  source: string;
  duration?: number | null;
  attribution?: string | null;
  preview_url: string;
  path: string;
  deletable?: boolean;
}

export interface MusicTrackListResponse {
  tracks: MusicTrack[];
  total: number;
}

export interface MusicThemeCount {
  theme: string;
  count: number;
}

export interface MusicThemesResponse {
  themes: MusicThemeCount[];
}

export interface MusicRefreshResponse {
  queued: boolean;
  detail: string;
}

// Free-catalog song search (GET /music/search). preview_url is the provider's
// remote URL; pass download_url back to POST /music/songs to cache it.
export interface MusicSearchResult {
  source: string; // jamendo | pixabay | freesound | youtube
  source_id: string; // for youtube this is the video id
  title: string;
  artist?: string | null;
  duration?: number | null;
  attribution?: string | null;
  preview_url: string;
  download_url: string;
  already_cached: boolean;
  thumbnail?: string | null;
  // Set for copyrighted sources (youtube): Content-ID warning to surface in the UI.
  copyright_warning?: string | null;
}

// What the LLM understood from a conversational "vibe" music search.
export interface MusicInterpretation {
  query: string;
  order: string;
  summary: string;
}

export interface MusicSearchResponse {
  results: MusicSearchResult[];
  total: number;
  interpretation?: MusicInterpretation | null;
  query_used?: string | null;
}

export interface AddSongRequest {
  source: string;
  source_id: string;
  title: string;
  download_url: string;
  duration?: number | null;
  attribution?: string | null;
}

export interface ThumbnailEditRequest {
  parent_job_id: string;
  clip_id: string;
  headline?: string;      // override the LLM headline (≤30 chars)
  accent_color?: string;  // override accent/fill color, hex (e.g. "#FF2D55")
  text_color?: string;    // override text color, hex (else auto-contrast)
  style?: ThumbnailStyle; // "auto" (LLM picks) or bubble/highlight/box/plain
  font?: ThumbnailFont;   // "auto" (Impact) or impact/arial/condensed
}

export type SplitScreenAudioMode = "fetched_video" | "bg_video";

export interface SplitScreenEditRequest {
  // Foreground (top half): either an existing clip (parent_job_id + clip_id)
  // or a standalone uploaded video (foreground_upload_id).
  parent_job_id?: string;
  clip_id?: string;
  foreground_upload_id?: string;
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
