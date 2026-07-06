"""
agents/long_to_shorts/api/mcp_server.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Remote MCP server exposing the Long-to-Shorts pipeline as a *custom connector*
for Claude.ai and ChatGPT.

Design
------
- Transport: Streamable HTTP (``mcp.http_app``), mounted onto the existing
  FastAPI app at ``/mcp`` (see app.py). Same process ⇒ tools reuse the running
  task queue and stores.
- Auth: FastMCP ``SupabaseProvider`` (see mcp_auth). The MCP token is a Supabase
  JWT whose ``sub`` is the app user_id; tools forward it into the routes.
- Every tool is a thin wrapper over an existing ``/api/v1`` endpoint via
  ``mcp_client.call_api`` — no business logic lives here, so behaviour matches
  the REST API exactly (validation, quota, ownership).

Async jobs
----------
Clip extraction, edits and uploads run in the background. Tools follow a
submit → poll shape: ``submit_shorts_job`` returns a ``job_id`` immediately;
call ``get_job_status`` (or the convenience ``wait_for_job``) until
``status == "done"``. Result artifact paths are rewritten to absolute
``MCP_PUBLIC_URL/static/...`` URLs so the model can hand back a working link.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from agents.long_to_shorts.api.mcp_auth import build_auth_provider, current_bearer
from agents.long_to_shorts.api.mcp_client import call_api

_INSTRUCTIONS = (
    "Turn long videos (YouTube URLs or already-uploaded files) into short 9:16 "
    "clips, then optionally add narration, music, thumbnails or split-screen, and "
    "publish to YouTube. Clip extraction is asynchronous: submit_shorts_job returns "
    "a job_id; poll get_job_status (or call wait_for_job) until status is 'done', "
    "then read the clips array. Use search/fetch to look up a user's past jobs and "
    "clips by keyword or id."
)

mcp: FastMCP = FastMCP(name="YTShortsEngine", instructions=_INSTRUCTIONS, auth=build_auth_provider())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output")).resolve()


def _public_base() -> str:
    return os.getenv("MCP_PUBLIC_URL", "").strip().rstrip("/")


def _to_url(fs_path: Optional[str]) -> Optional[str]:
    """Rewrite an absolute artifact path under OUTPUT_DIR into a public URL.

    Mirrors edit_runner._to_static_url (path → /static/...), then prefixes
    MCP_PUBLIC_URL so the model returns a directly openable link. Paths outside
    OUTPUT_DIR (shouldn't happen) or when no public base is set fall back to the
    relative /static path.
    """
    if not fs_path:
        return fs_path
    try:
        rel = Path(fs_path).resolve().relative_to(_output_dir())
        static_path = "/static/" + rel.as_posix()
    except ValueError:
        return fs_path
    base = _public_base()
    return base + static_path if base else static_path


def _rewrite_job(job: dict[str, Any]) -> dict[str, Any]:
    """Rewrite clip artifact paths in a JobStatus dict to public URLs."""
    for clip in job.get("clips") or []:
        if isinstance(clip, dict):
            clip["url"] = _to_url(clip.get("path"))
            clip["thumbnail_url"] = _to_url(clip.get("thumbnail_path"))
    return job


async def _json(method: str, path: str, **kwargs) -> Any:
    """Call the in-process API forwarding the caller's token; raise on error.

    Surfaces the API's own ``detail`` message as a ToolError so the model gets a
    clear, actionable reason (e.g. quota exceeded, not found, YouTube not
    connected) rather than an opaque failure.
    """
    resp = await call_api(method, path, token=current_bearer(), **kwargs)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise ToolError(f"{method} {path} failed ({resp.status_code}): {detail}")
    if resp.status_code == 204 or not resp.content:
        return {"ok": True}
    return resp.json()


# ---------------------------------------------------------------------------
# Core clip jobs
# ---------------------------------------------------------------------------

@mcp.tool
async def submit_shorts_job(
    youtube_url: Optional[str] = None,
    video_path: Optional[str] = None,
    top_n: int = 3,
    add_subtitles: bool = False,
    subtitle_position: str = "bottom",
    subtitle_size: str = "medium",
    add_top_text: bool = False,
    add_thumbnail: bool = False,
    thumbnail_style: str = "auto",
    add_intro: bool = True,
    add_music: bool = False,
    music_volume_db: float = -18.0,
    clip_mode: str = "portrait",
    user_context: Optional[str] = None,
) -> dict:
    """Submit a job that extracts the best 9:16 short clips from a long video.

    Provide EXACTLY ONE source: a `youtube_url` OR a server-side `video_path`
    (from a prior upload). Returns a job record with a `job_id` and status
    'queued'; poll `get_job_status` until 'done'. `top_n` (1-20) caps the number
    of clips. Optional flags burn subtitles / hook text, generate thumbnails,
    prepend a title intro, or mix background music. `clip_mode` is 'portrait'
    (9:16 reframed) or 'fullscreen'. `user_context` steers clip selection and copy.
    """
    body = {
        "youtube_url": youtube_url,
        "video_path": video_path,
        "top_n": top_n,
        "add_subtitles": add_subtitles,
        "subtitle_position": subtitle_position,
        "subtitle_size": subtitle_size,
        "add_top_text": add_top_text,
        "add_thumbnail": add_thumbnail,
        "thumbnail_style": thumbnail_style,
        "add_intro": add_intro,
        "add_music": add_music,
        "music_volume_db": music_volume_db,
        "clip_mode": clip_mode,
        "user_context": user_context,
    }
    return _rewrite_job(await _json("POST", "/api/v1/jobs", json=body))


@mcp.tool
async def rerun_job(job_id: str) -> dict:
    """Re-run a previous job with its original parameters (creates a new job)."""
    return _rewrite_job(await _json("POST", f"/api/v1/jobs/{job_id}/rerun"))


@mcp.tool
async def get_job_status(job_id: str) -> dict:
    """Get status and results for a clip job.

    While running, `current_node` shows the live pipeline stage. When
    `status == 'done'`, `clips` holds each clip with a `url` (and `thumbnail_url`)
    plus title, summary, hook_text, hashtags and timestamp_range.
    """
    return _rewrite_job(await _json("GET", f"/api/v1/jobs/{job_id}"))


@mcp.tool
async def list_jobs(limit: int = 50, offset: int = 0) -> dict:
    """List the current user's clip jobs, most recent first."""
    job_list = await _json("GET", "/api/v1/jobs", params={"limit": limit, "offset": offset})
    for job in job_list.get("jobs") or []:
        _rewrite_job(job)
    return job_list


@mcp.tool
async def get_usage() -> dict:
    """Get the user's plan, jobs used this month, and remaining quota."""
    return await _json("GET", "/api/v1/usage")


@mcp.tool
async def wait_for_job(job_id: str, timeout_seconds: int = 300, poll_interval_seconds: int = 5) -> dict:
    """Poll a clip job until it finishes or the timeout elapses (convenience).

    Returns the final job record when status is 'done' or 'failed'. If the
    timeout is reached first, returns the latest 'running'/'queued' record so the
    caller can keep polling with get_job_status.
    """
    deadline = asyncio.get_event_loop().time() + max(1, timeout_seconds)
    interval = max(1, poll_interval_seconds)
    job = await get_job_status(job_id)
    while job.get("status") in ("queued", "running"):
        if asyncio.get_event_loop().time() >= deadline:
            break
        await asyncio.sleep(interval)
        job = await get_job_status(job_id)
    return job


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------

@mcp.tool
async def edit_add_tts(
    text: str,
    voice_preset: str = "default",
    parent_job_id: Optional[str] = None,
    attach_to_clip_id: Optional[str] = None,
    video_upload_id: Optional[str] = None,
    video_url: Optional[str] = None,
) -> dict:
    """Generate TTS narration (returns an async edit job; poll get_edit_job).

    With `attach_to_clip_id` (+ `parent_job_id`) the narration is prepended to an
    existing clip. Alternatively lay it over an uploaded video (`video_upload_id`)
    or a `video_url`. With none of these, produces a standalone audio file.
    """
    body = {
        "text": text,
        "voice_preset": voice_preset,
        "parent_job_id": parent_job_id,
        "attach_to_clip_id": attach_to_clip_id,
        "video_upload_id": video_upload_id,
        "video_url": video_url,
    }
    return await _json("POST", "/api/v1/edit/tts", json=body)


@mcp.tool
async def generate_tts_script(summary: str, target_seconds: int = 30, tone: Optional[str] = None) -> dict:
    """Expand a short summary into a spoken narration script (synchronous)."""
    body = {"summary": summary, "target_seconds": target_seconds, "tone": tone}
    return await _json("POST", "/api/v1/edit/tts/script", json=body)


@mcp.tool
async def edit_add_music(
    parent_job_id: str,
    clip_id: str,
    theme: Optional[str] = None,
    music_path: Optional[str] = None,
    music_upload_id: Optional[str] = None,
    volume_db: float = -18.0,
    music_start_sec: float = 0.0,
) -> dict:
    """Mix background music under a clip (async edit job; poll get_edit_job).

    Provide exactly one of `theme` (audio theme name), `music_path` (a track path
    from search_music), or `music_upload_id`. `volume_db` ducks the music relative
    to the clip audio; `music_start_sec` offsets into the track (e.g. the chorus).
    """
    body = {
        "parent_job_id": parent_job_id,
        "clip_id": clip_id,
        "theme": theme,
        "music_path": music_path,
        "music_upload_id": music_upload_id,
        "volume_db": volume_db,
        "music_start_sec": music_start_sec,
    }
    return await _json("POST", "/api/v1/edit/add-music", json=body)


@mcp.tool
async def edit_generate_thumbnail(
    parent_job_id: str,
    clip_id: str,
    headline: Optional[str] = None,
    accent_color: Optional[str] = None,
    text_color: Optional[str] = None,
    style: str = "auto",
    font: str = "auto",
) -> dict:
    """Generate an AI-directed thumbnail for a clip (async edit job).

    Omit `headline`/colors to let the LLM decide. `style` is auto|bubble|highlight|box|plain,
    `font` is auto|impact|arial|condensed. Poll get_edit_job for the output URL.
    """
    body = {
        "parent_job_id": parent_job_id,
        "clip_id": clip_id,
        "headline": headline,
        "accent_color": accent_color,
        "text_color": text_color,
        "style": style,
        "font": font,
    }
    return await _json("POST", "/api/v1/edit/generate-thumbnail", json=body)


@mcp.tool
async def edit_split_screen(
    parent_job_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    foreground_upload_id: Optional[str] = None,
    background_default: bool = False,
    background_path: Optional[str] = None,
    background_url: Optional[str] = None,
    background_upload_id: Optional[str] = None,
    audio_mode: str = "fetched_video",
) -> dict:
    """Compose a split-screen short (async edit job; poll get_edit_job).

    Foreground (top) is EITHER an existing clip (`parent_job_id` + `clip_id`) OR a
    `foreground_upload_id`. Supply exactly one background: `background_default`
    (the configured gameplay loop), `background_url` (YouTube), `background_path`,
    or `background_upload_id`. `audio_mode` is 'fetched_video' (clip audio) or
    'bg_video' (background audio).
    """
    body = {
        "parent_job_id": parent_job_id,
        "clip_id": clip_id,
        "foreground_upload_id": foreground_upload_id,
        "background_default": background_default,
        "background_path": background_path,
        "background_url": background_url,
        "background_upload_id": background_upload_id,
        "audio_mode": audio_mode,
    }
    return await _json("POST", "/api/v1/edit/split-screen", json=body)


@mcp.tool
async def get_edit_job(edit_job_id: str) -> dict:
    """Get status and output URL for an edit job (tts/music/thumbnail/split_screen)."""
    return await _json("GET", f"/api/v1/edit/jobs/{edit_job_id}")


# ---------------------------------------------------------------------------
# Discover + music catalog
# ---------------------------------------------------------------------------

@mcp.tool
async def discover_topics() -> dict:
    """List the curated topic keys available for trending discovery."""
    return await _json("GET", "/api/v1/discover/topics")


@mcp.tool
async def discover_trending(
    topics: Optional[list[str]] = None,
    custom_queries: Optional[list[str]] = None,
    conversational_query: Optional[str] = None,
    days_ago: int = 7,
    max_results_per_query: int = 5,
    order: str = "relevance",
    min_duration_minutes: Optional[int] = None,
    max_duration_minutes: Optional[int] = None,
) -> dict:
    """Find trending long-form YouTube videos to turn into shorts.

    Combine curated `topics` (see discover_topics) and/or free-text
    `custom_queries`, or pass a natural-language `conversational_query` (e.g.
    "recent AI agent deep dives under an hour") to let the server interpret it.
    Returns ranked candidate videos with metadata; feed a chosen `url` into
    submit_shorts_job.
    """
    body = {
        "topics": topics or [],
        "custom_queries": custom_queries or [],
        "conversational_query": conversational_query,
        "days_ago": days_ago,
        "max_results_per_query": max_results_per_query,
        "order": order,
        "min_duration_minutes": min_duration_minutes,
        "max_duration_minutes": max_duration_minutes,
    }
    return await _json("POST", "/api/v1/discover", json=body)


@mcp.tool
async def search_music(q: str, order: str = "popular", limit: int = 12, conversational: bool = False) -> dict:
    """Search the free music catalog for background tracks.

    `q` is a title/artist, or a vibe phrase when `conversational=true`. `order` is
    popular|latest|relevance. Each result's `download_url`/`path` can be used with
    edit_add_music.
    """
    params = {"q": q, "order": order, "limit": limit, "conversational": conversational}
    return await _json("GET", "/api/v1/music/search", params=params)


# ---------------------------------------------------------------------------
# YouTube publishing
# ---------------------------------------------------------------------------

@mcp.tool
async def youtube_auth_status() -> dict:
    """Check whether the user's YouTube channel is connected for publishing."""
    return await _json("GET", "/api/v1/youtube/auth/status")


@mcp.tool
async def youtube_publish(
    parent_job_id: str,
    clip_id: str,
    title: str,
    description: str = "",
    tags: Optional[list[str]] = None,
    privacy_status: str = "private",
    category_id: str = "22",
    made_for_kids: bool = False,
) -> dict:
    """Publish an extracted clip to the user's connected YouTube channel (async).

    Requires the channel to be connected first in the web app (call
    youtube_auth_status; if not connected, ask the user to connect it there —
    the OAuth flow cannot be completed inside this connector). Returns an upload
    record; poll get_youtube_upload for the watch URL. Unverified apps force
    privacy to 'private'.
    """
    body = {
        "parent_job_id": parent_job_id,
        "clip_id": clip_id,
        "title": title,
        "description": description,
        "tags": tags or [],
        "privacy_status": privacy_status,
        "category_id": category_id,
        "made_for_kids": made_for_kids,
    }
    return await _json("POST", "/api/v1/youtube/upload", json=body)


@mcp.tool
async def get_youtube_upload(upload_id: str) -> dict:
    """Get status and watch URL for a YouTube upload job."""
    return await _json("GET", f"/api/v1/youtube/uploads/{upload_id}")


# ---------------------------------------------------------------------------
# ChatGPT deep-research compatibility: search + fetch
# ---------------------------------------------------------------------------

@mcp.tool
async def search(query: str) -> dict:
    """Search the user's jobs and clips by keyword (video titles, clip titles,
    summaries, hashtags). Returns a list of {id, title, url} results; pass an id
    to `fetch` for full detail. Included for ChatGPT deep-research compatibility.
    """
    needle = (query or "").strip().lower()
    job_list = await _json("GET", "/api/v1/jobs", params={"limit": 200, "offset": 0})
    results: list[dict] = []
    for job in job_list.get("jobs") or []:
        _rewrite_job(job)
        job_title = job.get("video_title") or job.get("job_id", "")
        if not needle or needle in str(job_title).lower():
            results.append({"id": job.get("job_id"), "title": f"Job: {job_title}", "url": None})
        for clip in job.get("clips") or []:
            hay = " ".join(
                str(x) for x in (
                    clip.get("title"), clip.get("summary"), clip.get("hook_text"),
                    " ".join(clip.get("hashtags") or []),
                )
                if x
            ).lower()
            if not needle or needle in hay:
                results.append({
                    "id": f"{job.get('job_id')}:{clip.get('clip_id')}",
                    "title": clip.get("title") or f"Clip {clip.get('clip_id')}",
                    "url": clip.get("url"),
                })
    return {"results": results}


@mcp.tool
async def fetch(id: str) -> dict:
    """Fetch a job or clip by id (from `search`).

    A plain job id returns the full job record; a `<job_id>:<clip_id>` id returns
    the single clip. Included for ChatGPT deep-research compatibility.
    """
    if ":" in id:
        job_id, clip_id = id.split(":", 1)
        job = _rewrite_job(await _json("GET", f"/api/v1/jobs/{job_id}"))
        for clip in job.get("clips") or []:
            if clip.get("clip_id") == clip_id:
                return clip
        raise ToolError(f"Clip '{clip_id}' not found in job '{job_id}'.")
    return _rewrite_job(await _json("GET", f"/api/v1/jobs/{id}"))


# ---------------------------------------------------------------------------
# ASGI app for mounting (see app.py). Served at "/" inside its own sub-app so
# the mount point (/mcp) yields the public MCP endpoint.
# ---------------------------------------------------------------------------

mcp_asgi_app = mcp.http_app(path="/")

__all__ = ["mcp", "mcp_asgi_app"]
