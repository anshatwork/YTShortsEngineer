# Deploy — Phase 0 stack

```bash
cd learning-os/deploy
docker compose up -d              # postgres, nats(JetStream), neo4j, qdrant, minio, gateway, ingestion
docker compose run --rm migrate   # apply ../migrations/*.sql
docker compose ps
```

Smoke test the exit criterion (AUTH_DISABLED=1 → dev owner):

```bash
curl -s -XPOST localhost:8080/v1/content \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","source_type":"youtube"}' | jq
# → {"content_id":"…","status":"saved","created":true}

docker compose logs ingestion | grep -E "appended ContentSaved|emitted ContentSaved"
```

Inspect the durable log:

```bash
docker compose exec postgres psql -U los -d learning_os \
  -c "select type, stream, seq, owner_id from domain_events order by occurred_at;"
docker compose exec postgres psql -U los -d learning_os \
  -c "select event_id, published from outbox;"
```

NATS JetStream monitoring: http://localhost:8222 · MinIO console: http://localhost:9001 ·
Neo4j Browser: http://localhost:7474 (Phase 1).

## Notes
- `gateway` and `ingestion` share one image (`Dockerfile`); the CMD differs per service.
- `ingestion` runs the **real** backends (NATS + Postgres); `gateway` is stateless.
- Neo4j/Qdrant/MinIO are declared for Phase 1+ and are not yet consumed.
