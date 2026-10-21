# Tools & Adapter Layer

The `tools/` package is the side-effecting adapter layer: LLMs, TTS, video editing,
asset/music sourcing, and YouTube access. LangGraph nodes and API routes call into these;
these modules never import graph state. Keep it that way (see `coding-guidelines.md`).

> Verified against the code as of this writing. When you change a signature or env var,
> update this file (or run `make docs` / `scripts/gen_repo_map.py`).

---

## tools/llm/ — provider-agnostic LLM

**Factory: `get_llm() -> BaseLLMProvider`** (`tools/llm/__init__.py:122`). This is the ONLY
way nodes should obtain an LLM. Selection order:

1. Thread-local BYOK credential (`current_llm_credential.get()`) — if present, construct
   that provider with the user's key and **no Ollama fallback** (a bad user key must never
   spend project GPU/credits).
2. Else `LLM_PROVIDER` env (default `claude`).
3. `ENABLE_LLM_FALLBACK` (default true): if primary construction fails and provider isn't
   ollama, fall back to Ollama; and when provider is `claude`, wrap in `FallbackLLM`
   (primary → Ollama on any runtime exception).

**Interface (`base.py`)** — `BaseLLMProvider`:
- `generate(prompt, **kwargs) -> str` (abstract)
- `complete(prompt) -> str` (defaults to `generate`)
- `parse(prompt, schema: Type[BaseModel], *, system=None) -> BaseModel` — structured
  output. Default impl is prompt-engineered (appends JSON schema, extracts first `{...}`
  via `_extract_json`, validates with Pydantic). This seam lets Ollama/HF/GLM do structured
  output without native support.

**Providers:**

| Provider | Class | Key env | Model env (default) | Structured output |
|---|---|---|---|---|
| `claude` | `AnthropicLLM` | `ANTHROPIC_API_KEY` | `CLAUDE_MODEL` (`claude-sonnet-4-6`) | native `messages.parse`, falls back to base |
| `glm` | `GLMLLM` | `GLM_API_KEY` (aliases `ZAI_API_KEY`, `ZHIPUAI_API_KEY`) | `GLM_MODEL` (`glm-4.5-flash`) | base (prompt-engineered) |
| `ollama` | `OllamaLLM` | — (local) | `OLLAMA_MODEL` (`llama3.1:8b`) | base |
| `hf` | `HuggingFaceLLM` | `settings.HUGGINGFACE_API_KEY` | `settings.LLM_MODEL_ID` | base |

- **Anthropic**: static `system` text is sent as an ephemeral cache block
  (`cache_control: ephemeral`) → prompt caching (~0.1× cost across chunks). `CLAUDE_MAX_TOKENS`
  (4096). Passing `api_key=None` lets the SDK read env.
- **GLM**: OpenAI-compatible REST (`GLM_BASE_URL`, default `https://api.z.ai/api/paas/v4`).
  Never logs the key; caps error bodies to 300 chars.
- **Ollama**: wraps LangChain `ChatOllama`; `check_available()` probes `/api/tags`.
- **HuggingFace**: note the non-standard `generate(prompt_template, input_variables: dict)`
  signature and that it reads `core.config.settings`, not `os.getenv`.

**BYOK** (`credentials.py`, `byok.py`):
- `LLMCredential(provider, api_key, model=None)` — frozen; validates `provider in BYOK_PROVIDERS`
  (**currently `("claude",)` only**); `__repr__` redacts the key.
- `current_llm_credential` is a `ContextVar`; `llm_credential_context(cred)` binds it per
  worker thread/job.
- At-rest encryption: `encrypt_secret`/`decrypt_secret` use Fernet; `_fernet()` requires
  `BYOK_FERNET_KEY` (raises if unset). Encrypted keys live in Supabase.

**LLM completion caching:** not in the providers. It lives in
`agents/long_to_shorts/_llm_cache.py::cached_llm_text(prompt, *, operation, version, invoke)`,
which memoizes raw completion text in the CAS (`core/cache`). Cache key = active model id +
hash of prompt, namespaced by `operation` + `version`. Bump `version` when a prompt changes
meaning; parsing stays outside the cache so parser fixes don't need a bump.

---

## tools/tts/ — text-to-speech

**Factory: `select_tts_provider()`** (`tools/tts/__init__.py:31`). Cascading priority:
ElevenLabs (real `ELEVENLABS_API_KEY`) → Chatterbox (`CHATTERBOX_API_KEY`) → Streamlabs
Polly (`TTS_FREE_PROVIDER=streamlabs`) → edge-tts (default free). `_real_key()` rejects
placeholder values so shipped `.env` placeholders don't trigger premium 401s.

**Interface (`base.py`)** — `generate_audio(text, output_path, voice_id=None, language="en",
preset=None) -> str`. Shared `_pyttsx3_to_file(...)` fallback renders WAV via SAPI5 then
transcodes with ffmpeg-python (libmp3lame for `.mp3`, aac for `.m4a/.aac`); raises
`AudioGenerationError` (no silent dummy).

| Provider | Notes |
|---|---|
| `EdgeTTS` | Free MS neural voices; falls back to pyttsx3 on failure. |
| `ElevenLabsTTS` | SDK `text_to_speech.convert`; `ELEVENLABS_VOICE_ID`; **no** pyttsx3 fallback. |
| `ChatterboxTTS` | POST `CHATTERBOX_API_URL`; pyttsx3 fallback. |
| `StreamlabsPollyTTS` | Undocumented `streamlabs.com/polly/speak`; pyttsx3 fallback. |

---

## tools/video_editing/ — rendering & mixing

- **`processor.py`** — `extract_word_timestamps(audio_path, model_name="base")` via **OpenAI
  Whisper** (`word_timestamps=True`). Raises `AudioGenerationError`. (Despite the name, no
  FFmpeg here.)
- **`layout_engine.py`** — `compose_video(...)` via **MoviePy 2.x**. `audio_mode` ∈
  {voiceover, fetched_video, bg_video}, `video_mode` ∈ {split_screen, fetched_video,
  bg_video}, target 1080×1920. Captions only when `audio_mode=="voiceover"`. Writes
  `libx264`/`aac`, `preset="medium"`, `threads=4`, `-pix_fmt yuv420p -movflags +faststart`.
  Raises `RenderingError`.
- **`caption_generator.py`** — `create_caption_clips(timestamps, video_duration)` → MoviePy
  `TextClip`s. **Hardcoded font `C:\Windows\Fonts\impact.ttf`** (Windows-only; a portability
  debt — see `design-decisions.md`). Emphasis words → 70px yellow + zoom, else 60px white.
- **`audio_mixer.py`** — direct **FFmpeg via subprocess**. `mix_background_music(video, music,
  out, volume_db=-18.0, music_start_sec=0.0)`. Loops music (`-stream_loop -1`), mixes under
  existing audio (`amix ... duration=first`), **copies video** (`-c:v copy`), re-encodes audio
  (`aac 192k`), `-shortest`. `_resolve_ffmpeg_bin()` prefers `imageio_ffmpeg.get_ffmpeg_exe()`.

Representative mix command:
```
ffmpeg -y -i <video> -stream_loop -1 [-ss <start>] -i <music> \
  -filter_complex "[1:a]volume=<db>dB[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map 0:v -map [a] -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest <out>
```

- **`tools/editor_engine.py`** (top-level) — legacy self-contained split-screen pipeline
  (yt-dlp download → ElevenLabs VO → Whisper → Impact captions → MoviePy assemble). Uses bare
  `RuntimeError`. Overlaps `video_editing/`; prefer the modular modules for new work.

**FFmpeg is invoked four ways across the repo:** MoviePy, ffmpeg-python, raw subprocess, and
yt-dlp's FFmpeg postprocessor. See `.claude/skills/ffmpeg-best-practices.md`.

---

## tools/assets/ — asset & music sourcing (registry pattern)

The proven abstraction to mirror for future video sourcing (`docs/future/video-sourcing.md`).

- **Models (`models.py`)**: `AssetType` enum (only `MUSIC` wired up); `Asset` dataclass
  (`cache_key = f"{source}:{source_id}"`); `AssetQuery(asset_type, theme, keywords, order,
  min/max_duration, limit=5, user_id, include_vocals)`, `bucket = theme or "default"`.
- **Provider (`base.py`)**: `AssetSource(ABC)` — `available()`, `discover(query)` (metadata),
  `fetch(asset)` (default HTTP GET to temp file, 30s).
- **Registry (`registry.py`)**: `register_source` (idempotent by name), `get_sources(type,
  available_only=True)`. **Registration order = tier priority.**
- **Sources (`sources/`)**: built-ins registered = `[Jamendo, Pixabay, Freesound]` (Jamendo
  primary). **YouTube music source is deliberately NOT auto-registered** — instantiated only
  by `music_routes.py` on manual pick, and every asset carries a `COPYRIGHT_WARNING`.
  `_env.configured(name)` rejects blank/placeholder env values.
- **Retrieval (`retrieval.py`)**: `retrieve(query, k=1)` — cache-first; on stale pool,
  `_discover_live` iterates sources in order downloading new candidates, then ranks. `_rank`
  blends freshness, popularity, keyword overlap; weights depend on `order` (latest/popular/
  relevance). `_personalization_bias` is a v1 stub (0). `record_feedback` logs only.
- **Store (`store.py`)**: file-backed CAS-adjacent cache with per-bucket `index.json`.
  `ASSET_CACHE_DIR` (default `assets`), MUSIC → `audio_cache/<bucket>/`. LRU-by-mtime eviction
  above `AUDIO_CACHE_MAX_SIZE_MB` (500); never evicts `user_*` files or the `songs` bucket.
- **Refresh (`refresh.py`)**: `refresh_music_cache()` warms every `AudioTheme` bucket; run on
  the task queue by `api/app.py`'s lifespan loop (`MUSIC_CACHE_REFRESH_HOURS`, default 24).
- **Resilience (`backoff.py`)**: every source's discover/download goes through `get_with_backoff`
  (retries 429/5xx with exp backoff+jitter). A download that fails after retries is recorded in a
  TTL **negative cache** (`mark_bad`/`is_bad`) keyed by `Asset.cache_key`, so a persistently broken
  track (e.g. a Jamendo storage 500) is skipped for `ASSET_NEGATIVE_CACHE_TTL_HOURS` instead of
  being re-fetched every refresh cycle. `_discover_live` also pre-filters known-bad candidates.

Key env: `ASSET_CACHE_DIR`, `AUDIO_CACHE_MAX_SIZE_MB`, `ASSET_FRESHNESS_TTL_HOURS` (24),
`ASSET_MIN_POOL` (5), `MUSIC_CACHE_TRACKS_PER_THEME` (8), `ASSET_MAX_RETRIES` (2),
`ASSET_BACKOFF_BASE_SECONDS` (0.5), `ASSET_NEGATIVE_CACHE_TTL_HOURS` (6), plus per-source keys
(`JAMENDO_CLIENT_ID`, `PIXABAY_API_KEY`, `FREESOUND_API_KEY`, `YT_API_KEY`).

`tools/audio_api.py` is a thin compat shim over `retrieve()`; new code should call
`tools.assets.retrieve` directly.

---

## tools/youtube/ + top-level YouTube

- **`downloader.py`** (yt-dlp): `download_video` (mp4 best; anti-bot UA/referer/headers,
  `player_client=["android","web"]`, retries; maps 403 → `VideoDownloadError`), `download_audio`
  (mp3 @192k via FFmpeg postprocessor), `fetch_video_title` (metadata only).
- **`search.py`** (YouTube Data API v3): `YouTubeSearchTool.search_videos(...)` (long-form
  default ≥1200s; 100 quota units + details batch), `trending_music` (chart mostPopular cat 10,
  **1 unit**), `search_music` (100 units). Reads `settings.YT_API_KEY`.
  - **Quota governance** (`quota.py`): every call goes through `_execute_with_backoff`, which
    charges the shared `youtube_quota` daily budget (`YOUTUBE_DAILY_QUOTA`, midnight-Pacific reset),
    retries transient rate-limit/5xx with exponential backoff+jitter (`YT_MAX_RETRIES`), and raises
    `QuotaExceededError` on daily-quota exhaustion (never retried). Callers degrade to the cached
    trending pool. Per-query results are TTL-cached (`YT_SEARCH_CACHE_TTL_HOURS`) — a repeat query
    costs 0 units. The background crawler yields to interactive discovery via `YT_QUOTA_RESERVE`.
- **`transcript.py`** (`youtube-transcript-api`, no key): `fetch_timed_segments` (supports v0.x
  and v1.x API shapes; retries other languages), `fetch_transcript` (joined text),
  `extract_video_id`.
- **`tools/youtube_api.py`**: legacy `fetch_yt_assets_node` used by the first shorts graph.

---

## tools/thumbnail.py — LLM-directed thumbnails

`generate_thumbnail(clip_meta, video_path, out_path, ...)` orchestrates: LLM `ThumbnailSpec`
(headline, accent_color, text_position, style, search_query) via `get_llm().parse` cached with
`cached_llm_text(operation="thumbnail_llm", version=2)` → best frame via ffmpeg `thumbnail`
filter (fallback Pixabay photo) → Pillow compositing (bubble/highlight/box/plain), JPEG q=90.
Never raises (falls back to `_fallback_spec`). Font resolution tries Windows/Linux paths →
Pillow default. Env: `THUMBNAIL_WIDTH/HEIGHT`, `THUMBNAIL_FONT_SIZE`, `THUMBNAIL_BOX_ALPHA`,
`THUMBNAIL_MARGIN_PX`, `PIXABAY_API_KEY`.

---

## Cross-cutting

- **Typed exceptions** (`core/exceptions.py`): `AudioGenerationError`, `RenderingError`,
  `VideoDownloadError`. Legacy `editor_engine.py` uses bare `RuntimeError` (debt).
- **Config inconsistency**: LLM/assets/thumbnail read `os.getenv` directly; `huggingface.py`
  and `youtube/search.py` read `core.config.settings`. Prefer `settings` for new code — see
  `design-decisions.md` ADR-006.
- **Caching layers**: asset disk cache (TTL/LRU), LLM completion cache (`cached_llm_text` over
  CAS), Anthropic ephemeral prompt cache, and clip-extract CAS. Providers have no request cache.
