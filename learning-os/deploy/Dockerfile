# Shared image for all Python services. The compose file overrides CMD per service.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install deps first for layer caching, then the source.
COPY pyproject.toml ./
COPY los ./los
RUN pip install --upgrade pip && pip install -e "."

EXPOSE 8080 8081

# Default = gateway; ingestion overrides this in docker-compose.
CMD ["uvicorn", "los.services.gateway.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
