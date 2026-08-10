---
name: prompt-review
description: Review LLM prompt changes in this repo (system prompts, user prompts, structured-output schemas, cache versioning). Use when editing _ANALYSIS_SYSTEM/_CONTENT_SYSTEM/THUMBNAIL_SYSTEM or any get_llm() call site.
---

# Prompt Review

Context: `docs/claude/prompts.md`. Prompts drive analyze_video, content_gen, thumbnail, discover,
music, and TTS-script.

## Checklist

**Structure**
- [ ] System prompt stays a **static** module constant (so the Anthropic ephemeral cache block
      keeps working). No per-request data interpolated into the system prompt.
- [ ] Creator guidance flows through `guidance_block(user_context)` into the **user** prompt only.
- [ ] Uses `llm.parse(prompt, PydanticSchema, system=...)`; the Pydantic schema encodes the
      contract (types, enums, limits) rather than prose-only rules.

**Cache correctness**
- [ ] If the prompt's *meaning/output* changed → **bump `version`** in the `cached_llm_text(...)`
      call for that operation (`analyze_llm`, `content_llm`, `thumbnail_llm`, …).
- [ ] If only parsing changed → no bump (parsing is outside the cache).

**Output & constraints**
- [ ] Hard limits (title ≤50, hook ≤55, N hashtags, mood ∈ AudioTheme) are enforced by the schema
      AND stated in the prompt; the two agree.
- [ ] Failure path defined: placeholder/synthetic fallback exists and is sensible (never crash the
      node).

**Quality**
- [ ] Instructions are specific and testable (avoid vague "be engaging").
- [ ] No leaking of the guidance block back as title/summary/hook (the block already forbids this —
      keep that instruction).

**Validation**
- [ ] Sanity-run on 2–3 representative transcripts across providers if feasible.
- [ ] Ideally gated by the eval suite (`docs/future/llm-judge.md`) once it exists — see the
      `llm-evaluation` skill.

## Output
State what changed, whether a `version` bump is required (and whether it was done), and any
schema/prompt disagreement. Flag prompts that only work on Claude but must also run on Ollama/GLM
(base `parse` is prompt-engineered JSON extraction — keep outputs simple and unambiguous).
