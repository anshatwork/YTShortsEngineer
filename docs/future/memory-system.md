# Future Spec — Agent Memory System

> Status: **Design only.** Not implemented.

## Problem

Every job runs stateless. The system never learns a creator's voice, which hooks/titles
performed, which music themes they keep, or which clips they reject. A memory system lets
agents personalize and improve over time — better defaults, fewer rejections, higher CTR.

## Goals

Four memory types, each with a clear read/write owner:

- **Working memory** — per-job scratch (already implicit in LangGraph state); formalize a
  cross-node bag not persisted after the job.
- **Episodic memory** — records of past jobs and their outcomes (accepted/rejected clips,
  edits made, upload metrics).
- **Semantic memory** — distilled facts/preferences per creator ("prefers punchy titles",
  "channel is about X", "never uses energetic music").
- **Vector memory** — embeddings of transcripts/clips/titles for similarity recall.

## Non-goals

- Model fine-tuning (out of scope; memory is retrieval-augmented context, not weights).
- Storing PII beyond what Supabase auth already holds.

## Proposed architecture

```
core/memory/
  base.py          # MemoryStore protocol; Memory record models
  working.py       # in-process, request-scoped (dict facade over state)
  episodic.py      # append-only job/outcome log (Supabase table)
  semantic.py      # distilled preference facts (Supabase table, LLM-summarized)
  vector.py        # pgvector similarity store (shared with gallery/video-sourcing)
  recall.py        # unified query → assembles context for a node/prompt
```

Persistence reuses **Supabase** (the app's system of record) with a new migration
(`supabase/migrations/0NN_memory.sql`) and `pgvector` for the vector store — no new infra,
consistent with existing `db/` stores.

### Record model

```python
class MemoryRecord(TypedDict):
    id: str
    user_id: str
    kind: Literal["episodic","semantic","vector"]
    scope: str                 # e.g. "titles", "music", "clip_selection"
    content: str               # human-readable fact or event
    embedding: Optional[list[float]]
    metadata: dict             # outcome metrics, job_id, timestamps
    created_at: str
```

### Write paths (owners)

- **Episodic**: written by `api/runner.py` and `edit_runner.py` on job completion, and by
  YouTube upload/metrics hooks (accepted vs rejected, edits applied).
- **Semantic**: a periodic distillation task (task queue, like the music/trending
  loops) summarizes recent episodic records per creator into stable preference facts via
  `get_llm()`.
- **Vector**: transcripts/titles/clip captions embedded on write (shared CLIP/text model).

### Read path

`recall.for_node(user_id, node_name, query)` returns a compact, token-budgeted context
block that nodes fold into prompts via the existing `_prompt_utils.guidance_block`
mechanism — so memory reaches the LLM through the *user* prompt (keeping cache keys
correct, exactly like creator `user_context` today).

## Integration points

- `analyze_video_node` / `content_gen_node`: inject recalled creator preferences into the
  guidance block → personalized hooks/titles/music.
- `music_attach` / `content_gen` music theme: bias toward historically-kept themes.
- `llm-judge.md`: episodic outcomes become the calibration signal ("what actually did well").
- Personalization must be **opt-in** and per-user isolated (RLS on Supabase tables).

## Phased plan

1. **P1** — Episodic log (migration + `episodic.py`); write from runners; no reads yet.
2. **P2** — Semantic distillation task + recall into guidance block for titles/hooks.
3. **P3** — Vector memory (pgvector) shared with gallery/video-sourcing; similarity recall.
4. **P4** — Outcome-driven calibration loop with `llm-judge`; metrics from uploads.

## Open questions

- Cache-key interaction: memory in the *user* prompt changes LLM cache keys per creator —
  intended, but reduces cross-user cache hits. Acceptable; document the tradeoff.
- Staleness/decay: weight recent episodic records higher; expire semantic facts on
  contradiction.
- Privacy: strict RLS + user-initiated "forget me" that purges all memory rows.
