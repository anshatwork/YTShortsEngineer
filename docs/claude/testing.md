# Testing

How to test this repo, what's covered, and the test taxonomy. See also
`.claude/skills/llm-evaluation.md` for the (future) prompt/LLM eval strategy.

## Layout & gotchas

- **`tests/`** — the maintained suite (long_to_shorts + SaaS surface). Run these.
- **Root `test_*.py`** — older legacy-workflow scripts. Many are `__main__` demo scripts, not
  pytest tests, and some make **live** network/model calls (`test_hook_workflow.py`). Don't run
  them in CI; they're manual/legacy.
- **No `conftest.py`** exists. Fixtures are declared inline per file. `pytest_output.txt` /
  `test_output.txt` are stale captured runs — ignore.
- **Known pre-existing redness:** the full `pytest tests/` run is red due to auth-ordering and a
  global task-queue singleton being shut down across `TestClient`s. **Validate per-file in
  isolation** (`pytest tests/test_x.py`), not the whole suite at once. (See the project memory
  note "Test suite pre-existing redness".)

## Running

```bash
# One file (the reliable way)
pytest tests/test_api.py -v

# A single test
pytest tests/test_credit_store.py::TestName::test_case -v

# Frontend
cd frontend && npm run lint && npm run build
```

Most `tests/` files mock external effects (FFmpeg, network, SDKs) and force in-memory stores
(`JOB_STORE`/`CREDIT_STORE`/`SUBSCRIPTION_STORE=memory`, `AUTH_DISABLED=1`). The one heavy
exception is `test_long_to_shorts.py`'s integration path, which runs **real FFmpeg** and needs
`assets/ailover.mp4`.

## What's covered (tests/)

| File | Layer | Notes |
|---|---|---|
| `test_api.py` | API / job lifecycle | routing, validation, queued→running→done/failed; `run_job` mocked |
| `test_billing_routes.py` | Billing | plans, Stripe+Razorpay checkout, signed webhooks, credit gate; SDKs mocked |
| `test_credit_store.py` | Credit ledger | in-memory primitives, `InsufficientCredits` |
| `test_credits_enforcement.py` | Credits meter | `enforce_and_debit`, `grant_for_plan`, snapshot |
| `test_edit_music.py` | Edit + FFmpeg | `/edit/add-music` + audio_mixer; ffmpeg/AudioFetcher patched |
| `test_edit_split.py` | Edit | `/edit/split-screen`; `compose_video`/`download_video` patched |
| `test_edit_tts.py` | Edit | `/edit/tts`; Chatterbox + intro builders patched |
| `test_glm_provider.py` | LLM provider | GLM (Z.ai); `requests.post` mocked |
| `test_hook_logic.py` | Legacy agents | ScriptGeneration + VideoSelection; HF mocked |
| `test_long_to_shorts.py` | **Graph** | (A) fully mocked unit tests, (B) real-ffmpeg integration |
| `test_music_cache.py` | Assets | placeholder-cred detection, Jamendo mapping, refresh, `/music/tracks` |
| `test_youtube_upload.py` | YouTube | OAuth signed-state, auth status, upload validation, job lifecycle |

## Test taxonomy for this project

1. **Unit — nodes.** Test `_<name>_impl` with a hand-built state dict; assert the returned
   partial state. Mock `get_llm()` and FFmpeg. Pattern: `test_long_to_shorts.py` (A). Cover the
   degrade-not-fail contract (per-clip error → `path` unchanged).
2. **Integration — API.** `fastapi.testclient.TestClient` with in-memory stores + `AUTH_DISABLED`.
   Assert status codes, validation (422/402/404/409), and the queued→done lifecycle with `run_job`
   mocked. Pattern: `test_api.py`, `test_edit_*`.
3. **Graph tests.** Drive `long_to_shorts_app.invoke(state)` with mocked tools to assert node
   ordering and state accumulation end-to-end.
4. **Prompt regression (future).** Golden inputs → structured outputs, asserted against a rubric
   or snapshot. Bump-`version` discipline is what these guard. See `docs/future/llm-judge.md`.
5. **LLM evaluation (future).** Scored (not asserted) quality over a small suite; provider
   comparison. `make evals`. See `docs/future/llm-judge.md`.
6. **Video pipeline tests.** Real FFmpeg on a tiny fixture (`assets/ailover.mp4`); assert output
   exists, is non-trivially sized, has the expected dimensions/streams (probe). Keep these
   opt-in/marked so CI without ffmpeg still passes.

## Writing new tests — conventions

- Force in-memory stores and `AUTH_DISABLED=1` via env at import/fixture time (see existing files).
- Mock at the boundary: `get_llm`, `tools.*` functions, `subprocess`/`ffmpeg`, SDK clients — not
  internal helpers.
- For money paths, assert **idempotency** (double webhook → single grant; failure → single refund)
  and **fail-open** (store error doesn't 500 the request).
- For SSE, assert the store `update` emits an event on the right channel rather than testing the
  socket.
- Prefer `tests/` (pytest) over adding another root-level `__main__` script.

## CI recommendation (not yet wired)

- `make lint typecheck` on every push.
- `pytest tests/ -p no:cacheprovider` **per-file** (a small script iterating files) until the
  shared-singleton redness is fixed, then whole-suite.
- `make evals` (once `docs/future/llm-judge.md` lands) gated on a threshold to catch prompt/model
  regressions. See `Makefile` targets in the repo root.
