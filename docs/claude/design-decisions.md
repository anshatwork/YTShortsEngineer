# Design Decisions (ADRs)

Architecture Decision Records — the *why* behind non-obvious choices. Each: context/problem,
decision, alternatives, tradeoffs. These are reconstructed from the code and existing docs; where
a decision looks accidental rather than intentional, it's flagged as **debt**, not an ADR.

---

## ADR-001 — Three coexisting graphs

**Problem.** The repo has three LangGraph graphs: the class-based `workflows/graph.py` (oldest,
via `main.py`), the modular `agents/graph.py` (via `batch_processor.py`), and the current
`agents/long_to_shorts/graph.py` (via the API). Only the last is the live product.

**Decision.** Keep the two legacy graphs in place, unmodified, and build the product on
`long_to_shorts`. Reuse only `ScriptParserAgent` and `VideoSelectionAgent` from the legacy code.

**Alternatives.** (a) Delete legacy graphs — risks losing the topic→short generation path and the
tests that still exercise those agents. (b) Refactor all three into one — large, high-risk, no
immediate product value.

**Tradeoffs.** Coexistence causes confusion (two `ShortsState` definitions, duplicated
YouTube/video-assembly logic) and dead-ish code. Accepted for now because the legacy path is
self-contained and cheap to ignore. New work should target `long_to_shorts`. See "Technical debt"
in the audit summary. *(This is partly documented intent, partly inertia — treat legacy as frozen.)*

---

## ADR-002 — In-process thread-pool task queue (not Celery/RQ/Temporal)

**Problem.** Pipeline jobs are long (FFmpeg + Whisper + LLM) and must not block the API.

**Decision.** Run jobs on an in-process `ThreadPoolTaskQueue` (`WORKER_THREADS`, default 2),
behind a `TaskQueue` ABC. `TASK_QUEUE_BACKEND` names celery/temporal/rq as future backends; they
currently warn and fall back to threadpool.

**Alternatives.** External broker (Celery/Redis) from day one — more moving parts, more infra cost.

**Tradeoffs.** Simple, single-box, cheap (fits the ~$20–70/mo go-live target). But: no durability
across restarts (in-flight jobs are lost), no horizontal scale, and the event bus + cache index
default to in-process/local — so the ABC seams exist precisely to swap in Redis/broker/S3 later
(see `docs/ARCHITECTURE.md` §7 scaling path). Uvicorn runs a **single process**; concurrency is
`WORKER_THREADS`, not uvicorn workers, because queue+bus are in-memory.

---

## ADR-003 — Content-addressable cache as the "resume" mechanism

**Problem.** Reruns and retries shouldn't re-pay for expensive, deterministic work (clip
extraction, LLM completions).

**Decision.** A CAS (`core/cache`) keyed by `sha256(operation, version, canonical_json(inputs))`
memoizes rendered clip blobs and LLM completion JSON. The long_to_shorts graph is compiled
**without a LangGraph checkpointer**; the CAS is the durability/resume story.

**Alternatives.** LangGraph checkpointer with a persistent backend — couples resume to graph
internals and doesn't help cross-job artifact reuse.

**Tradeoffs.** Cross-job reuse and cheap retries; deterministic artifact ids. Cost: correctness
depends on **version discipline** — forget to bump `version` after a prompt/encoder change and you
serve stale artifacts (see `debugging.md`). Blob store (`BLOB_STORE_BACKEND`) and index
(`CACHE_INDEX_BACKEND`) are swappable (local/S3, sqlite/supabase).

---

## ADR-004 — LLM provider abstraction with Claude default + Ollama fallback + BYOK

**Problem.** Need quality (Claude) but also a free/offline path (Ollama) and per-user keys (BYOK)
for the SaaS.

**Decision.** `get_llm()` factory selects by `LLM_PROVIDER` (default `claude`), wraps Claude in
`FallbackLLM` (→ Ollama on runtime error) when `ENABLE_LLM_FALLBACK`, and honors a thread-local
BYOK credential. **BYOK never falls back to Ollama** (a user's bad key must not spend project GPU).
BYOK is currently **claude-only** (`BYOK_PROVIDERS = ("claude",)`); keys are Fernet-encrypted at
rest (`BYOK_FERNET_KEY`). Structured output uses native `messages.parse` for Claude and a
prompt-engineered JSON-extraction path for others.

**Alternatives.** OpenRouter as the single gateway (recommended in `docs/inference-hosting-cost-comparison.md`
for the hosted SaaS) — simpler ops, one key, but a hard dependency and per-token cost.

**Tradeoffs.** Flexibility + cost control + offline dev. Cost: three code paths to keep working
and structured-output parity to maintain. Anthropic prompts use ephemeral cache blocks (~0.1×
cost across chunks) — keep system prompts static to preserve that.

---

## ADR-005 — MCP tools call the REST API in-process (not a parallel implementation)

**Problem.** Expose the pipeline to Claude.ai/ChatGPT without duplicating business logic.

**Decision.** MCP tools (`mcp_server.py`) are thin wrappers that invoke the same `/api/v1` routes
**in-process** via `httpx.ASGITransport` (`mcp_client.py`), forwarding the Supabase bearer token
so routes run as the authenticated user. Streamable-HTTP transport mounted at `/mcp`.

**Alternatives.** A separate MCP service reimplementing the operations — duplicated logic, drift,
double the auth/credit surface.

**Tradeoffs.** Behavior matches REST exactly; one code path; shares `app.state` (task queue).
Cost: MCP and REST share a process (no isolation), and the ASGI transport is an unusual pattern to
learn. Discovery routes must be registered on the app root (RFC 9728), a known footgun.

---

## ADR-006 — Dual config reads (`settings` + `os.getenv`)  *(debt, documented)*

**Problem.** `core/config.Settings` (pydantic-settings) can fail to construct (e.g. missing
required `HUGGINGFACE_API_KEY`), which would otherwise break unrelated modules at import.

**Decision.** `Settings` construction is wrapped in try/except (warn-only), and many modules read
`os.getenv` directly for their own vars so they work regardless. Some modules (`huggingface.py`,
`youtube/search.py`) read `settings`.

**Tradeoffs.** Resilience (a bad/missing var doesn't cascade). Cost: no single source of truth;
defaults live in two places and can diverge. **Guidance:** prefer `settings` for new code; don't
mix both in one module. Flagged as debt to consolidate.

---

## ADR-007 — Feature flags via both state and env vars

**Problem.** The pipeline runs both as an API job (per-job flags) and as a CLI/standalone graph
(process-wide config).

**Decision.** Optional nodes read `state["add_x"]` first, then env `ADD_X`. The API runner sets
the env vars from the request as a secondary channel before `invoke`.

**Tradeoffs.** Works in both contexts; per-job override possible. Cost: two sources of truth per
flag and process-global env mutation inside the runner (not thread-isolated — acceptable at
`WORKER_THREADS=2` today but a hazard if worker count grows or flags are set concurrently). Prefer
state; treat env as the fallback. Revisit if concurrency increases.

---

## ADR-008 — Credits (primary) + quota (secondary), both fail-open

**Problem.** Monetize per-operation while not blocking paying users on infra hiccups.

**Decision.** A ledger-backed credit meter (`credits.py`, opt-in `CREDITS_ENABLED`) debits per op
and refunds idempotently on failure; a monthly job-count `quota.py` is a coarse secondary cap.
Both **fail open** on transient store errors and raise `402` only on a real shortfall.

**Tradeoffs.** Revenue + resilience. Cost: possible under-billing during an outage (accepted:
better than false denials). Grants/refunds must stay idempotent (unique keys) or double-spend/
double-grant bugs appear.

---

## ADR-009 — Separate stores behind facades + `EventEmittingStore`

**Decision.** Each domain has a store facade choosing memory vs Supabase from an env toggle
(`JOB_STORE`, `CREDIT_STORE`, `SUBSCRIPTION_STORE`), with Supabase using the service-role client.
Job/edit/upload stores are wrapped in `EventEmittingStore` so every `update()` emits an SSE event.

**Tradeoffs.** Clean dev (in-memory) vs prod (Supabase) parity; SSE for free on state changes.
Cost: multiple toggles to keep straight; ownership checks must be enforced at the API layer since
workers bypass RLS.

---

## Non-decisions / open questions

- **Hosted inference gateway** — `docs/inference-hosting-cost-comparison.md` recommends OpenRouter
  for the live SaaS, but the code still centers Claude/Ollama/GLM. Reconcile before scale.
- **Frontend hosting** — separate deploy (Vercel/Cloudflare); the backend only serves REST+SSE+MCP.
- **Windows-first assumptions** — several paths (Impact font, ASS escaping) assume Windows; Docker
  uses DejaVu. A cross-platform font resolver is the clean fix.
