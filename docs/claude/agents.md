# Agents & Graph Nodes

Per-node reference for the **active** Long-to-Shorts pipeline
(`agents/long_to_shorts/`), plus a short guide to the legacy graph nodes. For state fields
see `state.md`; for prompt text see `prompts.md`; for the tools these nodes call see `tools.md`.

## Conventions shared by all long_to_shorts nodes

- Each node is a plain function `def <name>_node(state) -> dict` that returns a **partial**
  state dict LangGraph merges in. Most delegate to a private `_<name>_impl`.
- Every node body runs inside `node_stage(state, "<name>")` (`_logging_utils.py`), which logs
  START/END/FAILED with the `[job:<id>|<node>]` context, updates `job_store.current_node`, and
  records `stage_store` start/complete/fail. Store writes are best-effort; the node re-raises
  real exceptions after logging.
- Optional post-processing nodes read their flag from **state first, env var second**
  (`add_subtitles` → `ADD_SUBTITLES`, etc.). They **never raise on a per-clip failure** — they
  log and leave `clip["path"]` unchanged, so the pipeline always produces output.
- LLM access is always `from tools.llm import get_llm`. LLM completions are memoized via
  `cached_llm_text(operation, version, invoke)`.

---

## 1. analyze_video_node

- **Reads:** `transcript`, `top_n_clips` (default 5), `source_video_path`, `timed_transcript`,
  `user_context`, `job_id`.
- **Writes:** `analyzed_segments` (List[ClipObject] stubs, sorted by `hook_score` desc),
  `current_step`, `error`.
- **LLM:** `llm.parse(user, HookSegment, system=_ANALYSIS_SYSTEM)`, cached
  `operation="analyze_llm" version=3`. Chunks from `timed_transcript` (real timestamps) else
  char-offset.
- **Tools:** `ffmpeg.probe` for source duration (best-effort).
- **Failure modes:** empty transcript → `analysis_failed`; per-chunk parse errors skipped; no
  segments → synthetic evenly-spaced fallback; out-of-duration segments clamped/dropped; nothing
  survives → `analysis_failed`. `MIN_SEGMENT_SECONDS = 45`.
- **Upstream:** START. **Downstream:** clipping_logic.

## 2. clipping_logic_node

- **Reads:** `analyzed_segments`, `source_video_path`, `clip_mode` (portrait|fullscreen),
  `job_id`/`run_id`. **No LLM.**
- **Writes:** `generated_clips` (with `path` set), `clips_dir` (per-run
  `OUTPUT_DIR/jobs/<run_id>/clips`), `run_id`, `current_step`, `error`.
- **FFmpeg:** ffmpeg-python + raw subprocess. Portrait = scale+pad 9:16; fullscreen = native.
  Long clips use split-encode-concat (parallel part encode → concat demuxer copy); short clips
  single-pass. Rendered clips cached in CAS (`materialize_blob("clip_extract", version=2)`).
- **Tunables:** `CLIP_WORKER_THREADS`, `FFMPEG_THREADS_PER_PART`, `CLIP_PART_TARGET_SECONDS`,
  `CLIP_MAX_PARTS`, `CLIP_X264_PRESET`, `CLIP_FORCE_FPS`, `OUTPUT_DIR`.
- **Failure modes:** unreadable source → `clipping_failed` (with ffmpeg stderr); per-clip errors
  captured into `clip["error"]`, `path` stays None, never raises; all-failed → `clipping_failed`.
- **Upstream:** analyze_video. **Downstream:** content_gen. Sets the `clips_dir` all later nodes use.

## 3. content_gen_node (Reduce)

- **Reads:** `generated_clips`, `transcript`, `timed_transcript`, `user_context`, `job_id`.
- **Writes:** per clip `title`, `summary`, `hook_text`, `hashtags`, `music_theme`, and (if a
  track is found) `music_path`/`music_title`/`music_source`/`music_attribution`; plus
  `current_step`.
- **LLM:** `llm.parse(user, ClipMeta, system=_CONTENT_SYSTEM_FILLED)`, cached
  `operation="content_llm" version=3`.
- **Tools:** music recommendation via `_recommend_music → tools.assets.retrieve` (best-effort,
  gated by `RECOMMEND_MUSIC`). No FFmpeg.
- **Failure modes:** LLM unavailable → placeholder metadata; per-clip exception → placeholder
  title/summary + empty hashtags; music failure ignored.
- **Upstream:** clipping_logic. **Downstream:** thumbnail.

## 4. thumbnail_node (optional, default OFF)

- **Reads:** `add_thumbnail`/`ADD_THUMBNAIL`, `generated_clips`, `clips_dir`, `thumbnail_style`,
  `user_context`.
- **Writes:** per clip `thumbnail_path` (leaves `path` untouched); `current_step`.
- **Delegates** entirely to `tools.thumbnail.generate_thumbnail` (LLM `ThumbnailSpec` + ffmpeg
  frame grab + Pillow compositing). 4 worker threads.
- **Failure modes:** disabled → skipped; per-clip failure → clip returned without a thumbnail.

## 5. top_text_node (optional, default OFF)

- **Reads:** `add_top_text`/`ADD_TOP_TEXT`, `generated_clips` (`hook_text` → fallback `title`),
  `clips_dir`. **No LLM.**
- **Writes:** per clip `path` → `<clip_id>_noted.mp4`; `current_step`.
- **FFmpeg:** ffmpeg-python — word-wrapped `drawtext` over a `drawbox` strip near the top;
  re-encode libx264/aac. Env: `TOP_TEXT_FONT_SIZE`, `TOP_TEXT_COLOR`, `TOP_TEXT_BG_ALPHA`, etc.
- **Failure modes:** no text or missing path → skipped unchanged; ffmpeg error → original kept.

## 6. subtitles_node (optional, default OFF)

- **Reads:** `add_subtitles`/`ADD_SUBTITLES`, `generated_clips`, `subtitle_position`,
  `subtitle_size`, `timed_transcript`, `clips_dir`. **No LLM.**
- **Writes:** per clip `path` → `<clip_id>_sub.mp4`; `current_step`.
- **Subtitle source:** (1) slice `timed_transcript` per clip (no Whisper); (2) **Whisper
  fallback** (`whisper.load_model(SUBTITLES_WHISPER_MODEL)`), limited to 2 workers (CPU-heavy).
- **FFmpeg:** generates an ASS file (per-word karaoke highlight, real PlayRes), burns via raw
  subprocess `-vf ass=<file>` run with `cwd=srt_dir` + bare filename (Windows escaping).
- **Failure modes:** missing path / no segments → skipped; ffmpeg non-zero or missing/undersized
  output → RuntimeError (caught, clip unchanged); libass font failure detected in stderr. Needs
  `SUBTITLES_FONT_NAME` present on the box (Arial on Windows; DejaVu in Docker).

## 7. intro_attach_node (optional, default ON)

- **Reads:** `add_intro`/`ADD_INTRO` (disabled only by `0/false/no`), `generated_clips`
  (`title` → fallback "Now Playing"), `clips_dir`. **No LLM.**
- **Writes:** per clip `path` → `<clip_id>_final.mp4`; `current_step`.
- **FFmpeg:** ffmpeg-python — renders a title card (lavfi color + drawtext + silent audio), then
  joins intro+main with `xfade` video and `acrossfade` audio. Env: `INTRO_DURATION_SECS`,
  `INTRO_BG_COLOR`, `INTRO_FONT_SIZE`, `INTRO_TRANSITION_SECS`.
- **Failure modes:** disabled → skipped; missing path → skipped; ffmpeg error → original kept.

## 8. music_attach_node (optional, default OFF, runs last)

- **Reads:** `add_music`/`ADD_MUSIC`, `generated_clips` (needs `music_path` from content_gen),
  `music_volume_db` (default −18.0), `clips_dir`. **No LLM.**
- **Writes:** per clip `path` → `<clip_id>_music.mp4`; `current_step`.
- **Delegates** to `tools.video_editing.audio_mixer.mix_background_music` (loop/trim/mix under
  existing audio, copy video). 4 workers.
- **Failure modes:** disabled / no `music_path` / missing path → passthrough unchanged; mix error
  → original kept.

---

## Helper modules

- **`_llm_cache.py`** — `cached_llm_text(prompt, *, operation, version, invoke)`; memoizes raw
  completion text in CAS keyed on active model id + prompt hash, namespaced by operation/version.
- **`_logging_utils.py`** — `node_stage(state, name)` context manager (the node instrumentation).
- **`_prompt_utils.py`** — `guidance_block(user_context)`; folds creator guidance into the *user*
  prompt (keeps cache keys correct; byte-identical when empty).
- **`srt_utils.py`** — `parse_srt(path)` → `timed_transcript`-shaped dicts (BOM/CRLF/comma-ms tolerant).
- **`fetch_trending_videos.py` / `trending_crawler.py`** — discovery pool warming (static query
  bank by default; optional legacy LLM query path that `eval`s output — avoid).
- **`hitl_select_video_node.py`** — CLI-only blocking `input()` selection; not in the compiled graph.

---

## Edit workers (not graph nodes)

`api/edit_runner.py` runs per-clip edits off the task queue, reusing pipeline building blocks:
`run_tts_edit_job` (TTS narration; can attach with a crossfade intro), `run_music_edit_job`,
`run_split_screen_edit_job` (`compose_video`), `run_thumbnail_edit_job` (`generate_thumbnail`),
and the synchronous `generate_tts_script`. Each maps to a `/api/v1/edit/*` endpoint, meters a
credit op, and refunds on failure (idempotent). See `tools.md` and the API section of
`architecture.md`.

---

## Legacy graph nodes (avoid extending)

`agents/node.py` holds the modular graph's node functions (parse_scripts, generate_queries,
fetch_assets, generate_script, select_video, select_audio, render_video, review, upload_to_yt);
`render_video`/`upload_to_yt` are stubs. Class agents in `agents/*.py` (TrendDiscovery,
ContentSourcing, ScriptGeneration, VoiceSynthesis, VideoAssembly, QualityControl, Publisher)
belong to `workflows/graph.py`. Only `ScriptParserAgent` and `VideoSelectionAgent` are reused by
the modular graph. Prefer building on `long_to_shorts` — see `design-decisions.md` ADR-001.
