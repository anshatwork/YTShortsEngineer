---
name: video-pipeline
description: End-to-end guide to the Long-to-Shorts video pipeline — how a video becomes clips, node order, artifact flow, and how to add a new processing stage. Use when working on clip generation or adding a pipeline step.
---

# Video Pipeline

The active pipeline (`agents/long_to_shorts/graph.py`). Full detail: `docs/claude/agents.md`,
`state.md`. This skill orients you and covers adding a stage.

## Flow

```
input (YouTube URL / local path) ──runner Phase 1──► source_video_path + transcript/timed_transcript
        │
        ▼  long_to_shorts_app.invoke(initial_state)
analyze_video   → analyzed_segments (hook-scored)
clipping_logic  → generated_clips[].path + clips_dir   (FFmpeg 9:16 extraction, CAS-cached)
content_gen     → title/summary/hook_text/hashtags/music_theme(+music_path)
thumbnail?      → thumbnail_path
top_text?       → path _noted.mp4
subtitles?      → path _sub.mp4
intro_attach    → path _final.mp4     (ON by default)
music_attach?   → path _music.mp4
        │
        ▼  runner Phase 5
generated_clips → ClipResult[] persisted; served under /static
```

`?` = optional (state flag → env var). Each optional node **rewrites `clip["path"]`** to a new
suffixed file, so **order matters** — the `path` chain is `_noted → _sub → _final → _music`.

## Artifact locations
- Clips: `clips_dir = OUTPUT_DIR/jobs/<run_id>/clips` (set by clipping_logic). Write nowhere else.
- Edits: `OUTPUT_DIR/edits/<edit_job_id>/`. Served at `/static`.
- Music cache: `assets/audio_cache/<theme>/`, served at `/library`.

## Adding a new processing stage
1. Create `agents/long_to_shorts/<stage>_node.py`: `def <stage>_node(state) -> dict` delegating to
   `_<stage>_impl`, wrapped in `node_stage`.
2. Read the enable flag state-first/env-second; if disabled return `{"current_step": "<stage>_skipped"}`.
3. Read the current `clip["path"]` and `clips_dir`; write a new suffixed file; update `clip["path"]`.
   **On per-clip failure, log and leave `path` unchanged** (degrade-not-fail).
4. Register the node and insert the edge in `graph.py` at the right point in the `path` chain.
5. Add any new state keys to `agents/state.py` (owner comment) and, if user-facing, to
   `api/models.py::JobRequest` + the runner's `initial_state` + `db/mappers.py`.
6. Cache expensive work in the CAS with a versioned operation.
7. Tests: unit `_impl` (mock FFmpeg/LLM) + the degrade path; optionally an ffmpeg integration test
   on `assets/ailover.mp4`.
8. Update `docs/claude/agents.md` + `state.md`.

## Repro
`python run_clipping_workflow.py <path-or-url> --subtitles --top-text` — runs the graph without the
API. See the `ffmpeg-best-practices` and `langgraph-review` skills.
