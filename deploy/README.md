# Hosted deployment

This is the launch topology: one small CPU host for the API, ffmpeg, and
in-process workers. Ollama and the learning OS are not deployed.

```text
Cloudflare Pages (Next.js)
          |
     Caddy + TLS
          |
FastAPI + ffmpeg host ---- OpenRouter
          |                Supabase Auth/Postgres
          +---------------- S3 + CloudFront
```

## Launch configuration

Use a Lightsail 2 vCPU/2 GB instance or equivalent. Increase memory before
increasing worker concurrency. Run one API container because the task queue and
event bus are process-local at launch.

```dotenv
ENVIRONMENT=production
FRONTEND_URL=https://app.example.com
DOMAIN=api.example.com
ACME_EMAIL=ops@example.com

JOB_STORE=supabase
SUBSCRIPTION_STORE=supabase
CREDIT_STORE=supabase
QUOTA_ENABLED=true
CREDITS_ENABLED=true
PLAN_FREE_MONTHLY_JOBS=3
CREDITS_GRANT_FREE=30
CREDITS_COST_CLIP=10

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=...
OPENROUTER_MAX_TOKENS=1024
OPENROUTER_TIMEOUT=60
ENABLE_LLM_FALLBACK=false
LLM_LOCAL_ONLY=false

BLOB_STORE_BACKEND=s3
BLOB_S3_BUCKET=ytshorts-artifacts
BLOB_S3_REGION=...
CLOUDFRONT_DOMAIN=...

TASK_QUEUE_BACKEND=threadpool
EVENT_BUS_BACKEND=memory
WORKER_THREADS=2
```

Store secrets in SSM/Secrets Manager and render the runtime environment at
boot. Do not put `.env` in an image, AMI, or repository.

## Production checklist

1. Rotate previously exposed Supabase, Google, OpenRouter, and payment secrets.
2. Apply every migration in `supabase/migrations/`, including `013_payment_events.sql`.
3. Set Supabase Auth site and redirect URLs to the production frontend.
4. Use a private S3 bucket, CloudFront Origin Access Control, signed URLs, and
   a 7–30 day artifact lifecycle rule.
5. Restrict the host firewall to 80/443 and administrator SSH only.
6. Start with test-mode Stripe and Razorpay webhooks; switch to live secrets
   only after the end-to-end payment tests pass.
7. Confirm `/health`, signup, job submission, signed download, quota rejection,
   checkout, and webhook replay behavior.

## Scaling path

When queue depth or job age requires more capacity:

- Persist the job before enqueueing it.
- Move queue work to a durable managed broker and run separate API and worker
  services. The current thread pool is intentionally launch-only.
- The first supported hosted adapter is SQS: set `TASK_QUEUE_BACKEND=sqs`,
  provide `TASK_QUEUE_URL`, and run `python scripts/sqs_worker.py` in worker
  containers with a dead-letter queue configured.
- Keep Supabase `cache_entries` as the shared metadata index and S3 as the
  shared blob store; add Redis only for hot locks, rate limits, and ephemeral
  progress fan-out.
- Replace the process-local event bus with Redis Pub/Sub or managed realtime
  before running multiple API replicas.
- Scale ffmpeg workers and inference workers independently, with queue-depth
  autoscaling and bounded concurrency.
- Make retries idempotent using job IDs and content-addressed cache keys.

## Payments

Stripe uses hosted Checkout and signed webhooks. Razorpay handles India and
UPI Autopay subscriptions. A browser redirect never activates a subscription;
only a verified webhook may do that. `payment_events` provides durable event
deduplication, while the credit ledger remains the balance source of truth.

## Supabase retention

Preserve users, subscriptions, credits, credentials, and successful uploads.
Archive or delete expired cache rows, failed/abandoned jobs, old execution
journals, stale trend data, and orphaned rows according to the retention policy.
Export first; never truncate `auth.users` as part of routine cleanup.
