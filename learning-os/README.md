# AI Learning OS — Phase 0 (Foundations)

Event-sourced microservices that turn "Remember this" saved content into a **per-user knowledge
graph** + adaptive learning assets. Built on top of the existing clipping/KG repo
(`../` — reuses `core/kg`, `tools/embeddings`, `tools/llm`, `core/cache`).

Full architecture: [`../docs/future/ai-learning-os.md`](../docs/future/ai-learning-os.md).

> **Phase 0 scope = foundations.** Broker + stores + event envelope + transactional outbox + a
> Gateway + a Content Ingestion service + a Chrome-extension skeleton. **Exit criterion:** clicking
> *Remember this* results in a `ContentSaved` event in the log.

## Layout

```
learning-os/
  los/                       importable Python package (dir name is hyphenated → package is `los`)
    domain_shared/           event envelope, ids, owner-scope helpers
    events/                  broker port (NATS JetStream + in-process) + event store + outbox
    db/                      async Postgres pool helper
    config.py                env-driven settings (dual-read, like the parent repo)
    services/
      gateway/               edge: JWT verify, routing, SSE passthrough
      ingestion/             POST /content → persist + append ContentSaved (outbox) → publish
  migrations/                SQL: 0001 event store + outbox, 0002 content
  contracts/                 AsyncAPI (events) — OpenAPI is served live at each service's /openapi.json
  extension/                 Chrome MV3 skeleton (auth + POST /v1/content)
  deploy/                    Dockerfile + docker-compose (nats, postgres, neo4j, qdrant, minio)
  tests/                     Phase-0 exit test (in-memory backends, no Docker needed)
```

## Design: every port has a memory + real backend

Mirrors the parent repo's `JOB_STORE=memory|supabase` idiom so the whole chain is testable without
infra:

| Port | `*_BACKEND=memory` (default in dev/test) | real backend |
|---|---|---|
| Broker (`los.events.broker`) | in-process asyncio fan-out | NATS JetStream (`BROKER_BACKEND=nats`) |
| Event store + outbox (`los.events.event_store`) | in-memory append-only list | Postgres (`EVENT_STORE_BACKEND=postgres`) |
| Content repo (`los.services.ingestion.adapters`) | in-memory dict | Postgres (`CONTENT_STORE_BACKEND=postgres`) |

## Run it

### Fast path — prove the exit criterion, no Docker
```bash
cd learning-os
pip install -e ".[test]"
pytest tests/test_ingestion_content_saved.py -v      # POST /content → ContentSaved appended + published
```

### Full stack — Docker
```bash
cd learning-os/deploy
cp ../.env.example ../.env        # then edit secrets
docker compose up -d              # nats, postgres, neo4j, qdrant, minio, gateway, ingestion
docker compose run --rm migrate   # apply migrations/*.sql
# Gateway on :8080, Ingestion on :8081 (internal). Load extension/ as an unpacked Chrome extension.
curl -XPOST localhost:8080/v1/content -H 'Authorization: Bearer <jwt>' \
  -d '{"url":"https://youtu.be/X","source_type":"youtube"}'
docker compose logs -f ingestion  # → "emitted ContentSaved …"
```

## Status

Phase 0 only. Transcript/Embedding/Concept/Knowledge-Graph/Learning-Asset services arrive in
Phase 1–2 (see the roadmap in the architecture doc). Nothing here touches the running clipping
product.
