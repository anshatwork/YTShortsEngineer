# AI Learning OS — Architecture & System Design Specification

> **Status: Design only. Not implemented.** This is a forward-design spec (like the other
> `docs/future/*` docs). It defines the target architecture for a Personal Learning OS built on top
> of the existing knowledge-graph substrate. No service code exists yet; the roadmap (§20) sequences
> delivery. Nothing here changes the running clipping product until built and gated on.

---

## Context — why we are building this

An **AI-powered Personal Learning OS**: a long-term companion that turns every intentionally-saved
piece of content ("Remember this") into a **living per-user knowledge graph**, adaptive learning
assets, and personalized study plans. The primary entity is **knowledge**, not content — the system
answers *"what does this user know, how confident are we, what's weak, what's next?"* rather than
*"what videos did they watch?"*

**Why now / what prompted it.** This repo already contains ~80% of the hard substrate, built and
tested but idle behind `KG_ENABLED=false`:
- a **Neo4j knowledge-graph primitive** (`core/kg`) with a generic `NodeSpec`/`EdgeSpec` repository,
  owner-scoped Cypher, native vector index, entity resolution;
- an **11-node ingestion sub-graph** (`agents/ingestion`) — decode→transcribe→chunk→embed→extract
  entities/relationships→resolve→upsert;
- a **provider-agnostic embedding factory** (`tools/embeddings`) and **LLM factory** (`tools/llm`);
- a **content-addressable cache** (`core/cache`) that doubles as an idempotency key store;
- an **event bus + task queue + EventEmittingStore→SSE** execution layer (`core/execution`).

Critically, the KG schema **already declares** `Concept`, `Topic`, `Summary`, `Question`, `Quiz`,
`Story`, `Course`, `Collection` node types and `EXPLAINS`/`SUMMARIZES`/`BELONGS_TO`/`REFERENCES`
edges — with **no producers yet**. The repo's own roadmap lists "training/quiz, story builder,
memory as KG consumers" as future work (`docs/claude/roadmap.md`, `docs/claude/knowledge-graph.md`
Phase 4). **The Learning OS is that consumer layer.**

**Intended outcome.** A user installs a Chrome extension, clicks *Remember this* on a YouTube video
or article, and — with no further action — the content is ingested, concepts + prerequisites are
extracted into their personal knowledge graph, learning assets (summary, flashcards) are generated,
and everything is searchable. Everything beyond that (quizzes-as-mastery, study planner, spaced
repetition, recommendations) is architected now and delivered in later phases.

### Decisions locked (2026-08-11)

| # | Decision | Choice |
|---|---|---|
| A | **Topology** | **True microservices** on an external broker, each service its own DB. The existing clipping backend is treated as a standalone service (not redesigned). |
| B | **Graph tenancy** | **Fully per-user** concept graph. Every node carries `owner_id`; queries inject an owner filter (reuse `core/kg/query.build_cypher`). Mastery is a per-user overlay *within* the owner scope. **No shared global graph** (revisit for collaborative-learning phase). |
| C | **MVP boundary** | **Capture → ingest → concepts+prereqs → graph → basic assets (summary + flashcards) → semantic/graph search → browse UI.** Study planner, spaced repetition, recommendations, quizzes-as-mastery, coding exercises are **designed but deferred**. |
| D | **v1 content types** | **YouTube/Shorts** (reuse `agents/ingestion`) **+ Articles/Documentation** (new readability text path). PDFs, podcasts, repos, books, courses = extension points only. |

### Non-negotiable principles

1. **Model knowledge, not content.** Content is *evidence*; concepts are the aggregate root.
2. **Event-sourced.** Every meaningful operation emits an immutable domain event; events are the
   source of truth; **replay is a first-class capability** (improve a model → replay from the right
   event, don't rebuild).
3. **Clipping pipeline is a standalone microservice** — integrate, do not redesign.
4. **Extensibility over completeness** — design hooks for future content types/consumers; don't
   build them.

---

## Deliverable 1 — High-level architecture diagram

```
┌───────────────┐     ┌──────────────────────────────────────────────────────────────┐
│ Chrome Ext.   │     │                       CLIENTS                                 │
│ "Remember     │     │   Web App (Next.js 16)      Mobile (future)     MCP/Claude    │
│  this"        │     └──────────────────────────────────────────────────────────────┘
└──────┬────────┘                         │  HTTPS / SSE / WS
       │  HTTPS                            ▼
       └──────────────────────►┌──────────────────────────┐
                               │      API GATEWAY          │  authN (JWT verify), routing,
                               │  (FastAPI, edge)          │  rate-limit, SSE fan-out
                               └────────────┬──────────────┘
                                            │ REST (sync reads/commands)
        ┌───────────────────────────────────┼───────────────────────────────────────┐
        ▼                                    ▼                                        ▼
┌───────────────┐   ┌──────────────────────────────────────────────┐        ┌────────────────┐
│  AUTH         │   │      COMMAND-SIDE SERVICES (write)            │        │ QUERY-SIDE     │
│ (Supabase     │   │  Content Ingestion · Metadata · Transcript·  │        │ SERVICES (read)│
│  JWT, OIDC)   │   │  Embedding · Concept Extraction · Knowledge   │        │ Vector Search ·│
└───────────────┘   │  Graph · Learning Asset · Quiz · Study        │        │ Search (hybrid)│
                    │  Planner · Progress · Review Scheduler ·      │        │ · Recommender  │
                    │  Notification                                 │        └────────────────┘
                    └───────────────┬──────────────────────────────┘
                                    │ publish/subscribe (durable, replayable)
                          ┌─────────▼───────────────────────────────────┐
                          │         EVENT BUS  (NATS JetStream)          │
                          │  subjects = event types; durable streams;    │
                          │  per-consumer offsets; replay from offset 0  │
                          └─────────┬───────────────────────────────────┘
                                    │
   ┌───────────────┐   ┌────────────▼───────────┐   ┌──────────────┐   ┌───────────────────┐
   │ EXISTING      │   │  EVENT STORE (SoR)      │   │ Object Store │   │ Per-service DBs   │
   │ CLIPPING      │◄──┤  Postgres append-only   │   │ S3/MinIO     │   │ Postgres (rel) ·  │
   │ SERVICE       │   │  `domain_events` +      │   │ clips, audio │   │ Neo4j (graph) ·   │
   │ (this repo)   │   │  transactional outbox   │   │ keyframes,   │   │ Qdrant (vectors) ·│
   │ FastAPI+LG    │   └─────────────────────────┘   │ thumbnails   │   │ Raw content store │
   └───────────────┘                                 └──────────────┘   └───────────────────┘
```

**Two rails.** *Command* services own writes and emit events; *query* services build read-optimized
projections (search indexes, recommendation caches, progress views) from those events. Everything
between services is **asynchronous** over the broker; only client-facing reads/commands are sync
REST through the gateway.

---

## Deliverable 2 — Service dependency diagram

Runtime dependencies are almost entirely **via events** (the broker), not direct calls. Solid = sync
REST/gRPC call; dashed = async event.

```
Client ──sync──► API Gateway ──sync──► Auth (verify)
API Gateway ──sync──► {Knowledge Graph, Search, Study Planner, Progress}   (reads/commands)

Content Ingestion  ──emit──► ContentSaved
   └─ pulls bytes via ──sync──► (yt-dlp / readability) ; writes Object Store + Raw Content Store

Transcript         ──sub ContentSaved──►  emit TranscriptExtracted        (calls Clipping Svc for A/V)
Metadata           ──sub ContentSaved──►  emit MetadataExtracted
Segmentation*      ──sub TranscriptExtracted──► emit ContentSegmented      (*inside Ingestion in MVP)
Embedding          ──sub ContentSegmented──►  emit EmbeddingsGenerated     (calls Embedding libs)
Concept Extraction ──sub {Segmented,Embeddings}──► emit ConceptsExtracted   (calls LLM)
Knowledge Graph    ──sub ConceptsExtracted──►  emit KnowledgeGraphUpdated + MasteryUpdated
Clipping (existing)──sub ContentSaved(video)──► emit ClipsGenerated         (standalone svc)
Learning Asset     ──sub KnowledgeGraphUpdated──► emit LearningAssetsGenerated
Quiz               ──sub KnowledgeGraphUpdated──► emit QuizGenerated
Progress Tracker   ──sub {QuizCompleted,AssetViewed,...}──► emit MasteryUpdated
Review Scheduler   ──sub MasteryUpdated──►  emit RevisionScheduled
Study Planner      ──sub {MasteryUpdated,RevisionScheduled}──► emit StudyPlanUpdated
Recommender        ──sub KnowledgeGraphUpdated──► (rebuilds projection; served sync)
Notification       ──sub {RevisionDue,StudyPlanUpdated}──► push/email
Vector Search      ──sub EmbeddingsGenerated──►  (upserts Qdrant; served sync)
```

**Key rule (mirrors the repo's downward-only layering):** no service reaches into another service's
DB. Cross-service knowledge travels only as events or through a gateway-brokered sync read.

---

## Deliverable 3 — Event flow diagram (the "Remember this" chain)

```
ContentSaved
   ├──► [Transcript]  TranscriptExtracted ─┐
   ├──► [Metadata]    MetadataExtracted    │
   └──► [Clipping]    ClipsGenerated (video only, parallel, non-blocking)
                                            │
                          ContentSegmented ◄┘  (segmentation)
                                    │
                          EmbeddingsGenerated
                                    │            └──► [Vector Search upsert]
                          ConceptsExtracted
                                    │
                          KnowledgeGraphUpdated ──► MasteryUpdated(exposure++)
                             │            │              │
        ┌────────────────────┘            │              └──► [Review Scheduler] RevisionScheduled
        ▼                                 ▼                              │
  LearningAssetsGenerated            QuizGenerated                       ▼
        │                                 │                       StudyPlanUpdated
        └──────────────┬──────────────────┘                             │
                       ▼                                                 ▼
                (later) QuizCompleted / RevisionCompleted ──► MasteryUpdated ──► RecommendationsUpdated
```

Each arrow is a broker publish; each `[Service]` is an independent consumer with its own offset.
Fan-out is natural — many services subscribe to `KnowledgeGraphUpdated` without knowing about each
other.

---

## Deliverable 4 — Sequence diagrams

### 4a. Happy path: Remember a YouTube video

```
User→Ext: click "Remember this" on youtube.com/watch?v=X
Ext→Gateway: POST /v1/content {url, type:youtube}  (Bearer JWT)
Gateway→Auth: verify JWT → user_id
Gateway→Ingestion: POST /content (sync) → 202 {content_id}
Ingestion→RawStore: insert content(content_id, url, owner_id, status=saved)
Ingestion→EventStore: append ContentSaved (outbox, same txn)   ← atomic
Ingestion→Gateway→Ext: 202 {content_id, status:"saved"}        ← user is done here
Outbox→Broker: publish ContentSaved
Broker→Transcript: ContentSaved → (calls Clipping Svc /transcript or Whisper) → TranscriptExtracted
Broker→Clipping:   ContentSaved(video) → ClipsGenerated (parallel; best-effort)
Broker→Embedding:  ContentSegmented → EmbeddingsGenerated (CAS-cached per chunk)
Broker→Concept:    ConceptsExtracted (LLM parse, CAS-cached)
Broker→KG:         KnowledgeGraphUpdated (+ MasteryUpdated exposure++)
Broker→LearningAsset: LearningAssetsGenerated (summary+flashcards)
Gateway (SSE): /v1/content/{id}/events streams saved→ingesting→graphed→assets_ready
```

### 4b. Event replay (better embedding model ships)

```
Operator→Replay CLI: replay --from EmbeddingsGenerated --model bge-v2 --owner <id|all>
Replay→EventStore: read ContentSegmented events (offset 0..now) for scope
Replay→Broker: re-publish to a shadow subject `replay.ContentSegmented`
Embedding(replay consumer): recompute embeddings (new model) → EmbeddingsGenerated(v2)
  → Concept(replay) → ConceptsExtracted(v2) → KG(replay) upserts (idempotent MERGE) → assets regen
Transcript/Clipping: NOT re-run (upstream of the replay point)     ← replay boundary respected
```

Replay never re-runs transcript extraction or clip generation because it starts *below* them in the
chain — exactly the brief's requirement.

---

## Deliverable 5 — Domain model (DDD aggregates)

| Aggregate root | Owns / invariants | Lives in |
|---|---|---|
| **Content** (`content_id`) | source url/type/owner, `content_hash`, status; immutable once saved | Content Ingestion |
| **Transcript** (`content_id`) | segments `[{text,start,end,speaker?}]`; derived, versioned by model | Transcript |
| **Concept** (`owner_id,norm_name`) | canonical name, aliases, description, difficulty; **entity-resolution invariant: one node per (owner, normalized name)** | Knowledge Graph |
| **KnowledgeEdge** | `PREREQUISITE_FOR/REQUIRES/EXTENDS/RELATED_TO/...` between concepts; no self-loops; prereq graph is a DAG (cycle-broken on write) | Knowledge Graph |
| **LearnerConcept** (`owner_id,concept_id`) | mastery ∈ [0,1], confidence, exposure_count, last_seen, last_reviewed, forgetting_score, revision_priority; **only Progress Tracker mutates mastery** | Progress Tracker (overlay in KG) |
| **LearningAsset** (`asset_id`) | type (summary/notes/flashcards/…), `concept_ids[]`, `source_version`, content; regenerated+versioned when supporting content changes | Learning Asset |
| **Quiz / Question** (`quiz_id`) | items, concept coverage, difficulty | Quiz |
| **StudySession** (`session_id`) | plan (clips/quiz/exercise/reflection), time budget, outcomes | Study Planner |
| **RevisionSchedule** (`owner_id,concept_id`) | next_due, interval, ease (SM-2-ish) | Review Scheduler |
| **Clip** (`clip_id`) | timestamps, transcript, summary, `concept_ids[]`, difficulty, objectives — a first-class learning object | Clipping (existing) → linked in KG |

**Value objects:** `ContentHash`, `Embedding(vector,model,dim)`, `MasteryEstimate(signals→score)`,
`ConfidenceSignal` (exposure/diversity/retrieval/quiz/decay).

**Orchestration vs business logic:** each service = a thin transport/adapter shell (FastAPI routes +
event consumers) around a pure **domain layer** (`domain/`) with no I/O; all infra (graph store,
vector store, LLM, broker) behind **ports** (interfaces) and injected adapters — dependency
inversion, mirroring the repo's `tools/*` registry pattern and `core/kg` port design.

---

## Deliverable 6 — Bounded contexts

| Context | Responsibility | Reuses from repo |
|---|---|---|
| **Chrome Extension** | one action: *Remember this*; capture url/selection/type; auth token | — |
| **API Gateway** | edge auth, routing, rate-limit, SSE/WS fan-out | `events_routes` SSE pattern |
| **Auth** | identity, JWT issue/verify, OIDC | Supabase auth (existing) |
| **Content Ingestion** | dedup (content_hash), persist raw content, emit `ContentSaved`; text extraction (readability) for articles/docs | `core/cache.hash_*`, `agents/ingestion` decode |
| **Metadata Extraction** | title/author/platform/thumbnail/published-at/chapters | `tools/youtube` |
| **Transcript** | captions or Whisper; segment | `run_clipping_workflow.get_transcript`, Clipping svc |
| **Clipping (existing)** | long→shorts clips as learning objects | **the whole current backend** |
| **Embedding** | text/image vectors, provider-agnostic, CAS-cached | `tools/embeddings` |
| **Concept Extraction** | LLM entity+concept+prereq extraction, validated schema | `agents/ingestion/extract_*`, `tools/llm` |
| **Knowledge Graph** | concept/edge upsert, entity resolution, owner-scoped query/neighborhood | `core/kg` (driver/repo/resolution/query) |
| **Vector Search** | ANN over embeddings; hybrid with lexical | `core/kg.semantic_search` → Qdrant adapter |
| **Learning Asset** | summaries/notes/flashcards/mind-maps per concept; versioned | `docs/future/training-agent.md` |
| **Quiz** | quiz/question/coding-exercise generation *(deferred)* | training-agent spec |
| **Study Planner** | adaptive sessions from time+gaps+goals *(deferred)* | — |
| **Recommendation** | concept-level next-best via graph traversal *(deferred)* | `core/kg.neighbors` |
| **Progress Tracker** | multi-signal mastery/confidence; owns `MasteryUpdated` | `docs/future/memory-system.md` |
| **Review Scheduler** | spaced-repetition scheduling *(deferred)* | — |
| **Notification** | push/email for due reviews, plan ready *(deferred)* | — |

---

## Deliverable 7 — Database schemas (polyglot, per service)

**All services are Python/FastAPI** (reuse `tools/llm`, `tools/embeddings`, `core/kg`, `core/cache`
as shared libs) — polyglot **persistence**, not polyglot runtime.

### Relational (Postgres/Supabase) — one schema per service, no shared tables
```sql
-- Content Ingestion  (raw content store, immutable)
content(content_id uuid pk, owner_id uuid, source_type text, url text, content_hash text,
        title text, author text, platform text, published_at timestamptz,
        status text check(status in ('saved','ingesting','ingested','failed')),
        created_at timestamptz, unique(owner_id, content_hash))          -- idempotent capture

-- Transcript
transcript(content_id uuid pk, model text, lang text, segments jsonb, version int, created_at)

-- Learning Asset
learning_asset(asset_id uuid pk, owner_id uuid, kind text, concept_ids uuid[],
               source_version int, payload jsonb, created_at, superseded_by uuid null)

-- Progress Tracker (mastery overlay; system of record for learner state)
learner_concept(owner_id uuid, concept_id text, mastery real, confidence real,
                exposure_count int, last_seen timestamptz, last_reviewed timestamptz,
                forgetting_score real, revision_priority real, updated_at,
                primary key(owner_id, concept_id))
mastery_signal(id bigserial pk, owner_id, concept_id, signal_type text, weight real,
               value real, event_id uuid, created_at)                    -- audit of inputs

-- Quiz / Study / Review  (deferred; schemas stubbed)
quiz(...), question(...), study_session(...), revision_schedule(owner_id, concept_id,
     next_due timestamptz, interval_days real, ease real, reps int, primary key(owner_id,concept_id))

-- Event Store (system of record for events; see D8)
domain_events(event_id uuid pk, stream text, seq bigint, type text, version int,
              owner_id uuid, occurred_at timestamptz, payload jsonb, metadata jsonb,
              unique(stream, seq))
outbox(event_id uuid pk, published bool default false, created_at)       -- transactional outbox
```
RLS everywhere (owner-select); services write via service-role, gateway enforces owner from JWT —
identical to the existing `supabase/migrations/*` pattern.

### Graph (Neo4j) — Knowledge Graph service (reuse `core/kg/schema.py`)
- **Nodes** (existing labels): `Concept`, `Topic`, `Person`, `Organization`, `Product`,
  `MediaAsset`, `TranscriptChunk`, `Clip`, plus **new** `LearningAsset`, `Question`.
- **Existing edges reused:** `MENTIONS`, `ABOUT_TOPIC`, `EXPLAINS`, `SUMMARIZES`, `RELATED_TO`,
  `PART_OF`, `DERIVED_FROM`.
- **New edges to add to `EDGE_TYPES`:** `PREREQUISITE_FOR`, `REQUIRES`, `EXTENDS`, `DEPENDS_ON`,
  `ALTERNATIVE_TO`, `CONTRADICTS`, `IMPLEMENTS`.
- Every node keeps `owner_id`; queries go through `build_cypher(..., owner_id)` (unchanged).
- Native vector index stays for graph-coupled search; **Qdrant** holds the primary ANN index for the
  Vector Search service (behind the existing `Embedder`/search port).

### Vector (Qdrant) — Vector Search service
Collections per modality; payload `{content_id, chunk_id, owner_id, concept_ids}`; **owner_id filter
mandatory** on every query (multi-tenant). HNSW index.

### Object storage (S3/MinIO)
clips, keyframes, thumbnails, audio — keyed by `content_hash` (reuse `core/cache` CAS semantics).

---

## Deliverable 8 — Event schemas

**Envelope** (CloudEvents-compatible; one shape for all):
```json
{
  "event_id": "uuid", "type": "ConceptsExtracted", "version": 2,
  "stream": "content-<content_id>", "seq": 7,
  "owner_id": "uuid", "occurred_at": "2026-08-11T…Z",
  "correlation_id": "uuid", "causation_id": "uuid",
  "payload": { "…": "type-specific" },
  "metadata": { "source_service": "concept-extraction", "model": "claude-…", "cache_key": "sha256:…" }
}
```
`version` on the envelope enables **schema evolution + replay** (a consumer knows how to read v1 vs
v2). Extends the existing `core/execution/eventbus.Event` dataclass with `stream/seq/owner_id/
correlation_id/causation_id/version`.

**Canonical payloads (essentials):**
| Event | payload |
|---|---|
| `ContentSaved` | `content_id, source_type, url, content_hash, title?` |
| `TranscriptExtracted` | `content_id, model, segments[], lang` |
| `ContentSegmented` | `content_id, chunks[{chunk_id,text,start,end}]` |
| `EmbeddingsGenerated` | `content_id, chunk_ids[], model, dim` (vectors in Qdrant, not the event) |
| `ConceptsExtracted` | `content_id, concepts[{norm_name,label,description,difficulty}], relations[{src,rel,dst}]` |
| `KnowledgeGraphUpdated` | `owner_id, upserted_concept_ids[], upserted_edges[], stats` |
| `ClipsGenerated` | `content_id, clips[{clip_id,ts,summary,concept_ids}]` |
| `LearningAssetsGenerated` | `owner_id, asset_ids[], concept_ids[], kinds[]` |
| `MasteryUpdated` | `owner_id, concept_id, mastery, confidence, signals[]` |
| `QuizCompleted` | `owner_id, quiz_id, per_question[{concept_id,correct}]` |
| `RevisionScheduled` | `owner_id, concept_id, next_due, interval_days` |
| `StudyPlanUpdated` | `owner_id, session_id, items[]` |

**Idempotency:** every consumer keys side-effects on `event_id` (dedup table) **and** graph writes
are `MERGE` (naturally idempotent) — so at-least-once delivery and replay are safe.

---

## Deliverable 9 — API contracts (REST, via Gateway, `/v1`)

| Method & path | Purpose | Status |
|---|---|---|
| `POST /v1/content` | Remember this `{url,source_type,selection?}` → `{content_id}` | 202 |
| `GET /v1/content/{id}` / `GET /v1/content` | status + metadata / list | 200 |
| `GET /v1/content/{id}/events` | SSE ingestion progress | 200 (stream) |
| `GET /v1/graph/concepts` / `/concepts/{id}` | list / detail (mastery, sources, neighbors) | 200 |
| `GET /v1/graph/concepts/{id}/neighborhood` | prereq/related traversal | 200 |
| `GET /v1/search?q=&mode=keyword\|semantic\|graph\|hybrid` | unified search | 200 |
| `POST /v1/ask` | NL question → interpret_query → graph+vector answer | 200 |
| `GET /v1/assets?concept_id=` / `GET /v1/assets/{id}` | learning assets | 200 |
| `GET /v1/recommendations` | next concepts (graph traversal) *(deferred)* | 200 |
| `POST /v1/study/sessions` `{minutes,goal?}` *(deferred)* | adaptive session | 201 |
| `POST /v1/quiz/{id}/submit` *(deferred)* | grade → `QuizCompleted` | 200 |
| `GET /v1/progress` | mastery dashboard | 200 |
| `GET /v1/reviews/due` *(deferred)* | due revisions | 200 |

Backward-compat: the existing clipping service keeps its `/api/v1/*`, `/static`, `/library`, `/mcp`
contracts untouched; the gateway proxies to it.

---

## Deliverable 10 — Folder structure (new `learning-os/` monorepo alongside this repo)

```
learning-os/
  services/
    gateway/            app/ (routes, sse, auth_mw)   Dockerfile
    ingestion/          app/ domain/ adapters/ consumers/ events.py   Dockerfile
    transcript/         app/ domain/ adapters/ …
    embedding/          …            (wraps libs/embeddings)
    concept/            …            (wraps libs/llm + prompts)
    knowledge_graph/    …            (wraps libs/kg)
    vector_search/      …            (Qdrant adapter)
    learning_asset/     …
    progress/           …            (mastery engine)
    quiz/ study_planner/ recommender/ review_scheduler/ notification/   (deferred stubs)
  libs/                 # extracted, versioned shared packages (from this repo)
    kg/                 ← lift-and-shift of core/kg (leaf, imports only stdlib+driver)
    embeddings/         ← tools/embeddings
    llm/                ← tools/llm
    cache/              ← core/cache (CAS + idempotency)
    events/             ← core/execution.Event + broker port (NATS/Kafka/inproc adapters)
    domain_shared/      ← envelope, owner-scope helpers, event-store client, outbox
  extension/            manifest v3, background.js, popup, auth
  web/                  Next.js 16 browse UI (graph, search, assets)   [reuse frontend/ patterns]
  deploy/               docker-compose (dev), k8s/helm (prod), NATS, qdrant, neo4j, postgres
  contracts/            openapi/*.yaml, asyncapi/*.yaml (event schemas), json-schema/
  tools/replay/         replay CLI + projection rebuild
```
Each service: `domain/` (pure) · `adapters/` (ports impl) · `consumers/` (event handlers) · `app/`
(FastAPI). Mirrors the repo's downward-only layering (`app → domain → ports`, adapters at the edge).

---

## Deliverable 11 — Deployment architecture

- **Dev:** `docker-compose` — gateway + services + NATS JetStream + Postgres + Neo4j + Qdrant +
  MinIO. One command, mirrors the existing `docker-compose.yml`/Caddy setup.
- **Prod (target):** Kubernetes (or Nomad) — each service a Deployment + HPA; NATS JetStream cluster
  (3 nodes) or managed; Postgres = Supabase/RDS; Neo4j = Aura or a StatefulSet; Qdrant Cloud or
  StatefulSet; S3 + CloudFront (reuse existing S3/CloudFront + signed-URL work). Ingress + TLS via
  Caddy/Traefik (SSE-aware `flush_interval -1`, already solved in this repo).
- **Existing clipping service** deploys unchanged (its own image) and joins the mesh; the gateway and
  the ingestion/transcript services call it over REST.
- **Cost pragmatism (reuse the SaaS plan):** GPU (Whisper/embeddings/Ollama) scale-to-zero; managed
  broker only when single-node NATS is outgrown.

---

## Deliverable 12 — Technology choices with trade-offs

| Concern | Choice | Why / trade-off |
|---|---|---|
| **Broker** | **NATS JetStream** (primary) | Durable streams + per-consumer offsets + replay + subjects-as-event-types, far lighter than Kafka; single binary in dev. Trade-off: smaller ecosystem than Kafka → **Kafka** documented as the drop-in for very high throughput; `libs/events` keeps it broker-agnostic (the existing `EventBus` ABC already anticipates this). |
| **Event store** | **Postgres append-only + transactional outbox** | Events are SoR in Postgres (strong consistency with the aggregate write), outbox relays to the broker. Simpler/cheaper than EventStoreDB; replay reads Postgres or the JetStream stream. |
| **Graph** | **Neo4j** (reuse `core/kg`) | Already built, owner-scoped, native vectors, entity resolution. Trade-off: another stateful store; Memgraph is bolt-compatible drop-in. |
| **Vectors** | **Qdrant** | Dedicated ANN/HNSW, mandatory payload filtering for multi-tenant, horizontal scale. Behind a port → pgvector/Neo4j-native remain fallbacks (reuse `semantic_search`). |
| **Relational** | **Postgres/Supabase** | Reuse existing auth, RLS, migrations, service-role pattern. |
| **Runtime** | **Python/FastAPI everywhere** | Reuse `tools/llm`, `tools/embeddings`, `core/kg`, `core/cache`, LangGraph. Trade-off: not "best tool per service," but massive code reuse + one skill set beats polyglot churn for a solo/small team. |
| **LLM/Embeddings** | reuse `get_llm()` / `get_embedder()` + BYOK | provider-agnostic, cached, degrade-not-fail already solved. |
| **Object store** | S3/MinIO via `core/cache` CAS | content-hash idempotency already implemented. |

---

## Deliverable 13 — Scalability considerations

- **Async fan-out** means each consumer scales independently; hot stages (embedding, concept
  extraction, transcription) scale horizontally by adding consumers on the same durable stream
  (JetStream distributes by consumer group).
- **CAS memoization** (existing) makes reprocessing near-free — embeddings/transcripts/LLM parses are
  keyed by `(operation, version, inputs)`; re-ingest and replay converge cheaply.
- **CQRS**: read load hits projections (Qdrant, recommendation cache, progress views), never the
  write path or the event store.
- **Graph hotspots**: per-user isolation keeps each user's subgraph small; owner_id range index +
  `MERGE` on stable keys already in `core/kg/schema`. Prereq DAG queries bounded by traversal depth.
- **Backpressure**: JetStream max-ack-pending + bounded consumer concurrency; the existing
  `asyncio.Queue(maxsize=256)` drop-oldest policy informs SSE fan-out.
- **Partitioning**: stream-per-content (`content-<id>`) gives natural ordering per item without a
  global bottleneck; owner_id is the sharding key for stores.

---

## Deliverable 14 — Failure recovery strategy

- **At-least-once + idempotency**: every consumer dedups on `event_id`; graph writes are `MERGE`;
  learner mastery updates are computed from the full signal set (recomputable). This is the existing
  **degrade-not-fail** contract extended across services.
- **Transactional outbox**: aggregate write + event append commit in one Postgres txn; a relay
  publishes to the broker — no lost/dup events on crash between DB and broker.
- **Dead-letter**: JetStream max-deliver → DLQ subject; a DLQ inspector service + manual/auto retry.
- **Crash recovery**: consumers resume from their durable offset (like the existing publishing
  `list_resumable()` sweep, now broker-native). No work lost on restart.
- **Best-effort branches never block the chain**: Clipping, Metadata, and (later) Notification
  failures are logged and dropped — the KG chain still completes (mirrors
  `_maybe_enqueue_kg_ingestion` swallowing failures today).
- **Poison content**: per-content circuit breaker → mark `content.status='failed'`, emit
  `IngestionFailed`, refund any credits idempotently (reuse `refund:{id}` pattern).

---

## Deliverable 15 — Event replay strategy (first-class)

1. **Immutable log** in `domain_events` (+ JetStream retention) is the source of truth; projections
   and even the graph are rebuildable from it.
2. **Replay CLI** (`tools/replay`): `replay --from <EventType> --scope <owner|all> --to shadow`
   re-publishes historical events of/after a type to **shadow subjects**, consumed by
   **replay-mode** instances that write to the real stores idempotently (or to a green store for
   blue/green cutover).
3. **Boundary respected**: replaying `EmbeddingsGenerated` re-runs Embedding→Concept→KG→Assets but
   **not** Transcript/Clipping (they're upstream). Each stage's `version` (already a convention in
   `core/cache` keys and now on the event envelope) invalidates only what changed.
4. **Projection rebuild**: drop+rebuild Qdrant/recommendation/progress projections by re-reading the
   log — no re-ingestion.
5. **Snapshots**: periodic per-aggregate snapshots (learner state, graph stats) bound replay time;
   replay from latest snapshot + tail.

---

## Deliverable 16 — Security model

- **Tenant isolation is the top invariant.** `owner_id` on every node/row/vector; **mandatory owner
  filter** in `build_cypher` (Neo4j has no RLS), Qdrant payload filter, Postgres RLS. Cross-tenant
  read = treated as a Sev-1 class; contract tests assert every query path injects the filter.
- **Least privilege**: each service has its own DB creds scoped to its schema; no service can read
  another's tables. Broker subjects are ACL'd per service (publish/subscribe allowlists).
- **Secrets**: reuse Fernet-at-rest for BYOK keys (`tools/llm/credentials`), env-injected DB/broker
  creds, no secrets in events or logs (existing "never log secrets" rule).
- **Input trust**: the extension sends only a URL + JWT; entitlement/owner derived from the **verified
  JWT**, never the request body (existing money-path rule).
- **PII / erasure**: content may contain PII in transcripts → encrypt at rest, per-user delete
  (right-to-erasure) implemented as a `ContentForgotten` event that tombstones graph nodes + purges
  vectors/objects.

---

## Deliverable 17 — Authentication & authorization

- **AuthN**: Supabase JWT (reuse existing `auth.py`/`get_current_user_id`). Extension does OAuth/OIDC
  (Supabase), stores the token, sends `Authorization: Bearer`. Gateway verifies signature + exp; SSE
  uses `?token=` (EventSource can't set headers — existing pattern).
- **Service-to-service**: short-lived mTLS or signed service JWTs (audience = target service); broker
  connections authenticated per service.
- **AuthZ**: coarse ownership (owner_id == JWT sub) enforced at the gateway + every store; future
  roles (viewer/editor for collaborative learning) modeled as overlay edges, not built now.
- **Entitlement/metering**: reuse credits/quota (`credits.enforce_and_debit`, fail-open meters) —
  ingestion and asset-generation debit; refund-on-failure idempotent.

---

## Deliverable 18 — Observability

- **Correlation**: `correlation_id` (per user action) + `causation_id` (parent event) on every
  envelope → trace the full Remember-this chain across services. Reuse the repo's context-aware
  logging (`core/logging_config`, `job_log_context`).
- **Tracing**: OpenTelemetry spans per consumer, exported to Jaeger/Tempo; span links follow
  causation.
- **Metrics**: per-service RED (rate/errors/duration), per-event-type lag (consumer offset vs stream
  head), CAS hit-rate, LLM/token cost per stage (reuse existing cost logging), mastery-update
  throughput. Prometheus + Grafana.
- **Logs**: structured JSON, `owner_id`/`content_id`/`correlation_id` in every line; never secrets.
- **Health/SLOs**: `/health` per service (reuse `kg.health()` never-raises pattern); DLQ depth and
  consumer lag are the primary alerts.

---

## Deliverable 19 — Testing strategy

- **Domain unit tests** (pure `domain/`, no I/O) — mastery math, entity resolution, prereq-DAG cycle
  breaking, confidence signal fusion.
- **Consumer contract tests** — given event X, assert emitted event Y + idempotency on redelivery +
  **owner-filter present** on every store call. Mock at ports (broker, graph, vector, LLM,
  embeddings) — reuse the repo's boundary-mock + in-memory-store + `AUTH_DISABLED=1` approach.
- **Schema/contract tests** — AsyncAPI (events) + OpenAPI (REST) validated in CI; envelope version
  compatibility (v1 consumer reads v2? explicit).
- **Integration** — docker-compose up broker+stores, run the full ContentSaved→KnowledgeGraphUpdated
  chain against fakes (Neo4j faked / hash embeddings, as `tests/test_kg.py` already does).
- **Replay tests** — replay a fixture log, assert projections converge to the same state
  (determinism); assert transcript/clipping are *not* re-invoked.
- **Multi-tenant isolation tests** — property test: no query returns another owner's node.
- **Per-service CI** (mirrors the repo's per-file pytest discipline to avoid shared-singleton
  redness); frontend `lint && build`.

---

## Deliverable 20 — Incremental implementation roadmap

> Even the MVP is genuinely distributed (broker + several services) per the topology decision — but
> we stand up the **minimum service set** that proves the core value, then grow.

**Phase 0 — Foundations (infra + contracts).** `learning-os/` monorepo; extract `libs/{kg,
embeddings,llm,cache,events}` from this repo; NATS JetStream + Postgres + Neo4j + Qdrant + MinIO in
compose; `domain_events`+outbox; event envelope + AsyncAPI/OpenAPI contracts; Gateway + Auth
(Supabase reuse); Chrome extension skeleton (auth + POST /content). **Exit:** click → `ContentSaved`
in the log.

**Phase 1 — MVP core: capture → graph (the value prop).** Content Ingestion (dedup, article
readability path + YouTube), Transcript (reuse clipping svc), Embedding, Concept Extraction (with
prereq edges), Knowledge Graph (extract `core/kg`, add prereq edges + mastery exposure overlay).
Full chain `ContentSaved → … → KnowledgeGraphUpdated (+ MasteryUpdated exposure)`. Web browse UI:
graph + concept detail. **Exit:** remember 10 mixed items → a coherent personal concept graph with
prerequisites.

**Phase 2 — Assets + search.** Learning Asset service (summary + flashcards, versioned), Vector
Search (Qdrant projection from `EmbeddingsGenerated`), unified `/search` + `/ask` (hybrid). Clipping
service wired as a parallel `ClipsGenerated` consumer producing clip learning-objects linked in KG.
**Exit:** every remembered item yields a summary + flashcards and is findable by keyword/semantic/
graph.

**Phase 3 — Adaptive learning (deferred set).** Progress Tracker (multi-signal mastery), Quiz,
Review Scheduler (SM-2 spaced repetition), Study Planner (adaptive sessions), Recommendation
(concept-level traversal), Notification. **Exit:** a 20-minute adaptive session with review clips +
quiz + reflection + next recommendation.

**Phase 4 — Scale & replay hardening.** Replay CLI + projection rebuild + snapshots; DLQ tooling;
OTel/Prometheus/Grafana; k8s + HPA; managed broker if needed.

**Phase 5 — Extensibility (architected only).** New content adapters (PDF/podcast/repo/book/course);
collaborative/org graphs (revisits the per-user→global-overlay decision); MCP server surface; voice
tutor; calendar; mobile.

---

## Verification (how to validate the design & later the build)

- **Design review (now):** this document + the AsyncAPI/OpenAPI contract stubs are the review
  artifact. Confirm bounded contexts, event schemas, and the replay boundary before any code.
- **Phase-exit demos** (above) are the functional acceptance gates.
- **Local end-to-end (Phase 1):** `docker-compose up`, POST a YouTube URL + an article URL via the
  gateway, watch SSE go `saved→ingesting→graphed`, then inspect Neo4j Browser for
  `Concept`/`PREREQUISITE_FOR` nodes and query `/v1/graph/concepts` — reusing the existing
  `tests/test_kg.py` faked-driver harness for CI and Neo4j only for the live demo.
- **Replay validation:** replay `EmbeddingsGenerated` with a new model; assert graph/assets update
  and transcript/clipping do **not** re-run.

---

## Open questions to resolve before Phase 0

1. **Broker**: NATS JetStream (recommended) vs Kafka — cost/ops preference?
2. **Web browse UI**: extend the existing `frontend/` (Next.js 16) or a fresh `learning-os/web`?
3. **Repo layout**: new `learning-os/` monorepo vs `services/` inside this repo (affects how
   `libs/` are shared vs the current in-repo `core/`, `tools/`).
4. **Clipping coupling**: keep the existing backend fully intact as-is (gateway proxies), or extract
   its KG-ingestion path into the new Ingestion service over time?

---

## Relationship to existing forward specs

This spec is the umbrella that composes several existing `docs/future/*` designs as services:
`training-agent.md` → Learning Asset + Quiz services; `memory-system.md` → Progress Tracker;
`gallery-agent.md`/`vlm-agent.md` → richer perception feeding Concept Extraction; `video-sourcing.md`
→ additional content adapters. The knowledge-graph substrate it builds on is documented in
`docs/claude/knowledge-graph.md`.
