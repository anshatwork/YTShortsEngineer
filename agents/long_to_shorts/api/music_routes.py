"""
agents/long_to_shorts/api/music_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for the cached music library (mounted at /api/v1/music).

The cache itself lives in ``tools/assets`` (file-backed, theme-bucketed, with a
background refresh — see tools/assets/refresh.py). These endpoints expose it to
the UI so users can browse/preview cached trending tracks in the clip editor and
on the discover page, and trigger a manual refresh.

Endpoints
---------
    GET    /music/tracks   List cached tracks (optionally filtered by theme/bucket).
    POST   /music/tracks   Add a user-supplied track, tagged with a mood (theme).
    DELETE /music/tracks   Remove a curated track (user uploads + songs library).
    GET    /music/search   Free-catalog song search (live; not cached).
    POST   /music/songs    Add a searched song into the dedicated 'songs' library.
    GET    /music/themes   Per-theme track counts (for UI chips).
    POST   /music/refresh  Enqueue a background refresh of the cache.

A picked track is used by passing its ``path`` straight back as
``MusicEditRequest.music_path`` — no new edit field is needed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.models import (
    AddSongRequest,
    MusicInterpretation,
    MusicRefreshResponse,
    MusicSearchResponse,
    MusicSearchResult,
    MusicThemeCount,
    MusicThemesResponse,
    MusicTrack,
    MusicTrackListResponse,
)
from core.audio_themes import AudioTheme
from tools.assets import Asset, AssetQuery, AssetType
from tools.assets.registry import get_sources
from tools.assets.store import AssetStore

logger = logging.getLogger(__name__)

router = APIRouter()

# Audio formats accepted for user-supplied tracks.
_ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}

# Public mount prefix for cached audio (see app.py: StaticFiles at /library).
_LIBRARY_URL_PREFIX = "/library"

# Reserved bucket for user-curated named songs (kept apart from mood beds).
SONGS_BUCKET = "songs"

# Hosts we'll download a searched song from (SSRF guard on POST /music/songs).
_ALLOWED_DOWNLOAD_HOSTS = ("jamendo.com", "pixabay.com")
_DOWNLOAD_TIMEOUT = 30

# YouTube watch hosts — committed via yt-dlp (not requests.get), so they bypass
# the _ALLOWED_DOWNLOAD_HOSTS allowlist and use the dedicated branch in add_song.
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")

# Short in-process cache for the trending chart so repeated tab opens don't each
# spend a (cheap) quota unit. {region: (epoch, [MusicSearchResult, ...])}.
_TRENDING_TTL_SECONDS = 600
_trending_cache: dict[str, tuple[float, list]] = {}

# Cache for YouTube keyword searches — each miss costs 100 quota units, so memo
# identical (query, order) pairs. {f"{q}|{order}": (epoch, [MusicSearchResult])}.
_YT_SEARCH_TTL_SECONDS = 600
_yt_search_cache: dict[str, tuple[float, list]] = {}


def _is_curated_bucket(bucket: str) -> bool:
    return bucket == SONGS_BUCKET


def _host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in _ALLOWED_DOWNLOAD_HOSTS)


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in _YOUTUBE_HOSTS)


def _music_root() -> Path:
    """Filesystem root of the music cache: <ASSET_CACHE_DIR>/audio_cache."""
    return (Path(os.getenv("ASSET_CACHE_DIR", "assets")) / "audio_cache").resolve()


def _preview_url(local_path: str) -> Optional[str]:
    """Map a cached file path to its /library URL, or None if outside the root."""
    try:
        rel = Path(local_path).resolve().relative_to(_music_root())
    except (ValueError, OSError):
        return None
    return f"{_LIBRARY_URL_PREFIX}/{rel.as_posix()}"


def _to_track(asset: Asset, theme: str) -> Optional[MusicTrack]:
    """Map a cached Asset to a MusicTrack, or None if it isn't servable."""
    if not asset.local_path:
        return None
    preview = _preview_url(asset.local_path)
    if preview is None:
        return None
    return MusicTrack(
        track_id=asset.cache_key,
        title=asset.title or Path(asset.local_path).stem,
        theme=theme,
        source=asset.source,
        duration=asset.duration,
        attribution=asset.attribution,
        preview_url=preview,
        path=asset.local_path,
        deletable=asset.source == "user" or _is_curated_bucket(theme),
    )


def _tracks_for_theme(store: AssetStore, theme: str) -> list[MusicTrack]:
    out: list[MusicTrack] = []
    for asset in store.get(AssetType.MUSIC, theme):
        track = _to_track(asset, theme)
        if track is not None:
            out.append(track)
    return out


@router.get(
    "/tracks",
    response_model=MusicTrackListResponse,
    summary="List cached music tracks (optionally filtered by theme)",
)
async def list_tracks(
    theme: Optional[str] = Query(default=None, description="AudioTheme value; omit for all themes."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
) -> MusicTrackListResponse:
    store = AssetStore()

    valid_buckets = AudioTheme.list_values() + [SONGS_BUCKET]
    if theme:
        themes = [theme] if theme in valid_buckets else []
    else:
        themes = valid_buckets

    tracks: list[MusicTrack] = []
    for t in themes:
        tracks.extend(_tracks_for_theme(store, t))

    # Stable ordering: theme, then title.
    tracks.sort(key=lambda tr: (tr.theme, tr.title.lower()))
    window = tracks[offset : offset + limit]
    return MusicTrackListResponse(tracks=window, total=len(tracks))


@router.post(
    "/tracks",
    response_model=MusicTrack,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user-supplied track, tagged with a mood (theme)",
)
async def add_track(
    file: UploadFile = File(...),
    theme: str = Form(...),
    title: Optional[str] = Form(default=None),
    user_id: str = Depends(get_current_user_id),
) -> MusicTrack:
    if AudioTheme.validate(theme) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown theme '{theme}'. Valid: {AudioTheme.list_values()}",
        )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported audio extension '{ext}'. Allowed: {sorted(_ALLOWED_AUDIO_EXTS)}",
        )

    # Write into the theme bucket via a `user_`-prefixed name (the prefix keeps it
    # safe from LRU eviction — see AssetStore.cleanup). AssetStore.put moves the
    # file into <ASSET_CACHE_DIR>/audio_cache/<theme>/ and indexes it.
    track_uuid = uuid.uuid4().hex
    filename = f"user_{track_uuid}{ext}"
    bucket_dir = _music_root() / theme
    bucket_dir.mkdir(parents=True, exist_ok=True)
    staged = bucket_dir / filename

    size = 0
    with staged.open("wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            fh.write(chunk)

    if size == 0:
        staged.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    asset = Asset(
        asset_type=AssetType.MUSIC,
        source="user",
        source_id=track_uuid,
        title=(title or "").strip() or Path(file.filename or filename).stem,
        url="",
        local_path=str(staged),
        theme=theme,
        attribution="User upload",
    )
    stored = AssetStore().put(asset)
    logger.info("user track added: %s -> %s (user=%s)", stored.cache_key, stored.local_path, user_id)

    track = _to_track(stored, theme)
    if track is None:  # pragma: no cover — put() guarantees a local_path under the root
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Track stored but could not be served.",
        )
    return track


@router.delete(
    "/tracks",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user-added track (user tracks only)",
)
async def delete_track(
    track_id: str = Query(..., description="Track id (Asset cache_key)."),
    theme: str = Query(..., description="The track's theme bucket."),
    user_id: str = Depends(get_current_user_id),
) -> None:
    store = AssetStore()
    match = next(
        (a for a in store.get(AssetType.MUSIC, theme) if a.cache_key == track_id),
        None,
    )
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")
    if match.source != "user" and not _is_curated_bucket(theme):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only user-added tracks and songs-library tracks can be deleted.",
        )

    store.delete(AssetType.MUSIC, theme, track_id)
    logger.info("curated track deleted: %s bucket=%s (user=%s)", track_id, theme, user_id)


def interpret_music_query(text: str) -> MusicInterpretation:
    """Translate a natural-language "vibe" request into a catalog search phrase.

    Mirrors ``interpret_discover_query`` (discover_routes.py): uses the configured
    LLM provider's structured-output ``parse``. On *any* failure — no API key,
    network error, schema-parse failure — falls back to treating the raw text as
    the search phrase so the search still proceeds. Never raises.
    """
    system = (
        "You are a query-understanding engine for a royalty-free music search tool "
        "(Jamendo/Pixabay free catalogs). Translate the user's natural-language "
        "vibe description into a concise catalog search phrase plus a sort order.\n\n"
        "Rules:\n"
        "- `query`: 2-5 keywords capturing genre, mood and instrumentation that a "
        "free catalog would match — e.g. 'upbeat lo-fi for a cooking montage' → "
        "'upbeat lo-fi instrumental', 'something dark and cinematic' → 'dark "
        "cinematic ambient'. Drop incidental words (durations, 'for a …', 'I need'). "
        "Never leave it empty.\n"
        "- `order`: 'popular' for trending/popular/best, 'latest' for newest/recent, "
        "otherwise 'relevance'.\n"
        "- `summary`: one line starting with 'Understood: ' recapping the vibe in "
        "plain words."
    )
    try:
        from tools.llm import get_llm

        interp = get_llm().parse(text, MusicInterpretation, system=system)
        if not (interp.query or "").strip():
            interp.query = text
        if interp.order not in ("popular", "latest", "relevance"):
            interp.order = "popular"
        if not interp.summary:
            interp.summary = f"Understood: {text}"
        return interp
    except Exception as exc:  # noqa: BLE001 — degrade gracefully to raw keyword search
        logger.warning(
            "Music vibe interpretation failed (%s); falling back to raw search.",
            exc, exc_info=True,
        )
        return MusicInterpretation(
            query=text,
            order="popular",
            summary=f"Understood (basic): {text}",
        )


def _search_youtube_songs(keyword: str, order: str, limit: int) -> MusicSearchResponse:
    """Keyword-search YouTube for copyrighted songs (manual pick), with a TTL cache."""
    from tools.assets.sources.music_youtube import COPYRIGHT_WARNING, YouTubeMusicSource

    source = YouTubeMusicSource()
    if not source.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube search is unavailable — YT_API_KEY is not configured.",
        )

    cache_key = f"{keyword.lower()}|{order}"
    cached = _yt_search_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _YT_SEARCH_TTL_SECONDS:
        results = cached[1]
    else:
        candidates = source.discover(
            AssetQuery(
                asset_type=AssetType.MUSIC,
                keywords=[keyword],
                order=order,
                limit=limit,
            )
        )
        cached_keys = {a.cache_key for a in AssetStore().get(AssetType.MUSIC, SONGS_BUCKET)}
        results = [
            MusicSearchResult(
                source=a.source,
                source_id=a.source_id,
                title=a.title or "Untitled",
                artist=(a.metadata or {}).get("artist"),
                duration=a.duration,
                attribution=a.attribution,
                preview_url=a.url,
                download_url=a.url,
                already_cached=a.cache_key in cached_keys,
                thumbnail=(a.metadata or {}).get("thumbnail"),
                copyright_warning=(a.metadata or {}).get("copyright_warning", COPYRIGHT_WARNING),
            )
            for a in candidates
        ]
        _yt_search_cache[cache_key] = (time.time(), results)

    return MusicSearchResponse(results=results[:limit], total=len(results), query_used=keyword)


@router.get(
    "/search",
    response_model=MusicSearchResponse,
    summary="Search music catalogs for named/trending songs (live, not cached)",
)
async def search_songs(
    q: str = Query(..., min_length=1, description="Song title/artist, or a vibe phrase when conversational=true."),
    order: str = Query(default="popular", description="'popular' (trending) | 'latest' | 'relevance'."),
    limit: int = Query(default=12, ge=1, le=40),
    conversational: bool = Query(
        default=False,
        description="When true, LLM-interpret `q` as a natural-language vibe into a search phrase + order.",
    ),
    provider: str = Query(
        default="free",
        description="'free' = royalty-free catalogs (jamendo/pixabay/freesound); 'youtube' = copyrighted YouTube songs (100 quota units/search).",
    ),
    user_id: str = Depends(get_current_user_id),
) -> MusicSearchResponse:
    # YouTube keyword search — copyrighted; pricey (search.list = 100 units), so
    # cache identical (query, order) pairs briefly.
    if provider == "youtube":
        return _search_youtube_songs(q.strip(), order, limit)

    # Conversational "vibe" search: interpret the phrase into a concise catalog
    # query + order (the manual order arg is overridden by what's understood).
    interpretation: Optional[MusicInterpretation] = None
    keyword = q.strip()
    if conversational:
        interpretation = interpret_music_query(keyword)
        keyword = interpretation.query.strip() or keyword
        order = interpretation.order

    query = AssetQuery(
        asset_type=AssetType.MUSIC,
        keywords=[keyword],
        order=order,
        include_vocals=True,  # songs mode: full-text name search, vocals allowed
        limit=limit,
    )

    sources = get_sources(AssetType.MUSIC)
    if not sources:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No music source configured (set JAMENDO_CLIENT_ID).",
        )

    # Which source_ids are already in the songs library, to flag in the UI.
    cached_keys = {a.cache_key for a in AssetStore().get(AssetType.MUSIC, SONGS_BUCKET)}

    results: list[MusicSearchResult] = []
    seen: set[str] = set()
    for source in sources:
        try:
            candidates = source.discover(query)
        except Exception as exc:  # noqa: BLE001 — one bad source shouldn't fail the search
            logger.warning("song search via '%s' failed: %s", source.name, exc)
            continue
        for a in candidates:
            if not a.url or a.cache_key in seen:
                continue
            seen.add(a.cache_key)
            results.append(
                MusicSearchResult(
                    source=a.source,
                    source_id=a.source_id,
                    title=a.title or "Untitled",
                    artist=(a.metadata or {}).get("artist"),
                    duration=a.duration,
                    attribution=a.attribution,
                    preview_url=a.url,
                    download_url=a.url,
                    already_cached=a.cache_key in cached_keys,
                )
            )

    results.sort(key=lambda r: r.already_cached)  # un-cached first
    return MusicSearchResponse(
        results=results[:limit],
        total=len(results),
        interpretation=interpretation,
        query_used=keyword,
    )


@router.get(
    "/trending",
    response_model=MusicSearchResponse,
    summary="Browse trending YouTube songs (copyrighted — manual pick only)",
)
async def trending_songs(
    limit: int = Query(default=25, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
) -> MusicSearchResponse:
    """List the current YouTube Music chart for manual selection.

    These are real, copyrighted commercial songs — every result carries a
    ``copyright_warning`` the UI must surface. Discovery costs ~1 quota unit and
    is cached briefly. The track is only downloaded (via yt-dlp) when the user
    explicitly adds it through POST /music/songs.
    """
    from tools.assets.sources.music_youtube import COPYRIGHT_WARNING, YouTubeMusicSource

    source = YouTubeMusicSource()
    if not source.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube trending is unavailable — YT_API_KEY is not configured.",
        )

    region = os.getenv("YT_TRENDING_REGION", "US")
    cached = _trending_cache.get(region)
    if cached and (time.time() - cached[0]) < _TRENDING_TTL_SECONDS:
        results = cached[1]
    else:
        candidates = source.discover(
            AssetQuery(asset_type=AssetType.MUSIC, theme=SONGS_BUCKET, limit=limit)
        )
        cached_keys = {a.cache_key for a in AssetStore().get(AssetType.MUSIC, SONGS_BUCKET)}
        results = [
            MusicSearchResult(
                source=a.source,
                source_id=a.source_id,
                title=a.title or "Untitled",
                artist=(a.metadata or {}).get("artist"),
                duration=a.duration,
                attribution=a.attribution,
                preview_url=a.url,
                download_url=a.url,
                already_cached=a.cache_key in cached_keys,
                thumbnail=(a.metadata or {}).get("thumbnail"),
                copyright_warning=(a.metadata or {}).get("copyright_warning", COPYRIGHT_WARNING),
            )
            for a in candidates
        ]
        _trending_cache[region] = (time.time(), results)

    return MusicSearchResponse(results=results[:limit], total=len(results), query_used="trending")


@router.post(
    "/songs",
    response_model=MusicTrack,
    status_code=status.HTTP_201_CREATED,
    summary="Add a searched song into the dedicated 'songs' library",
)
async def add_song(
    body: AddSongRequest,
    user_id: str = Depends(get_current_user_id),
) -> MusicTrack:
    is_youtube = body.source == "youtube" or _is_youtube_url(body.download_url)

    if is_youtube:
        # Copyrighted trending song: pull audio with yt-dlp (no direct media URL,
        # so it bypasses the requests.get allowlist path). Attribution carries the
        # Content-ID warning so it follows the track into the editor.
        from tools.assets.sources.music_youtube import COPYRIGHT_WARNING
        from tools.youtube.downloader import download_audio

        url_hash = hashlib.md5(body.download_url.encode()).hexdigest()[:8]
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp3", prefix=f"youtube_{url_hash}_"
        )
        tmp.close()
        try:
            local_path = download_audio(body.download_url, tmp.name)
        except Exception as exc:  # noqa: BLE001 — surface a clean 502 to the UI
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not download YouTube audio: {exc}",
            )
        attribution = body.attribution or COPYRIGHT_WARNING
        if COPYRIGHT_WARNING not in attribution:
            attribution = f"{attribution}. {COPYRIGHT_WARNING}"
        asset = Asset(
            asset_type=AssetType.MUSIC,
            source="youtube",
            source_id=body.source_id,
            title=body.title.strip() or "Song",
            url=body.download_url,
            local_path=local_path,
            theme=SONGS_BUCKET,
            duration=body.duration,
            attribution=attribution,
        )
        stored = AssetStore().put(asset)
        logger.info("youtube song added to library: %s -> %s (user=%s)", stored.cache_key, stored.local_path, user_id)
        track = _to_track(stored, SONGS_BUCKET)
        if track is None:  # pragma: no cover
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Song stored but could not be served.",
            )
        return track

    if not _host_allowed(body.download_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="download_url host is not allowed.",
        )

    # Download to a temp file, then hand to AssetStore.put (moves into the songs bucket).
    try:
        resp = requests.get(body.download_url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not download track: {exc}",
        )

    ext = ".wav" if ".wav" in body.download_url.lower() else ".mp3"
    url_hash = hashlib.md5(body.download_url.encode()).hexdigest()[:8]
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=ext, prefix=f"song_{url_hash}_"
    )
    tmp.write(resp.content)
    tmp.close()

    asset = Asset(
        asset_type=AssetType.MUSIC,
        source=body.source or "search",
        source_id=body.source_id,
        title=body.title.strip() or "Song",
        url=body.download_url,
        local_path=tmp.name,
        theme=SONGS_BUCKET,
        duration=body.duration,
        attribution=body.attribution,
    )
    stored = AssetStore().put(asset)
    logger.info("song added to library: %s -> %s (user=%s)", stored.cache_key, stored.local_path, user_id)

    track = _to_track(stored, SONGS_BUCKET)
    if track is None:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Song stored but could not be served.",
        )
    return track


@router.get(
    "/themes",
    response_model=MusicThemesResponse,
    summary="Per-theme cached-track counts",
)
async def list_theme_counts(
    user_id: str = Depends(get_current_user_id),
) -> MusicThemesResponse:
    store = AssetStore()
    counts = [
        MusicThemeCount(theme=t, count=len(_tracks_for_theme(store, t)))
        for t in AudioTheme.list_values()
    ]
    return MusicThemesResponse(themes=counts)


@router.post(
    "/refresh",
    response_model=MusicRefreshResponse,
    summary="Enqueue a background refresh of the trending-music cache",
)
async def refresh(
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> MusicRefreshResponse:
    from tools.assets.refresh import music_sources_available, refresh_music_cache

    if not music_sources_available():
        return MusicRefreshResponse(
            queued=False,
            detail=(
                "No music source configured. Set JAMENDO_CLIENT_ID "
                "(or PIXABAY_API_KEY / FREESOUND_API_KEY) on the server."
            ),
        )

    http_request.app.state.task_queue.enqueue(refresh_music_cache)
    logger.info("music cache refresh enqueued by user=%s", user_id)
    return MusicRefreshResponse(queued=True, detail="Refresh queued.")
