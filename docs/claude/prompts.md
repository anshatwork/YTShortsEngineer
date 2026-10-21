# Prompt Catalog

Every LLM prompt used by the Long-to-Shorts pipeline, where it lives, its variables,
expected structured output, and common failure modes. All prompts run through
`get_llm()` (`tools/llm/__init__.py`) and, where noted, are memoized by
`cached_llm_text(operation, version, ...)` (`agents/long_to_shorts/_llm_cache.py`).

**Convention:** system prompts are static module constants (sent as an Anthropic ephemeral
cache block); creator guidance is folded into the *user* prompt via
`_prompt_utils.guidance_block(user_context)` so LLM cache keys differ per guidance and stay
byte-identical when there is none. When you change a prompt's *meaning*, bump the
`version` passed to `cached_llm_text` for that operation.

---

## 1. Hook analysis — `analyze_video_node.py`

- **Purpose:** score transcript segments for scroll-stopping "hook" quality and pick the
  best 45–75s windows.
- **System:** `_ANALYSIS_SYSTEM` (module constant). Opens: *"You are a senior viral content
  strategist specialising exclusively in YouTube Shorts…"*. Contains a 1–10 HOOK SCORE
  RUBRIC, a HOOK TYPE list, and a DURATION rule (45–75s, offsets relative to the excerpt).
- **User:** `_ANALYSIS_USER` — `Transcript excerpt (starts at {offset_seconds:.1f}s into the
  video):\n"""\n{transcript_chunk}\n"""`, prepended with `guidance_block(user_context)`.
- **Output schema:** `HookSegment` (Pydantic): `start_time`, `end_time`, `hook_score` (1–10),
  `hook_type` ∈ {curiosity_gap, surprising_fact, emotional_story, controversy, humor, how_to},
  `reason`.
- **Call:** `llm.parse(user_prompt, HookSegment, system=_ANALYSIS_SYSTEM)` via
  `cached_llm_text(operation="analyze_llm", version=3)`.
- **Chunking:** from `timed_transcript` (real caption timestamps) when present, else char-offset.
- **Common failures / handling:** empty transcript → `analysis_failed`; per-chunk parse errors
  logged & skipped; no LLM segments → `_make_synthetic_segments` (evenly spaced); segments
  outside probed duration clamped/dropped; nothing survives → `analysis_failed` ("captions
  cover a longer/different cut"). `MIN_SEGMENT_SECONDS = 45.0` enforced.

---

## 2. Clip metadata & music mood — `content_gen_node.py`

- **Purpose:** write viral title, summary, hook overlay text, hashtags, and a music mood per clip.
- **System:** `_CONTENT_SYSTEM` (pre-filled once as `_CONTENT_SYSTEM_FILLED` with
  `max_title_chars=50`, `max_hook_chars=55`, mood options). Opens: *"You are an expert YouTube
  Shorts copywriter who creates content that stops the scroll."* Rules: title ≤50 chars (power
  openers, no emojis/ALL-CAPS), one-sentence summary + soft CTA, hook_text ≤55 chars, 5
  hashtags (no `#`, lowercase), mood = an `AudioTheme` value.
- **User:** `_CONTENT_USER` — `Transcript excerpt:\n"""\n{transcript_excerpt}\n"""`, prepended
  with `guidance_block(user_context)`.
- **Output schema:** `ClipMeta` (Pydantic): `title`, `summary`, `hook_text`, `hashtags:
  list[str]`, `mood: AudioTheme`.
- **Call:** `llm.parse(user_prompt, ClipMeta, system=_CONTENT_SYSTEM_FILLED)` via
  `cached_llm_text(operation="content_llm", version=3)`.
- **Common failures / handling:** LLM unavailable → placeholder metadata for all clips;
  per-clip exception → placeholder title/summary + empty hashtags. Music recommendation
  (`_recommend_music` → `tools.assets.retrieve`) is best-effort and gated by `RECOMMEND_MUSIC`.

---

## 3. Thumbnail direction — `tools/thumbnail.py`

- **Purpose:** act as a "creative director" — choose a headline, accent color, text placement,
  caption style, and a stock-image fallback query for a clip's thumbnail.
- **System:** `THUMBNAIL_SYSTEM` (module constant in `tools/thumbnail.py`).
- **Output schema:** `ThumbnailSpec` (Pydantic): `headline`, `accent_color`, `text_position`
  (top/bottom), `style` (bubble/highlight/box/plain), `search_query`.
- **Call:** `get_llm().parse(...)` via `cached_llm_text(operation="thumbnail_llm", version=2)`.
- **Common failures / handling:** any failure → `_fallback_spec` (never raises). Used only when
  `add_thumbnail` is on.

---

## 4. Discover query interpretation — `api/discover_routes.py`

- **Purpose:** turn a conversational discovery query ("find me long podcasts about AI safety")
  into structured search parameters.
- **Function:** `interpret_discover_query(...)` → `get_llm().parse(..., DiscoverInterpretation)`.
- **Output schema:** `DiscoverInterpretation` (`models.py`), doubles as the LLM `output_format`.
- **Common failures / handling:** degrades to plain keyword search on any failure.
- **Related:** `interpret_user_interests` (over the user's last 40 jobs) → `UserInterestProfile`
  for `/discover/suggestions` ranking.

---

## 5. Music query interpretation — `api/music_routes.py`

- **Purpose:** interpret conversational music search ("upbeat lofi for a cooking clip").
- **Function:** `interpret_music_query(...)` → `get_llm().parse(..., MusicInterpretation)`.
- **Output schema:** `MusicInterpretation` (`models.py`).
- **Common failures / handling:** falls back to keyword search.

---

## 6. TTS script generation — `api/edit_runner.py`

- **Purpose:** synchronous helper that turns a short summary into a spoken narration script
  for the `/api/v1/edit/tts/script` endpoint.
- **Function:** `generate_tts_script(...)` (edit_runner.py) using `get_llm()`.
- **Common failures / handling:** endpoint returns **502** on LLM failure or empty output.

---

## 7. Trending query bank — `agents/long_to_shorts/fetch_trending_videos.py`

- **Purpose (optional path):** when `use_llm_queries=True`, generate 5 search queries for a topic.
- **Note:** this path imports `core.llm.llm` (a legacy inline path) rather than
  `tools.llm.get_llm`, uses an inline f-string prompt, and `eval`s the result (flagged
  `noqa: S307`). The default path uses a static `TRENDING_QUERY_BANK` instead. Treat the LLM
  path as legacy/risky — prefer static queries. See `debugging.md` and `design-decisions.md`.

---

## Editing & maintaining prompts

1. **Locate:** prompts are module-level constants near the top of their node/tool file
   (`_ANALYSIS_SYSTEM`, `_CONTENT_SYSTEM`, `THUMBNAIL_SYSTEM`, …). Search the file, don't
   guess.
2. **Structured output first:** prefer `llm.parse(prompt, Schema, system=...)` with a Pydantic
   schema over free-text parsing. Regex fallback parsers exist (`_parse_llm_json`,
   `_parse_content_response`) for non-structured providers but are the fallback, not the path.
3. **Cache correctness:** if you change what a prompt *asks for*, bump the operation `version`
   in the `cached_llm_text(...)` call — otherwise stale completions are served. Parser-only
   changes need no bump (parsing is outside the cache).
4. **Creator guidance:** never concatenate `user_context` into the *system* prompt; route it
   through `guidance_block()` into the user prompt.
5. **Evaluation:** prompt changes should be validated with the (future) `llm-judge` suite —
   see `docs/future/llm-judge.md` and `.claude/skills/prompt-review.md`.
