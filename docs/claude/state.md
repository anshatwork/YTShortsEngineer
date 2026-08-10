# State Schema, Ownership & Persistence

LangGraph state is a `TypedDict` merged across nodes: each node returns a partial dict, LangGraph
shallow-merges it into the running state. There are **three** state types (one per graph — see
`architecture.md`). The active pipeline uses `LongToShortsState`.

## LongToShortsState (`agents/state.py`)

`TypedDict, total=False` (all keys optional — nodes must `.get()` and tolerate absence).

### Inputs (set by runner / CLI)
| Key | Type | Meaning |
|---|---|---|
| `source_video_path` | str | Local path to the long-form video |
| `transcript` | str | Full text transcript |
| `top_n_clips` | int | Max clips (default 5) |
| `user_context` | Optional[str] | Creator guidance (folded into user prompts) |
| `timed_transcript` | Optional[list[dict]] | `{text,start,duration}` from captions/SRT; skips Whisper |
| `clip_mode` | str | `portrait` (default) or `fullscreen` |

### Feature flags (per-job; preferred over env vars)
`add_top_text`, `add_subtitles`, `add_intro`, `add_music`, `add_thumbnail` (bool);
`thumbnail_style`, `subtitle_position`, `subtitle_size` (str); `music_volume_db` (float).

### Job tracking (set by `api/runner.py`; absent in CLI runs)
`job_id` (UUID for log correlation), `current_node` (name of executing node).

### Per-run output isolation (set by clipping_logic, read by all downstream)
| Key | Owner | Meaning |
|---|---|---|
| `run_id` | clipping_logic | `job_id` (API) or deterministic hash (CLI) |
| `clips_dir` | clipping_logic | `OUTPUT_DIR/jobs/<run_id>/clips` — where every clip artifact lives |

This is what prevents concurrent jobs and reruns from overwriting each other's files. **Never
write clip artifacts anywhere but `clips_dir`.**

### Intermediate / outputs
| Key | Owner (writer) | Readers |
|---|---|---|
| `analyzed_segments: list[ClipObject]` | analyze_video | clipping_logic |
| `generated_clips: list[ClipObject]` | clipping_logic (creates) → all later nodes (enrich) | runner (maps to `ClipResult`) |
| `current_step` | every node | logging / debugging |
| `error` | any node on hard failure | runner (Phase 4 raises if set) |

### ClipObject (the unit that flows through the pipeline)

```
clip_id, source_video_path, path (the current rendered file — rewritten by each post node),
timestamp_range (start,end), hook_score,
title, summary, hook_text, hashtags,        # content_gen
thumbnail_path,                             # thumbnail
music_theme, music_path, music_title, music_source, music_attribution,  # content_gen → music_attach
error                                       # per-clip failure note
```

**Ownership rule:** `path` is rewritten in place by each optional node (`_noted` → `_sub` →
`_final` → `_music`). Downstream nodes always read the *current* `path`, so ordering matters (see
the graph edges in `architecture.md`). Don't reorder post nodes without checking suffix assumptions.

## State lifecycle

1. `runner._run_job_impl` builds `initial_state` (inputs + flags + `job_id`) and sets `ADD_*` env
   vars as a secondary channel.
2. `long_to_shorts_app.invoke(initial_state)` runs the graph synchronously in the worker thread,
   inside `llm_credential_context(byok)`.
3. Each node merges its partial return; `node_stage` mirrors `current_node`/stage progress to the
   stores (→ SSE).
4. Final state's `generated_clips` → `ClipResult[]` persisted on the job row; `error` (if set)
   fails the job.

State is **not** persisted between nodes beyond the in-memory dict — `long_to_shorts_app` is
compiled **without a checkpointer**. Durability comes from the CAS cache + the job store, not from
LangGraph checkpoints.

## Checkpoints & resume

- **Long-to-shorts graph:** no `MemorySaver`, no interrupts (see `graph.py`). It is a
  batch pipeline; HITL is handled at the API layer (submit → poll), not via LangGraph interrupts.
- **Legacy graphs:** `agents/graph.py` and `workflows/graph.py` DO use `MemorySaver` +
  `interrupt_before=[…]` for HITL (video selection, review). That checkpointer is in-memory only.
- **Effective resume** for the active pipeline is achieved by the **content-addressable cache**
  (`core/cache`): rerunning a job recomputes keys and re-uses cached clip extracts and LLM
  completions, so unchanged steps are near-free. `PIPELINE_RESUME_ENABLED` and the CAS are the
  resume story; there is no per-node graph checkpoint to resume from.

## Persistence layers (what survives a process restart)

| Data | Store | Backend toggle | Notes |
|---|---|---|---|
| Job status + clips | `db/job_store` (`clip_jobs`) | `JOB_STORE` (memory\|supabase) | wrapped in `EventEmittingStore` |
| Edit jobs | `db/edit_job_store` (`edit_jobs`) | `JOB_STORE` | ” |
| Stage progress | `db/stage_store` (`job_stages`) | `JOB_STORE` | uses `lifecycle` state machine |
| Credit ledger | `db/credit_store` (`credit_ledger`) | `CREDIT_STORE` | append-only; balance = SUM/period |
| Subscriptions | `db/subscription_store` (`subscriptions`) | `SUBSCRIPTION_STORE` | usage counted from `clip_jobs` |
| Trending pool | `db/trending_store` | `JOB_STORE` | crawler-warmed |
| BYOK LLM creds | `db/user_llm_credentials_store` | `JOB_STORE` | Fernet-encrypted at rest |
| YouTube creds/uploads | `db/youtube_*_store` | `JOB_STORE` | OAuth tokens; upload idempotency |
| Rendered clips + LLM completions | `core/cache` CAS | `BLOB_STORE_BACKEND`, `CACHE_INDEX_BACKEND` | keyed by inputs+version |

Supabase stores use the **service-role** client (bypasses RLS); the API layer enforces per-user
ownership using the `user_id` from the verified JWT. Migrations live in `supabase/migrations/`.

## Editing the state schema — checklist

1. Add the field to the right `TypedDict` in `agents/state.py` (usually `LongToShortsState` or
   `ClipObject`) with a comment naming the owning node.
2. Only the **owning node** should write it; readers use `.get()` with a sensible default.
3. If it's user-facing input, thread it through `api/models.py::JobRequest` and
   `runner._run_job_impl`'s `initial_state`.
4. If it becomes an output, map it in the runner's `ClipResult` construction and
   `db/mappers.py` (clips are stored as JSONB).
5. Update this file and `agents.md`.
