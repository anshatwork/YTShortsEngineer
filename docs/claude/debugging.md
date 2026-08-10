# Debugging Guide

Common failures and how to diagnose them. Start with logs: the central config
(`core/logging_config`) writes `logs/app.log` (rotating) and, per job,
`logs/jobs/<job_id>.log`. Every line carries `[job:<id>|<node>]`, so grep by job id.

## First moves

```bash
# Follow a specific job end-to-end
tail -f logs/jobs/<job_id>.log

# Everything, filtered to a node
grep "|clipping_logic]" logs/app.log

# Raise verbosity (per-logger override supported: LOG_LEVEL_agents=DEBUG etc.)
LOG_LEVEL=DEBUG python agents/long_to_shorts/api/server.py --reload
```

Job status + `current_node` + `error` live on the job row (`GET /api/v1/jobs/{id}`) and stream on
`GET /api/v1/jobs/{id}/events`. `current_step` in the returned state tells you which node last ran.

---

## Pipeline / graph

**"analysis_failed — captions cover a longer/different cut."** `analyze_video` produced no
in-duration segments. Usually a transcript/video mismatch (captions for a different cut) or a
transcript shorter than `MIN_SEGMENT_SECONDS` (45s). Check the source has a real transcript; try
`--fullscreen`/local path via `run_clipping_workflow.py` to isolate.

**Empty/placeholder titles & hashtags.** `content_gen`'s LLM was unavailable or errored. Check for
a `get_llm` fallback warning in the log. Verify `LLM_PROVIDER` + key; if `ENABLE_LLM_FALLBACK`,
confirm Ollama is reachable (`OLLAMA_BASE_URL/api/tags`).

**A clip has no thumbnail / no subtitles / no music but the job succeeded.** By design: optional
nodes **degrade, don't fail**. Grep the node stage (`|thumbnail]`, `|subtitles]`) for the per-clip
warning and its cause. The job is still "done" with the previous `path`.

**Wrong node ran / didn't run.** Optional nodes check `state` flag then env var. If the API set
`ADD_X` env but a concurrent job cleared it, you can get cross-talk (see `design-decisions.md`
ADR-007). Prefer per-job state flags; check the runner's Phase 2 env-setting for the job.

---

## Caching (the sneaky one)

**Stale output after a prompt/encoder change.** The CAS serves a cached artifact because the cache
key didn't change. Fix: **bump the `version`** for that operation —
`cached_llm_text(operation=…, version=N+1)` for prompts, or the `_CLIP_EXTRACT_CACHE_VERSION` /
similar constant for renders. Symptom: your prompt edit has no effect on output.

**Force a clean recompute.** Set `CACHE_ENABLED=0` for a run, or delete the CAS
(`cache/` dir for local blob store; the sqlite index). Confirm backends via `BLOB_STORE_BACKEND` /
`CACHE_INDEX_BACKEND`.

**Cache "hit" but file missing.** Local blob store shards under `cache/cas/<hash[:2]>/`. If the dir
was cleaned but the index wasn't, `materialize_blob` recomputes; if the index is Supabase and the
blob is local (or vice-versa), you can get a mismatch — keep index/blob backends consistent per
environment.

---

## FFmpeg

**Subtitles don't burn / "no usable font".** libass can't find the font. On Windows set
`SUBTITLES_FONT_NAME=Arial` (must be installed); in Docker use DejaVu (the image bakes it). The
node scans stderr for `fontselect`/`glyph`/`no usable font` and treats it as failure — grep for it.

**Subtitle path errors on Windows.** ASS burn-in must run with `cwd=srt_dir` and a bare filename to
avoid `C:\`/`:` escaping. If you added a new FFmpeg call that burns ASS, copy `subtitles_node`'s
pattern.

**`ffprobe not found`.** `imageio_ffmpeg` bundles ffmpeg but **not** ffprobe. Use `ffmpeg.probe`
(ffmpeg-python), or ensure a real ffprobe is on PATH. `_resolve_ffmpeg_bin` handles the ffmpeg
binary; probing is separate.

**Output plays audio but black video (or vice-versa).** Check the `-map`/stream handling — e.g.
`audio_mixer` copies video (`-c:v copy`) and remaps audio; a source with no audio needs the
video-only path (see `intro_attach`'s branch). Probe the input streams first.

**Green/garbled or won't play in browser.** Missing `-pix_fmt yuv420p` or `-movflags +faststart`.
All final outputs must set both.

---

## Video acquisition

**YouTube 403 / "Sign in to confirm you're not a bot".** yt-dlp is being blocked. The downloader
already spoofs UA/referer and uses `player_client=["android","web"]` with retries; see
`YOUTUBE_403_FIX.md`. Persistent blocks usually need a cookies file or a different IP.

**No transcript.** `youtube-transcript-api` raises on disabled/missing captions. The runner falls
back to Whisper (slow, CPU). For long videos watch `WHISPER_MAX_MINUTES`. Supplying an SRT
(`srt_path`) skips both.

---

## API / auth / execution

**401 on every request.** Missing/invalid Supabase JWT. In dev set `AUTH_DISABLED=1` (fixed dev
user). **Never** set it with `ENVIRONMENT=production` — the app raises `RuntimeError` at startup by
design.

**SSE connects but no events.** The event bus binds the loop at startup (`bind_loop`); if a worker
thread published before startup, events drop. Also EventSource can't send headers — the token goes
in the query string (`?token=<jwt>`). No replay buffer: reconnect re-syncs via snapshot.

**Job stuck in `queued`.** The task queue didn't pick it up. `WORKER_THREADS` may be saturated by
other long jobs (default 2), or the queue singleton was shut down (common in tests sharing
`TestClient`s — see `testing.md`). Restart clears in-memory queue state (in-flight jobs are lost —
ADR-002).

**402 unexpectedly.** Credit shortfall or monthly quota hit. Check `GET /api/v1/usage`. Meters
**fail open** on store errors, so a 402 means a real shortfall, not an outage. Verify
`CREDITS_ENABLED`/`QUOTA_ENABLED` and the plan grants.

**Double charge / double grant.** Idempotency key regression. Grants/refunds key on
`refund:{job_id}` / period-scoped keys; a duplicate webhook must be a no-op. Check the ledger for
duplicate `idempotency_key` rows.

**MCP sign-in fails at discovery.** RFC 9728 protected-resource metadata must be served at the
origin root — `app.py` extends the app router with the provider's routes. If you changed the mount,
re-check that. Requires `SUPABASE_URL` + `MCP_PUBLIC_URL` (and raises in production if unset).

---

## Config

**`Settings` warning at startup / a var seems ignored.** `Settings` construction is warn-only on
failure, and many modules read `os.getenv` directly. A var read via `settings` won't pick up an
`os.environ` change made after import, and vice-versa. Check *how* the specific module reads it
(ADR-006). `HUGGINGFACE_API_KEY` is the one field with no default.

---

## Quick reproduction harnesses

- **Whole pipeline, local, no API:** `python run_clipping_workflow.py <path-or-url>
  [--subtitles --top-text --no-intro --fullscreen]`. Fastest way to repro a node bug.
- **API locally:** `python agents/long_to_shorts/api/server.py --reload` (or `start.bat` for API +
  frontend). `/docs` is available when `ENVIRONMENT` ≠ production.
- **One node in isolation:** call `_<name>_impl(state)` from a REPL/test with a minimal state dict.
