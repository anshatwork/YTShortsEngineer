# Remember this — Chrome extension (Phase 0 skeleton)

One action: **Remember this** → `POST /v1/content` on the gateway.

## Load it
1. `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select this folder.
2. Click the toolbar icon → **Settings** → set Gateway URL (`http://localhost:8080` for the local
   stack) and, in prod, paste a Supabase JWT. In dev (`AUTH_DISABLED=1`) the token can be blank.
3. Click **Remember this page**, or right-click → **Remember this**.

## What it does
- Detects the active tab URL, classifies it (`youtube` / `youtube_shorts` / `article`), and POSTs it.
- Shows whether it was newly saved or already remembered (idempotent capture).

> Add an `icon128.png` before publishing (notifications reference it). Not required to load unpacked.
