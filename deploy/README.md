# Deploy — single-EC2 launch topology

The cheapest live setup: **one EC2** running the API + pipeline workers in Docker
behind **Caddy** (auto-HTTPS). Ollama runs on a **separate GPU EC2**; Supabase and
S3/CloudFront are managed. See `../<plan>` for the full architecture.

```
Browser ──► Cloudflare Pages / Amplify (Next.js frontend)
                       │  NEXT_PUBLIC_API_URL
                       ▼
        Caddy (443, TLS) ──► api:8000  (FastAPI + ThreadPool workers)   ← this EC2
                       │
       ┌───────────────┼────────────────────────┐
       ▼               ▼                         ▼
  GPU EC2 :11434   Supabase (DB+Auth)      S3 + CloudFront (clips)
  (Ollama, private)  (managed)             (signed URLs, lifecycle expiry)
```

## 1. Provision

- **App EC2**: start with `t3.large` (2 vCPU / 8 GB). ffmpeg is CPU-bound — size up
  to `c7i.xlarge`/`c6i` if encode latency hurts. Install Docker + compose plugin.
- **GPU EC2**: `g4dn.xlarge`, private subnet, security group allowing **11434 only
  from the app EC2's SG**. Install Ollama + `ollama pull qwen2.5:7b-instruct`.
  **Do not leave it running 24/7** — schedule start/stop via EventBridge, or wire
  scale-to-zero later.
- **DNS**: point `api.example.com` at the app EC2's elastic IP.

## 2. Configure secrets on the box

Create `/opt/ytshorts/.env` (gitignored; or render it from SSM/Secrets Manager at
boot). Required variables:

```bash
# --- Caddy / TLS ---
DOMAIN=api.example.com
ACME_EMAIL=you@example.com
FRONTEND_URL=https://app.example.com         # CORS allow-list (no trailing slash)
ENVIRONMENT=production                        # disables /docs, tightens config

# --- Supabase (rotate the keys that were committed!) ---
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...

# --- LLM: default GPU Ollama (private IP of the GPU EC2) ---
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://10.0.x.x:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
ENABLE_LLM_FALLBACK=false                     # don't silently fall back off-box

# --- BYOK credential encryption (Phase 2) ---
BYOK_FERNET_KEY=...                           # cryptography.fernet.Fernet.generate_key()

# --- Storage (Phase 3) ---
BLOB_STORE_BACKEND=s3
BLOB_S3_BUCKET=ytshorts-artifacts
BLOB_S3_REGION=us-east-1
CLOUDFRONT_DOMAIN=dxxxx.cloudfront.net
CLOUDFRONT_KEY_PAIR_ID=...
CLOUDFRONT_PRIVATE_KEY_PATH=/run/secrets/cf_private_key.pem

# --- External APIs ---
YT_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YOUTUBE_OAUTH_REDIRECT_URI=https://api.example.com/api/v1/youtube/auth/callback
JAMENDO_CLIENT_ID=...

# --- Payments (Phase 5) ---
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...

# --- Encode tuning (predictable resource use) ---
CLIP_X264_PRESET=veryfast
CLIP_WORKER_THREADS=2
WORKER_THREADS=2
```

> The app loads `.env` automatically (see `agents/long_to_shorts/api/app.py`).
> Prefer rendering this file from SSM Parameter Store (SecureString) at instance
> boot so secrets never sit in git or an AMI.

## 3. Run

```bash
docker compose up -d --build
docker compose logs -f api
curl -fsS https://api.example.com/health
```

## 4. Notes

- Concurrency = in-process `WORKER_THREADS`; the task queue is in-memory, so run a
  **single** api container until `TASK_QUEUE_BACKEND` moves to SQS/Celery.
- Logs go to container stdout (json-file, rotated) **and** `./logs` on the host.
  Run the CloudWatch agent on the host to ship them; set log-group retention.
- `OUTPUT_DIR`/`ASSET_CACHE_DIR` are ephemeral `/tmp` scratch — finished clips are
  uploaded to S3 and served via CloudFront signed URLs.
