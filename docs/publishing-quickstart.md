# Publishing Quickstart — upload directly to YouTube

How to go from "nothing configured" to a Short published on your channel through
the Autonomous Publishing Agent. Two one-time setup phases (Google + env), then
the run itself. Verified against `agents/long_to_shorts/api/youtube_oauth.py`,
`youtube_routes.py`, `youtube_upload_runner.py`, and `docs/go-live-setup.md`.

---

## 1. Google Cloud Console (one-time)

1. **Create a project** → APIs & Services → **Enable "YouTube Data API v3"**.
2. **API key** (Credentials → Create → API key). This powers search/discovery.
   Restrict it to the YouTube Data API. → sets `YT_API_KEY`.
3. **OAuth client** (Credentials → Create → **OAuth client ID → Web application**).
   Add an **Authorized redirect URI** that EXACTLY matches your backend callback:
   - local dev: `http://localhost:8000/api/v1/youtube/auth/callback`
   - production: `https://api.<your-domain>/api/v1/youtube/auth/callback`

   Copy the client id + secret → `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
4. **OAuth consent screen**: set app name, support email, a privacy-policy URL and
   terms URL, and add the two scopes the app requests:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.readonly`

   These are **restricted** scopes. While your app is unverified (Testing mode):
   - add yourself under **Test users** (only test users can connect);
   - uploads land as **private** regardless of the privacy you request;
   - refresh tokens **expire after 7 days** (you'll re-connect).

   Lifting these limits requires Google's OAuth verification (demo video +
   justification, and a CASA security review above a user threshold).

---

## 2. Environment (`.env`)

```dotenv
# Search / discovery
YT_API_KEY=your_youtube_data_api_key

# OAuth (Connect YouTube). Redirect URI MUST match what you registered above.
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
YOUTUBE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/youtube/auth/callback

# Where the OAuth callback bounces the browser back to
FRONTEND_URL=http://localhost:3000

# Signs the OAuth state token (also your app's auth JWT secret)
SUPABASE_JWT_SECRET=your_supabase_jwt_secret

# Persistence so connected accounts + jobs survive a restart (else in-memory).
JOB_STORE=supabase
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Notes
- Run the SQL migrations in `supabase/migrations/` (incl. `011_publishing.sql`) so
  publishing runs + YouTube credentials persist.
- For a quick local trial without Supabase you can set `AUTH_DISABLED=true` and
  leave `JOB_STORE=memory`, but connected YouTube credentials then live only in
  memory (lost on restart).
- Local Ollama inference: set `LLM_PROVIDER=ollama` and pull the tier models
  (`INFERENCE_MODEL_SMALL/MEDIUM/LARGE`). Or set `LLM_PROVIDER=claude` +
  `ANTHROPIC_API_KEY` to run in the cloud.

---

## 3. Start the app

```bash
# Backend (http://localhost:8000, /docs when not production)
python agents/long_to_shorts/api/server.py --reload
# Frontend (http://localhost:3000)
cd frontend && npm run dev
# or both together on Windows:
start.bat
```

---

## 4. Connect your YouTube account (one-time per user)

In the web app, click **Connect YouTube** (top-right of the navbar, also offered
at the upload gate). This calls `GET /api/v1/youtube/auth/login`, redirects you to
Google's consent screen, and Google returns to
`GET /api/v1/youtube/auth/callback`, which stores your refresh token and bounces
you back with `?youtube=connected`. Verify via **Settings**/status
(`GET /api/v1/youtube/auth/status` → `connected: true`).

---

## 5. Run the Autonomous Publishing flow

1. Go to **PUBLISH** in the nav (`/publishing`).
2. Type what you want, e.g. *"today's best AI agent explainers under an hour"*,
   set candidates/clips, **Start run**. (Autonomous discovery begins.)
3. **Decision #1 — approve a source.** When the run reaches
   *Needs source approval*, you'll see ranked candidate videos with a rationale
   (why chosen, expected clip quality, hook potential, relevance). Click
   **Approve** on one (or **Refresh** for new candidates). The agent then
   generates clips, scores them, and evaluates the best one automatically.
4. **Decision #2 — approve the upload.** At *Needs upload approval* you'll see the
   auto-selected clip (with a video preview), its metadata, and the evaluation
   report. Optionally **Edit metadata**, then **Approve & upload** (or
   **Regenerate** / **Reject**).
5. When the run reaches **Complete**, the page shows a **Watch ↗** link to the
   live video.

Everything between the two approvals — search, ranking, generation, scoring,
evaluation, and any revision passes — is autonomous.

### Prerequisites the upload enforces (from the code)
- **Connected account** — else `409 "YouTube not connected"`.
- **A rendered clip file** — the selected clip must have a produced `path` on disk
  (the pipeline creates it), else `422`.
- The upload is **resumable + idempotent** (keyed on user + file signature + title
  + privacy), so a retry after a crash reconciles to the existing video instead of
  double-publishing.

### Doing it manually (without the agent)
You can still publish any individual clip directly: generate clips via a normal
job, then `POST /api/v1/youtube/upload` with `{parent_job_id, clip_id, title, …}`
(the frontend's per-clip **Publish** dialog does this). Same OAuth + rendered-file
prerequisites apply.

---

## 6. Programmatic / MCP

Connected via the MCP connector (Claude.ai / ChatGPT), the same flow is available
as tools: `start_publishing` → poll `get_publishing` → `approve_source` →
`approve_upload`. Note the connector cannot run the OAuth flow itself — connect
YouTube once in the web app first.
