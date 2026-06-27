# Inference & Hosting Cost Comparison — YTShortsEnginer

**Purpose:** decide the cheapest way to run inference for the live SaaS, comparing
three framings the team raised:

1. **Vercel + one EC2** (Ollama + ffmpeg on the same box)
2. **Vercel + GLM free inference**
3. **Vercel + OpenRouter credits** *or* **AWS Bedrock** for inference

> Prices are point-in-time **late June 2026**, us-east-1, USD. Token math uses the
> workload model in §3. Treat absolute numbers as ±20% planning estimates;
> the *relative* ordering and break-evens are the durable takeaways.

---

## 1. TL;DR / Recommendation

- **The framing hides the real cost.** Vercel can only host the Next.js
  **frontend**. Your FastAPI backend + the **ffmpeg / Whisper / yt-dlp** pipeline
  **cannot run on Vercel** (5–13 min function cap, no GPU, ephemeral FS, large
  binaries). So **every** option still needs a media-compute box. The three
  options differ *only in where the LLM runs* — not whether you need a server.
- **At low/medium volume, pay-per-token beats a GPU.** A small CPU box
  (~$61/mo) + a cheap strong model via **OpenRouter (GLM-4.6 ≈ $0.018/job)** comes
  to **~$108/mo at 50 jobs/day** and **~$189/mo at 200 jobs/day** — still cheaper
  than a 24/7 g4dn GPU (**~$404/mo flat**).
- **The GPU only wins** at *sustained high volume*, when you need **data to stay
  in-house** (no third-party LLM), or to exploit **NVENC** (GPU-accelerated
  ffmpeg) — which also slashes encode time, the pipeline's true hidden cost.
- **GLM "free" is not a SaaS backbone.** It's rate-limited (~1,000 req/day),
  has no SLA, sends user data to a third party (compliance risk for a paid
  product), and the Flash free models are weaker. Use it for **dev / fallback**,
  not as the paid path.

**Recommended launch stack:** Vercel (frontend) + **one small CPU EC2** (FastAPI +
ffmpeg) + **OpenRouter** as the default inference (swap models freely), **Bedrock**
as the all-AWS/compliance alternative, **BYOK** so power users bring their own key
(already built), and **GLM-free only for dev**. Revisit a GPU box only when
sustained volume crosses the break-even (§7) or encode throughput forces it.

---

## 2. Critical architecture note — what actually runs where

| Workload | Can run on Vercel? | Where it must run |
|---|---|---|
| Next.js frontend | ✅ Yes | Vercel |
| Light API routes (auth proxy) | ✅ Yes | Vercel (optional) |
| **FastAPI backend + job queue** | ❌ No (long-lived, stateful) | EC2 / container |
| **ffmpeg clip encoding** | ❌ No (minutes/clip, CPU/GPU heavy) | EC2 / container |
| **Whisper transcription** | ❌ No (heavy, optional GPU) | EC2 / container |
| **yt-dlp download** | ❌ No (long, large temp files) | EC2 / container |
| **LLM inference** | ❌ Not on Vercel itself | Ollama on EC2 **or** an API |

**Consequence:** "Vercel + GLM" and "Vercel + OpenRouter/Bedrock" both **silently
require a media box** for ffmpeg/Whisper. The only thing the inference choice
changes is whether that box needs a **GPU** (Option 1) or can be a **cheap CPU
box** (Options 2 & 3).

---

## 3. Workload model & assumptions

One **job** = 1 source video (~10 min) → ~5 short clips. Per job:

- **Transcript:** YouTube captions when available (free); Whisper only as fallback.
- **LLM calls:** `analyze_video` (hook-scores transcript, chunked) +
  `content_gen` (title/summary/hook/hashtags **per clip** × 5) + optional thumbnail.
- **Token estimate (generous):** **~20K input + ~5K output tokens / job.**
- **ffmpeg:** 5 clips × ~30–60 s, 1080×1920. CPU (libx264) = minutes; GPU (NVENC) = ~5–10× faster.

Volume tiers used below: **10/day (300/mo)**, **50/day (1,500/mo)**, **200/day (6,000/mo)**.

---

## 4. Component pricing reference (June 2026)

**Compute (on-demand, us-east-1):**

| Instance | Role | $/hr | $/mo (24/7) |
|---|---|---|---|
| `g4dn.xlarge` (T4 GPU) | Ollama + NVENC ffmpeg | $0.526 | **~$384** |
| `t3.large` (2 vCPU/8GB) | CPU ffmpeg + API | $0.0832 | **~$61** |
| `c7i.xlarge` (4 vCPU) | faster CPU ffmpeg | ~$0.17 | **~$122** |

**Inference (per 1M tokens, in/out):**

| Model / route | Input | Output | ≈ $/job (20K/5K) |
|---|---|---|---|
| **Ollama** (self-host on GPU) | $0 marginal | $0 marginal | $0 (+ fixed GPU) |
| **OpenRouter — GLM-4.6** | $0.43 | $1.74 | **~$0.018** (incl. 5.5% credit fee) |
| **OpenRouter — Llama 3.3 70B :free** | $0 | $0 | $0 (rate-limited) |
| **Bedrock — Claude Haiku 4.5** | $1 | $5 | **~$0.05** |
| **Bedrock — Claude Sonnet 4.6** | $3 | $15 | **~$0.135** |
| **Bedrock — Llama 3 70B** | $2.65 | $3.50 | ~$0.07 (+~10% cross-region) |
| **GLM free (GLM-4.7-Flash / 5.1 free)** | $0 | $0 | $0 (~1,000 req/day cap) |

**Platform:**

- **Vercel Pro:** **$20/mo** (commercial SaaS needs Pro; Hobby is non-commercial),
  $20 included credit, 1 TB transfer then $0.15/GB, functions cap **5 min**
  (13 min with Fluid Compute) — still far short of a full job.
- **OpenRouter:** passthrough token prices + **5.5% fee on credit purchase**;
  free models give 50 req/day, or 1,000/day after a one-time $10 top-up.
- **GLM free (Z.ai):** GLM-4.7-Flash / GLM-4.5-Flash fully free; GLM-5.1 free at
  ~1,000 req/day. No SLA; ToS/availability can change.
- **Storage/egress (common to all):** S3 + CloudFront ≈ **$10–30/mo** at launch
  with lifecycle expiry; identical across options, so omitted from the deltas below.

---

## 5. The three options in detail

### Option 1 — Vercel + one EC2 (Ollama + ffmpeg), GPU `g4dn.xlarge`

**Architecture:** Vercel frontend → one **GPU EC2** that runs FastAPI + ffmpeg
(NVENC) **and** Ollama (`qwen2.5:7b`). Inference is $0 marginal.

**Cost:** Vercel $20 + GPU. GPU is the swing factor:
- 24/7: **~$404/mo flat** (volume-independent).
- Stopped when idle (e.g. ~8 h/day via EventBridge/scale-to-zero): **~$148/mo** —
  but only feasible at low volume; busy days erase the savings.

**Pros:** no per-token cost; **data never leaves your infra** (privacy/compliance);
**GPU accelerates both LLM and encode** (NVENC ~5–10× faster ffmpeg → higher
throughput per box); fully predictable bill.

**Cons:** brutal **idle cost** (~$384/mo even at 1 job/day if left on); real
**ops burden** (GPU drivers, Ollama, model pulls, patching); single point of
failure; scaling = bigger/more GPUs; cold-start latency if you stop/start; 7B
local model quality < Sonnet.

---

### Option 2 — Vercel + GLM free inference

**Architecture:** Vercel frontend → **CPU EC2** (FastAPI + ffmpeg, *still required*)
→ GLM **free** API (GLM-4.7-Flash / GLM-5.1 free) for LLM.

**Cost:** Vercel $20 + `t3.large` $61 + inference **$0** = **~$81/mo**.

**Pros:** lowest headline cost; no GPU; near-zero inference spend while the free
tier lasts.

**Cons / why it's not a paid backbone:**
- **Rate-limited** ~1,000 req/day ≈ **~100 jobs/day** ceiling (each job is ~10
  calls) — caps growth.
- **No SLA**; the free tier can be throttled, changed, or revoked at any time.
- **Data leaves to a third party** (Z.ai/Zhipu) — a real **compliance/privacy**
  problem when you're charging customers.
- **Weaker models** (Flash) → lower title/hook quality, the thing users pay for.
- CPU ffmpeg (no NVENC) is slower → longer encodes, but the box is cheap.

**Verdict:** fine for **dev/prototyping or an emergency fallback**; **not** the
revenue path.

---

### Option 3 — Vercel + OpenRouter credits *or* AWS Bedrock

**Architecture:** Vercel frontend → **CPU EC2** (FastAPI + ffmpeg, *still required*)
→ pay-per-token API. Two flavors:

**3a. OpenRouter** — one key, 300+ models, switch model via config; cheap strong
models (GLM-4.6 ≈ $0.018/job). 5.5% fee on credit top-ups. Free models available
as a fallback tier.

**3b. AWS Bedrock** — Claude Haiku/Sonnet, Llama, Nova; **stays inside AWS**
(IAM, VPC, no data egress to a third party), batch -50%, provisioned throughput
options. Higher per-token than OpenRouter passthrough.

**Cost:** Vercel $20 + `t3.large` $61 + inference (see tables). Pennies–low-$ at
launch volumes.

**Pros:** elastic, **no GPU ops**, pay only for use; **top-tier model quality**
(Sonnet/Haiku); Bedrock keeps **data in AWS** (compliance); OpenRouter gives
**flexibility + lowest per-token**; both integrate with the **BYOK** path already
built (users can offload their own usage).

**Cons:** per-token cost **grows with volume** (a GPU eventually wins at scale);
depends on an external API (OpenRouter adds a vendor hop → privacy/SLA nuance;
Bedrock avoids that but costs more/token); needs spend caps to avoid abuse.

---

## 6. Side-by-side monthly cost (excludes common ~$10–30 storage)

Fixed = Vercel $20 + media box. Inference scales with volume.

### At 50 jobs/day (1,500/mo)

| Option | Fixed | Inference | **Total** | Notes |
|---|---|---|---|---|
| Opt 2 — GLM free + t3.large | $81 | $0 | **~$81** | rate-limit/quality/compliance risk |
| Opt 3a — OpenRouter GLM-4.6 + t3.large | $81 | $27 | **~$108** | best $/quality balance |
| Opt 1 — GPU, idle-managed | $20 | $0 | **~$148** | only if genuinely idle off-peak |
| Opt 3b — Bedrock Haiku + t3.large | $81 | $68 | **~$149** | all-AWS, strong quality |
| Opt 3b — Bedrock Sonnet + t3.large | $81 | $203 | **~$284** | premium quality |
| Opt 1 — GPU 24/7 | $404 | $0 | **~$404** | flat regardless of volume |

### At 200 jobs/day (6,000/mo)

| Option | Fixed | Inference | **Total** | Notes |
|---|---|---|---|---|
| Opt 3a — OpenRouter GLM-4.6 + t3.large | $81 | $108 | **~$189** | still beats the GPU |
| Opt 3b — Bedrock Haiku + t3.large | $81 | $270 | **~$351** | approaching GPU cost |
| Opt 1 — GPU 24/7 | $404 | $0 | **~$404** | now competitive; NVENC bonus |
| Opt 3b — Bedrock Sonnet + t3.large | $81 | $810 | **~$891** | premium only |
| Opt 2 — GLM free | — | — | **not viable** | exceeds ~100 jobs/day cap |

> At 200/day a single `t3.large` likely can't keep up with encoding — you'd need
> `c7i.xlarge` (+$61) or a second box, narrowing the gap to the GPU further (and
> making NVENC attractive). See §8.

---

## 7. Break-even analysis (vs. a 24/7 GPU at ~$404/mo)

A pay-per-token option costs `media_box + Vercel + (jobs × $/job)`. Solving for
when it equals the GPU's flat **$404/mo** (using `t3.large + Vercel = $81`):

| API choice | $/job | Break-even jobs/mo | ≈ jobs/day |
|---|---|---|---|
| OpenRouter GLM-4.6 | $0.018 | (404−81)/0.018 ≈ **17,900** | **~600/day** |
| Bedrock Haiku 4.5 | $0.05 | ≈ **6,460** | **~215/day** |
| Bedrock Sonnet 4.6 | $0.135 | ≈ **2,390** | **~80/day** |

**Reading it:** with a cheap strong model (OpenRouter GLM), the API path stays
cheaper than an always-on GPU until **~600 jobs/day**. Even Bedrock Haiku holds to
**~215/day**. Only **premium Sonnet** flips early (~80/day) — and there the answer
is "use Haiku/GLM for the bulk, Sonnet only where quality matters," not "buy a GPU."

If you **idle-manage** the GPU (~$148/mo) the break-evens drop, but idling only
works at *low* volume — exactly where the API path is already cheapest. The GPU's
real edge is **privacy/no-third-party** and **NVENC encode throughput**, not raw
inference price until you're very large.

---

## 8. The hidden constant: ffmpeg & Whisper

Inference is the *small* part of a job; **encoding is the heavy, ever-present
cost** — and it exists in all three options:

- **CPU (libx264, current code):** minutes per clip; a `t3.large` handles low
  volume but becomes the bottleneck by ~50–200 jobs/day → bigger box or more boxes.
- **GPU (NVENC, `h264_nvenc`):** ~5–10× faster encode. This is the **under-rated
  reason** to own a GPU — it accelerates *encoding*, not just the LLM. The current
  pipeline uses libx264; switching to NVENC on a GPU box is a config/flag change.
- **Whisper:** prefer YouTube captions (free). When transcribing, CPU `base` is OK
  at low volume; offload to a cheap STT API (e.g. hosted Whisper) or the GPU at scale.

**Implication:** if you grow to where a GPU makes sense, you get *two* wins at once
(LLM + NVENC). Below that, a CPU box + API inference is both cheaper and simpler.

---

## 9. Recommendation & phased path

1. **Launch (unknown/low volume):** **Option 3a** — Vercel + `t3.large`
   (FastAPI + ffmpeg) + **OpenRouter** default model (GLM-4.6 for cost, Haiku/Sonnet
   selectable per quality need). Cheapest, flexible, no GPU ops. **~$80–110/mo + storage.**
2. **Compliance-sensitive customers:** flip the default to **Bedrock** (data stays
   in AWS) — same architecture, swap the provider. Your code's provider abstraction
   (`tools/llm`) + the **BYOK** path already support this.
3. **GLM-free:** wire only as a **dev/fallback** provider, never the paid backbone.
4. **Scale trigger → add a GPU (Option 1):** when sustained volume passes the §7
   break-even **or** CPU encoding can't keep up. Then run **Ollama + NVENC** on the
   GPU for the double win, and keep the API path for burst/overflow and BYOK.

This is a slight, deliberate revision of the earlier "GPU-default" launch
assumption: the numbers say **start API-first on a cheap CPU box**, and treat the
GPU as a *scale* decision, not a *launch* one.

---

## Sources

- [AWS EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/) ·
  [g4dn.xlarge ~$383.98/mo](https://www.economize.cloud/resources/aws/pricing/ec2/g4dn.xlarge/) ·
  [g4dn.xlarge specs/pricing (Vantage)](https://instances.vantage.sh/aws/ec2/g4dn.xlarge) ·
  [t3.large pricing (Vantage)](https://instances.vantage.sh/aws/ec2/t3.xlarge)
- [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) ·
  [Bedrock 2026 model costs (TokenMix)](https://tokenmix.ai/blog/aws-bedrock-pricing) ·
  [Claude platform pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [OpenRouter models](https://openrouter.ai/models) ·
  [OpenRouter GLM-4.6 pricing](https://openrouter.ai/z-ai/glm-4.6) ·
  [Lowest-cost inference guide (OpenRouter)](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/) ·
  [OpenRouter pricing overview (CostBench)](https://costbench.com/software/llm-api-providers/openrouter/)
- [Z.ai GLM free tiers & limits (TokenMix)](https://tokenmix.ai/blog/glm-free-api-access-tiers-2026) ·
  [Z.AI developer docs](https://docs.z.ai/devpack/overview)
- [Vercel pricing](https://vercel.com/pricing) ·
  [Vercel limits](https://vercel.com/docs/limits) ·
  [Vercel Pro plan](https://vercel.com/docs/plans/pro-plan)
