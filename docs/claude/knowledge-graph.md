# Knowledge Graph

The persistent multimodal Knowledge Graph (KG) — the semantic layer every future AI capability
consumes. Expensive understanding is computed **once** at ingestion and reused; the graph is the
single source of truth for *what the media means*. Phase 0 (substrate) + Phase 1 (minimal ingestion)
are implemented; deeper perception (VLM, object/face) is deferred behind registries.

> **Additive + off by default.** Everything is gated by `KG_ENABLED` (default `false`). Nothing in
> the clip pipeline changes until it is turned on. See `docs/future/*` for the forward specs this
> realizes.

## Where the data lives (three stores, one anchor)

| Store | System-of-record for | Key |
|---|---|---|
| **Neo4j** (or Memgraph) — `core/kg` | the semantic graph (nodes, edges, **native vector index**) | node stable keys |
| **Supabase/Postgres** — `assets`, `ingestion_jobs` (`010_kg.sql`) | ownership + ingestion job tracking | `asset_id` |
| **CAS** (`core/cache`) / S3 | bytes (keyframes, blobs) | `content_hash` |

The cross-store anchor is **`content_hash`** = the Neo4j `MediaAsset` stable key = Supabase
`assets.content_hash`. Neo4j has **no RLS**, so every node carries `owner_id` and the query layer
(`core/kg/query`) *always* injects an `owner_id` filter.

## Layout

```
core/kg/                     leaf primitive (peer of core/cache; imports only core/)
  driver.py                  Neo4j driver singleton + kg_enabled() + session/run_read/run_write/health
  schema.py                  KEY_PROPS, constraint/index/vector/fulltext DDL (idempotent)
  migrations/__init__.py     run_migrations() — apply_schema() + numbered data backfills
  models.py                  NodeSpec, EdgeSpec, QuerySpec, safe_identifier(), label/edge vocab
  repository.py              parameterized Cypher: upsert_node(s)/edge(s), get, neighbors,
                             vector_search, fulltext_search, redirect_edges (merge)
  resolution.py              normalize_name, canonical_key, merge_entity, resolve_label (fuzzy)
  query.py                   build_cypher (owner-enforced), semantic_search (hybrid),
                             neighborhood, interpret_query (NL→QuerySpec)
tools/embeddings/            get_embedder() factory (mirrors tools/llm): local (bge+OpenCLIP) | hash
tools/vision/                detect_scenes, extract_keyframe (CAS-cached), ocr_image (optional)
agents/ingestion/            ingestion sub-graph: state.py, graph.py, 11 *_node.py, _kg_prompts.py
agents/long_to_shorts/api/   asset_store, ingestion_job_store, ingestion_runner, kg_routes, db/asset_store
supabase/migrations/010_kg.sql   assets + ingestion_jobs
```

## Ingestion pipeline (`agents/ingestion/graph.py`)

Linear LangGraph sub-graph mirroring `long_to_shorts` (each node wraps `node_stage`, delegates to
`_<name>_impl`, returns a partial dict, **degrades not fails**; no checkpointer — durability = CAS +
content-hash keys):

```
decode_probe → scene_detect → keyframe_extract → transcribe → chunk_transcript
  → ocr → embed → extract_entities → extract_relationships → resolve_entities → graph_upsert
```

- **Idempotent:** every KG write is a `MERGE` on a stable key; every expensive stage is CAS-memoized
  (Whisper, keyframes, embeddings, LLM entity extraction). Re-ingesting the same bytes converges,
  cheaply.
- **Reuses** the clip pipeline's helpers: cached Whisper (`run_clipping_workflow.get_transcript`),
  `core/cache`, `get_llm()`, the task queue, the event bus, SSE.

## Schema (essentials)

Node stable keys (`core/kg/schema.KEY_PROPS`): `MediaAsset{content_hash}`,
`Scene{asset_id,scene_index}`, `Frame{asset_id,t_s}`, `TranscriptChunk{asset_id,start_s,end_s}`,
`TextBlock{asset_id,block_key}`, resolvable entities (`Concept/Topic/Person/Organization/Product/
Location/Event/Activity`) `{owner_id,norm_name}`. Edges: `PART_OF`, `HAS_FRAME`, `FOLLOWS`,
`MENTIONS`, `ABOUT_TOPIC`, `APPEARS_IN`, `CONTAINS_TEXT`, `DERIVED_FROM`/`GENERATED_FROM` (clips),
`MERGED_INTO` (resolution provenance). Searchable nodes carry an `embedding` (text=384 dim,
image=512 dim by default) indexed by a per-label Neo4j vector index.

**Excluded:** `Face`/`Emotion` and biometric handling (design decision). `Person` is text/NER-derived.

## Entity resolution (`core/kg/resolution.py`)

1. **Exact (free, at write time):** entities MERGE on `(owner_id, normalize_name(name))`, so a term
   mentioned across 500 assets is one node.
2. **Fuzzy (background):** `resolve_label(label, owner_id, embed_text=…)` finds embedding-nearest
   same-label candidates and `merge_entity()` folds duplicates into the canonical node via
   `repository.redirect_edges` (redirects edges + records `MERGED_INTO` + appends alias). This is
   also the "unknown → later identified" mechanism — all prior edges follow the merge automatically.

## Embeddings (`tools/embeddings`)

`get_embedder()` — `EMBEDDING_PROVIDER=local` (default: `sentence-transformers` bge + OpenCLIP, GPU,
shared text↔image space for cross-modal search) with automatic degrade to `hash` (deterministic,
dependency-free) when local deps are missing. `embed_text_cached`/`embed_image_cached` memoize each
item in the CAS. **Selective:** only searchable nodes get vectors.

## Query engine (`core/kg/query.py`)

- `build_cypher(QuerySpec, owner_id)` → parameterized Cypher, `owner_id` filter always applied.
- `semantic_search(label, text, owner_id)` → hybrid: vector ANN (`repository.vector_search`) +
  lexical full-text, fused and de-duped; degrades to lexical-only if embeddings are unavailable.
- `interpret_query(question)` → NL to a **validated** `QuerySpec` via `get_llm().parse` (never raw
  Cypher generation).

## API (`agents/long_to_shorts/api/kg_routes.py`, mounted at `/api/v1`)

`POST /assets` (201) · `GET /assets` · `GET /assets/{id}` · `POST /assets/{id}/ingest` (202, metered
`ingest` credits, idempotent refund on failure) · `GET /ingest/jobs[/{id}]` ·
`GET /ingest/jobs/{id}/events` (SSE) · `POST /kg/search` · `POST /kg/query` ·
`GET /kg/assets/{id}/graph` · `GET /kg/health`. Reads run off the event loop (`asyncio.to_thread`).
When `KG_ENABLED` is off, `/kg/*` and ingest return `503`.

**Clip-run hook:** on a successful clip job, `runner._maybe_enqueue_kg_ingestion` registers the
source and enqueues ingestion (best-effort, `KG_ENABLED`-gated; a KG failure never affects the clip
job).

## Setup & verification

```bash
# 1. Start a graph (Docker) and point env at it
docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=neo4j/please_change_me neo4j:5
export KG_ENABLED=true NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=please_change_me

# 2. Apply the schema (idempotent: constraints + vector/fulltext indexes)
python -m core.kg.migrations

# 3. Tests (no Neo4j / models needed — driver faked, hash embeddings)
python -m pytest tests/test_kg.py -v

# 4. End-to-end: run a clip job with KG on, then inspect the graph in Neo4j Browser
python run_clipping_workflow.py <youtube-url>     # with KG_ENABLED=true
#   → MediaAsset/Scene/TranscriptChunk/Concept nodes appear; a KG failure never fails the clip job
```

Config: `KG_ENABLED`, `NEO4J_URI/USER/PASSWORD/DATABASE`, `KG_VECTOR_SIMILARITY`,
`EMBEDDING_PROVIDER/FALLBACK`, `EMBEDDING_MODEL_TEXT/IMAGE`, `EMBEDDING_DIM_TEXT/IMAGE`,
`CREDITS_COST_INGEST` (all in `core/config.py` + `.env.example`).

## Roadmap (what's next)

Phase 2: first consumer (`/kg/search` UI + gallery intelligence). Phase 3: perception depth
(`tools/vlm` captioning/object detection → `SHOWS_OBJECT`; diarization → `Speaker`). Phase 4:
training/quiz, story builder, memory, LLM-judge as KG consumers. Phase 5: scheduled re-resolution;
optional privacy-gated affect module. See the approved plan for detail.
