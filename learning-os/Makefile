# AI Learning OS — dev targets. Run from learning-os/.
.PHONY: install test run-gateway run-ingestion up down migrate logs

install:
	pip install -e ".[test]"

# Phase 0 exit criterion — no Docker required (in-memory backends).
test:
	pytest tests/ -v

run-gateway:
	uvicorn los.services.gateway.app.main:app --reload --port $${GATEWAY_PORT:-8080}

run-ingestion:
	uvicorn los.services.ingestion.app.main:app --reload --port $${INGESTION_PORT:-8081}

up:
	cd deploy && docker compose up -d

down:
	cd deploy && docker compose down

migrate:
	cd deploy && docker compose run --rm migrate

logs:
	cd deploy && docker compose logs -f gateway ingestion
