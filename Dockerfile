# syntax=docker/dockerfile:1
#
# Backend image for the Long-to-Shorts API + in-process pipeline workers.
# Runs FastAPI (uvicorn) and the ThreadPool job runners in one container.
#
# Build:  docker build -t ytshorts-api .
# Run:    docker run --env-file .env -p 8000:8000 ytshorts-api
#
FROM python:3.11-slim AS base

# ffmpeg (with libass for subtitle burning) + fonts for the ASS overlay filter.
# We install the real apt ffmpeg rather than relying solely on imageio-ffmpeg's
# static binary, which lacks the libass build the subtitles node needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first so the layer caches across code changes.
# Force the CPU torch wheel — the app box has no GPU (Ollama/Whisper-GPU live on
# the separate GPU EC2). This avoids pulling the ~2GB CUDA wheel onto the API box.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# Pre-bake the Whisper model so the first subtitles job doesn't block on a
# ~140MB download. Override the tag with WHISPER_MODEL at build time if needed.
ARG WHISPER_MODEL=base
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}')"

# App source.
COPY . .

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs /tmp/output /tmp/assets \
    && chown -R appuser:appuser /app /tmp/output /tmp/assets
USER appuser

EXPOSE 8000

# Default runtime env — override via --env-file / compose. OUTPUT_DIR and
# ASSET_CACHE_DIR point at ephemeral scratch; finished artifacts go to S3
# (BLOB_STORE_BACKEND=s3) in production.
ENV PORT=8000 \
    OUTPUT_DIR=/tmp/output \
    ASSET_CACHE_DIR=/tmp/assets \
    LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

# Single process; concurrency comes from the in-process ThreadPool workers
# (WORKER_THREADS), not from uvicorn workers — the task queue is in-memory and
# must stay in one process until TASK_QUEUE_BACKEND moves to SQS/Celery.
CMD ["sh", "-c", "uvicorn agents.long_to_shorts.api.app:app --host 0.0.0.0 --port ${PORT}"]
