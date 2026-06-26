# Claude API Migration & Prompt Enhancement Plan

## Context

The pipeline currently runs LLM calls through **two** local/remote stacks:

| Stack | Built on | Used by | Default model |
|---|---|---|---|
| **Ollama** (`tools/llm/ollama.py`) | LangChain `ChatOllama`, `.invoke([HumanMessage])` | `agents/long_to_shorts/analyze_video_node.py`, `content_gen_node.py`, `fetch_trending_videos.py` (disabled) | `llama3.1:8b` |
| **HuggingFace** (`tools/llm/huggingface.py`) | `BaseLLMProvider.generate(prompt)` | `agents/script_generation.py` | `zai-org/GLM-4.7` (`core/config.py:32`) |

Both conform (or can conform) to `BaseLLMProvider.generate()` in `tools/llm/base.py`.

Three problems motivate this change:

1. **Fragile output handling.** Every prompt hand-rolls a structured format (bare JSON, "EXACTLY these five lines", `[HOOK]/[BRIDGE]/[CORE SCRIPT]` markers) and then parses it with regexes + fallbacks. Failures silently degrade to synthetic segments / placeholder metadata.
2. **Local model quality.** `llama3.1:8b` is weak at reliable JSON/instruction following, which is the root cause of (1).
3. **No managed option.** There's no path to a high-quality hosted model for production runs.

**Goal:** add Claude (official `anthropic` SDK) as the **default** provider with the existing Ollama/HF stacks retained as an **offline fallback**, and replace the hand-rolled output formats with **structured outputs** + **prompt caching**.

### Decisions (confirmed)

- **Strategy:** Claude default, Ollama/HF kept as fallback (`LLM_PROVIDER` env switch; `ENABLE_LLM_FALLBACK` honored).
- **Model:** `claude-sonnet-4-6` for all pipeline calls.
- This document is the plan; no code has been changed yet.

> Note on "TTS hooks": the files under `tools/tts/` (`base/chatterbox/elevenlabs/streamlabs_polly`) are pure text→audio and contain no LLM/prompt. The hook logic is (a) `agents/voice_synthesis.py::_clean_script_for_tts()` which strips `[HOOK]/[BRIDGE]/[CORE SCRIPT]` markers, and (b) the `agents/script_generation.py` prompt that emits them. This plan removes the need for the marker-stripping by having script generation return discrete fields.

---

## Target architecture

```
core/config.py            LLM_PROVIDER, CLAUDE_MODEL, ANTHROPIC_API_KEY, ENABLE_LLM_FALLBACK
        │
tools/llm/__init__.py      get_llm()  ── selects provider, wraps in fallback chain
        │
        ├── tools/llm/anthropic_provider.py   AnthropicLLM(BaseLLMProvider)  ← default
        ├── tools/llm/ollama.py               OllamaLLM (existing)           ← fallback
        └── tools/llm/huggingface.py          HuggingFaceLLM (existing)      ← fallback
```

`AnthropicLLM` exposes two methods on top of `BaseLLMProvider`:

- `generate(prompt, *, system=None, max_tokens=...) -> str` — free text (script body).
- `parse(prompt, schema, *, system=None) -> BaseModel` — structured output via `client.messages.parse()`.

All calls use `model="claude-sonnet-4-6"`, static instruction text in `system` with `cache_control: {"type": "ephemeral"}`, and the per-item transcript in the user turn (after the cache breakpoint). `max_tokens` defaults to 4096 (well under the non-streaming timeout). No `thinking`/`effort` params — these are short extraction tasks.

---

## Step-by-step

### Step 1 — Dependencies & config

- `requirements.txt`: add `anthropic>=0.69` (remove `langchain-ollama` only if going Claude-only — **not** in this plan; keep it for fallback).
- `.env`: add
  ```
  LLM_PROVIDER=claude            # claude | ollama | hf
  ANTHROPIC_API_KEY=sk-ant-...
  CLAUDE_MODEL=claude-sonnet-4-6
  ```
  (existing `OLLAMA_*` and `ENABLE_LLM_FALLBACK=true` stay.)
- `core/config.py`: add `LLM_PROVIDER`, `CLAUDE_MODEL` (default `claude-sonnet-4-6`), and read `ANTHROPIC_API_KEY` via pydantic-settings.

### Step 2 — `tools/llm/anthropic_provider.py` (new)

```python
import os, anthropic
from pydantic import BaseModel
from tools.llm.base import BaseLLMProvider

class AnthropicLLM(BaseLLMProvider):
    def __init__(self, model=None, max_tokens=4096):
        self._client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY
        self._model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self._max_tokens = max_tokens

    def _system(self, system):
        return [{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}] if system else None

    def generate(self, prompt, *, system=None, max_tokens=None, **_):
        resp = self._client.messages.create(
            model=self._model, max_tokens=max_tokens or self._max_tokens,
            system=self._system(system),
            messages=[{"role": "user", "content": prompt}],
        )
        return next((b.text for b in resp.content if b.type == "text"), "")

    def parse(self, prompt, schema: type[BaseModel], *, system=None, **_):
        resp = self._client.messages.parse(
            model=self._model, max_tokens=self._max_tokens,
            system=self._system(system),
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        return resp.parsed_output
```

Error handling: wrap call sites' use behind the fallback factory (Step 3); surface `anthropic.APIError` so the fallback chain can catch it.

### Step 3 — Unified factory `tools/llm/__init__.py`

```python
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    chain = {"claude": AnthropicLLM, "ollama": OllamaLLM, "hf": HuggingFaceLLM}
    primary = chain[provider]()
    if os.getenv("ENABLE_LLM_FALLBACK", "true") == "true" and provider == "claude":
        return FallbackLLM(primary, OllamaLLM)   # lazy-construct fallback on first failure
    return primary
```

`FallbackLLM` is a thin `BaseLLMProvider` that tries the primary, and on `APIError`/network error constructs and delegates to the fallback (preserving today's `check_available()` pre-flight for the Ollama branch).

### Step 4 — Convert the prompts to structured outputs

Define Pydantic schemas and call `get_llm().parse(...)`:

- **`analyze_video_node.py`** — schema `HookSegment{start_time, end_time, hook_score, hook_type, reason}`. Replaces `_parse_llm_json` + the bare-JSON instruction. Keep the duration-clamp logic (45–75s) as post-validation on the parsed object. Keep synthetic-segment fallback only for the *no-LLM* path.
- **`content_gen_node.py`** — schema `ClipMeta{title, summary, hook_text, hashtags: list[str], mood}` with `mood` as an `enum` of the `AudioTheme` values. Replaces the 5 regexes. Length caps (title ≤50, hook ≤55) become field constraints / post-trim.
- **`script_generation.py`** — schema `Script{visual_intent, hook_style, hook, bridge, core_script}`. **Implementation note:** the script is re-assembled *with* `[HOOK]/[BRIDGE]/[CORE SCRIPT]` markers because `agents/script_parser.py` parses them — so `voice_synthesis.py::_clean_script_for_tts()` is left untouched. The win is the structured (enum-validated) LLM *response*, replacing the regex `_parse_response`.

In each prompt template: drop `CRITICAL:`/`EXACTLY`/`MUST` phrasing and the "return only JSON / these five lines" instructions (the schema enforces shape now). Keep the rubric/criteria content.

### Step 5 — Caching layer

`_llm_cache.py` already keys on `_model_id()` which reads `LLM_MODEL_ID`/`OLLAMA_MODEL`. Add `CLAUDE_MODEL` to that lookup so Claude completions cache under the right key. Bump `_ANALYZE_LLM_CACHE_VERSION` / `_CONTENT_LLM_CACHE_VERSION` since the prompt+contract changes. (This memoization is separate from Anthropic prompt caching and complementary.)

### Step 6 — Call-site edits

Replace `get_chat_model()` + `check_available()` + `.invoke([HumanMessage(...)])` in the 3 long-to-shorts nodes with `get_llm().parse(prompt, Schema, system=INSTRUCTIONS)`. Keep `_invoke_with_retry` semantics (or rely on the SDK's built-in `max_retries`). `script_generation.py` switches `HuggingFaceLLM()` → `get_llm()`.

---

## Model recommendations (reference)

- **Pipeline calls:** `claude-sonnet-4-6` (chosen) — 1M context, structured outputs, good copy quality.
- **Cost lever (optional, future):** `claude-haiku-4-5` is well-suited to the per-chunk scoring + metadata extraction tasks at ~⅓ the cost; could be set per-call if cost matters.
- **Local fallback upgrade:** replace `llama3.1:8b` with **`qwen2.5:7b-instruct`** (much stronger JSON/instruction adherence, same footprint), or `qwen2.5:14b-instruct` / `mistral-nemo:12b` / `gemma2:9b` with more VRAM. Set via `OLLAMA_MODEL`.

---

## Verification

1. `LLM_PROVIDER=claude` — run `run_clipping_workflow.py` on one already-downloaded video; confirm `analyze_video_node` and `content_gen_node` return schema-valid output and the clips render.
2. Inspect `resp.usage.cache_read_input_tokens` on the 2nd+ chunk/clip call to confirm prompt caching is hitting.
3. `LLM_PROVIDER=ollama` — confirm the fallback path still runs end-to-end.
4. Force an API error (bad key) with `ENABLE_LLM_FALLBACK=true` — confirm `FallbackLLM` drops to Ollama.

## Files touched

- New: `tools/llm/anthropic_provider.py`, `tools/llm/__init__.py` (factory + `FallbackLLM`)
- Edited: `core/config.py`, `.env`, `requirements.txt`, `tools/llm/base.py`, `tools/llm/ollama.py`, `tools/llm/huggingface.py`, `agents/long_to_shorts/analyze_video_node.py`, `content_gen_node.py`, `_llm_cache.py`, `agents/script_generation.py`
- Deliberately **not** touched: `agents/voice_synthesis.py` / `_clean_script_for_tts` (markers preserved for `script_parser` compatibility)
