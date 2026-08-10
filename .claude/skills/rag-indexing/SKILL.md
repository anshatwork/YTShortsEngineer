---
name: rag-indexing
description: Guide for retrieval-augmented and indexing features in this repo — embeddings, vector store (pgvector), content-addressable caching, incremental/idempotent indexing. Use when building gallery/video-sourcing/memory retrieval or any embedding index.
---

# RAG & Indexing

For gallery indexing (`docs/future/gallery-agent.md`), unified video sourcing
(`docs/future/video-sourcing.md`), and agent memory (`docs/future/memory-system.md`). Build all of
them on shared infrastructure — don't create parallel stacks.

## Shared infrastructure (reuse, don't reinvent)
- **Vector store: Supabase `pgvector`.** This is already a Supabase shop; add a migration in
  `supabase/migrations/` rather than introducing FAISS/Chroma infra.
- **Embeddings: one CLIP (image/text) model + one text-embedding model**, shared across
  gallery/video-sourcing/vlm/memory. A single embed module in `core/` or `tools/`.
- **Blob/keyframe storage: the CAS (`core/cache`).** Keyframes, thumbnails, and downloaded media go
  in the content-addressable store — not a new directory scheme.
- **Change detection: content hashes.** Hash files (`core/cache/keys.hash_file`) and skip unchanged
  inputs — indexing must be **idempotent and incremental**.

## Indexing pipeline pattern
1. Enumerate sources (folders/providers).
2. Hash each item → skip if already indexed at that hash.
3. Extract units (scenes/segments) → keyframe/text.
4. Embed + compute pHash → upsert `{id, embedding, metadata}` into pgvector.
5. Run as a **background task on the task queue** (like the music/trending warm loops in
   `api/app.py` lifespan), bounded by worker count.

## Retrieval pattern
- [ ] Embed the query; vector top-k with metadata filters (duration, resolution, has-OCR).
- [ ] **Blend lexical + semantic**: exact-term queries should also match `ocr_text`/`tags`, not
      embeddings alone.
- [ ] Deduplicate results: exact (content hash) → near-dup (pHash Hamming → embedding cosine
      tiebreak); keep the highest-quality/most-permissive copy.
- [ ] Return a token-budgeted context block; for agent memory, inject via
      `guidance_block()` into the user prompt (keeps LLM cache keys correct).

## Guardrails
- [ ] Per-user isolation via RLS on any user-scoped index (memory).
- [ ] Ranking weights live in `core/config.py` (tunable without code changes).
- [ ] Don't embed on the event loop — it's IO/CPU; use the task queue.

## Review with: `architecture-review`, `performance-optimization`, `search-retrieval`.
