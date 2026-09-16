# Contracts

- **Events (AsyncAPI):** [`asyncapi/learning-os.yaml`](asyncapi/learning-os.yaml) — the domain-event
  envelope + `ContentSaved`. Validate with `npx @asyncapi/cli validate asyncapi/learning-os.yaml`.
- **REST (OpenAPI):** served live by each FastAPI service at `/openapi.json` (and `/docs`):
  - Gateway: `http://localhost:8080/openapi.json`
  - Ingestion: `http://localhost:8081/openapi.json`

Contract tests (Phase 1) assert every consumer honors the envelope and that envelope `version`
changes are handled explicitly.
