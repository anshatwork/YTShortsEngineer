"""
tools/thumbnail.py
~~~~~~~~~~~~~~~~~~
AI-directed thumbnail generation for a single clip.

The LLM (Ollama / Claude — whatever ``tools.llm.get_llm`` resolves to) is the
*creative director*: it never renders pixels, it produces a :class:`ThumbnailSpec`
(punchy headline, accent color, text placement, and a fallback image-search query).
The actual image is built from a real video frame:

    1.  ``pick_best_frame``      — ffmpeg's ``thumbnail`` filter grabs the most
                                    representative frame of the clip.
    2.  ``search_fallback_image`` — if no usable frame (audio-only / unreadable),
                                    fetch a topical photo from Pixabay (free tier,
                                    reuses PIXABAY_API_KEY).
    3.  ``compose_thumbnail``     — burn the headline over the background with Pillow,
                                    in a user-selectable caption style (bubble /
                                    highlight / box / plain), with color + font control.

Everything degrades gracefully: any failure leaves the clip without a thumbnail
rather than breaking the run. This module is the single source of truth shared by
the pipeline node (``thumbnail_node``) and the edit worker (``run_thumbnail_edit_job``).

RAG note: ``_build_user_prompt`` reserves an empty ``trend_context`` slot so a future
thumbnail-trends retrieval step can inject examples without changing this contract.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import ffmpeg  # ffmpeg-python
import requests
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output geometry / style (overridable via environment)
# ---------------------------------------------------------------------------

_WIDTH: int = int(os.getenv("THUMBNAIL_WIDTH", "1080"))
_HEIGHT: int = int(os.getenv("THUMBNAIL_HEIGHT", "1920"))
_FONT_SIZE: int = int(os.getenv("THUMBNAIL_FONT_SIZE", "96"))
_BOX_ALPHA: float = float(os.getenv("THUMBNAIL_BOX_ALPHA", "0.55"))
_MARGIN: int = int(os.getenv("THUMBNAIL_MARGIN_PX", "140"))

# Bump to invalidate cached thumbnail-spec completions when the prompt changes.
# v2: ThumbnailSpec gained a `style` field (the LLM now suggests a caption style).
_THUMBNAIL_LLM_CACHE_VERSION: int = 2

_PIXABAY_API_URL = "https://pixabay.com/api/"
_PIXABAY_TIMEOUT = 10

_HEADLINE_MAX_CHARS = 30

# ---------------------------------------------------------------------------
# Caption styles + fonts
# ---------------------------------------------------------------------------

ThumbnailStyle = Literal["auto", "bubble", "highlight", "box", "plain"]
ThumbnailFont = Literal["auto", "impact", "arial", "condensed"]

# Drawn styles (everything except the "auto" sentinel, which resolves to one of these).
_DRAWN_STYLES = ("bubble", "highlight", "box", "plain")

# Candidate font files per logical name. Tried in order; falls back across OSes and
# finally to Pillow's bundled default so rendering never hard-fails on a missing font.
_FONT_CANDIDATES: Dict[str, List[str]] = {
    "impact": [
        r"C:\Windows\Fonts\impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    "arial": [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "condensed": [
        r"C:\Windows\Fonts\ARIALNB.TTF",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    ],
}
_DEFAULT_FONT_KEY = "impact"


# ---------------------------------------------------------------------------
# LLM contract — the "creative director" spec
# ---------------------------------------------------------------------------

class ThumbnailSpec(BaseModel):
    """Structured design brief the LLM returns for one thumbnail."""

    headline: str                              # <= 30 chars, 2–5 words
    accent_color: str                          # vivid hex, e.g. "#FFCC00"
    text_position: Literal["top", "bottom"]
    style: Literal["bubble", "highlight", "box", "plain"] = "bubble"
    search_query: str                          # 2–4 keywords; fallback image only


THUMBNAIL_SYSTEM = """\
You are a YouTube thumbnail strategist for vertical (9:16) Shorts. Given a clip's
metadata, design ONE click-driving thumbnail. Return:
- headline: up to 30 characters, 2-5 words, emotionally charged, ALL-CAPS friendly.
  It restates the clip's hook, punchier than the title. No clickbait lies.
- accent_color: a vivid hex color (e.g. "#FFCC00") that pops over video and fits the
  mood. Avoid muddy / low-contrast colors.
- text_position: "top" or "bottom" - whichever keeps faces/action unobscured.
- style: the caption treatment that best fits the vibe, one of:
  "bubble" (rounded pill behind the text - friendly/modern),
  "highlight" (tight marker blocks per line - bold/punchy),
  "box" (full-width band - news/clean), or
  "plain" (outlined text, no background - minimal).
- search_query: 2-4 plain keywords for the clip's visual subject, used ONLY if no
  good video frame can be grabbed (e.g. "stock market chart").
Rules: the headline must be glanceable on a phone. Prefer punchy nouns and power
words. Never exceed the character limits."""

_THUMBNAIL_USER = """\
Clip title: {title}
On-screen hook: {hook_text}
One-line summary: {summary}
Hashtags: {hashtags}
{trend_context}
Design the thumbnail."""


def _build_user_prompt(clip_meta: Dict[str, Any], *, trend_context: str = "") -> str:
    """Render the per-clip user prompt. ``trend_context`` is the reserved RAG slot."""
    hashtags = clip_meta.get("hashtags") or []
    return _THUMBNAIL_USER.format(
        title=clip_meta.get("title") or "(untitled)",
        hook_text=clip_meta.get("hook_text") or "(none)",
        summary=clip_meta.get("summary") or "(none)",
        hashtags=", ".join(hashtags) if hashtags else "(none)",
        # Trailing newline only when populated, so the byte-identical empty case
        # keeps the cached prefix stable.
        trend_context=(trend_context + "\n") if trend_context else "",
    )


def _fallback_spec(clip_meta: Dict[str, Any]) -> ThumbnailSpec:
    """Deterministic spec used when the LLM is unavailable or returns garbage."""
    headline = (clip_meta.get("hook_text") or clip_meta.get("title") or "WATCH THIS").strip()
    headline = headline[:_HEADLINE_MAX_CHARS]
    query_src = clip_meta.get("title") or " ".join(clip_meta.get("hashtags") or []) or "abstract background"
    query = " ".join([w for w in re.split(r"\W+", query_src) if len(w) > 2][:3]) or "abstract background"
    return ThumbnailSpec(
        headline=headline,
        accent_color="#FFCC00",
        text_position="bottom",
        style="bubble",
        search_query=query,
    )


def generate_spec(
    clip_meta: Dict[str, Any], *, user_context: Optional[str] = None
) -> ThumbnailSpec:
    """Ask the LLM for a :class:`ThumbnailSpec`; never raises.

    Cached on (model, prompt) via the same layer ContentGenNode uses, so re-runs
    and resumes don't pay for the model again. ``user_context`` is optional
    creator guidance steering the headline; it rides the ``trend_context`` slot.
    """
    from agents.long_to_shorts._prompt_utils import guidance_block

    user_prompt = _build_user_prompt(
        clip_meta, trend_context=guidance_block(user_context).lstrip()
    )
    try:
        from tools.llm import get_llm
        from agents.long_to_shorts._llm_cache import cached_llm_text

        llm = get_llm()

        def _invoke() -> str:
            spec = llm.parse(user_prompt, ThumbnailSpec, system=THUMBNAIL_SYSTEM)
            return spec.model_dump_json()

        raw = cached_llm_text(
            user_prompt,
            operation="thumbnail_llm",
            version=_THUMBNAIL_LLM_CACHE_VERSION,
            invoke=_invoke,
        )
        spec = ThumbnailSpec.model_validate_json(raw)
        # Enforce the soft headline cap the prompt asks for.
        spec.headline = re.sub(r"\s+", " ", spec.headline).strip()[:_HEADLINE_MAX_CHARS]
        if not spec.headline:
            spec.headline = _fallback_spec(clip_meta).headline
        return spec
    except Exception as exc:  # noqa: BLE001 — design brief is best-effort
        logger.warning("thumbnail spec LLM failed (%s); using fallback spec.", exc)
        return _fallback_spec(clip_meta)


# ---------------------------------------------------------------------------
# Background — best frame via ffmpeg, with a Pixabay image-search fallback
# ---------------------------------------------------------------------------

def _has_video_stream(video_path: str) -> bool:
    try:
        return any(
            s.get("codec_type") == "video"
            for s in ffmpeg.probe(video_path)["streams"]
        )
    except Exception:  # noqa: BLE001
        return False


def _cover(stream, w: int, h: int):
    """scale-to-cover then center-crop to exactly w×h (fills the frame)."""
    return (
        stream
        .filter("scale", w, h, force_original_aspect_ratio="increase")
        .filter("crop", w, h)
    )


def pick_best_frame(video_path: str, out_png: str, w: int = _WIDTH, h: int = _HEIGHT) -> bool:
    """Grab the most representative frame of *video_path* into *out_png*.

    Uses ffmpeg's ``thumbnail`` filter (analyses frame batches and picks the most
    statistically representative one). Returns True on success, False on any
    failure or when the clip has no video stream.
    """
    if not video_path or not Path(video_path).exists() or not _has_video_stream(video_path):
        return False
    try:
        video = _cover(ffmpeg.input(video_path).video.filter("thumbnail", n=100), w, h)
        (
            ffmpeg
            .output(video, out_png, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return Path(out_png).exists() and Path(out_png).stat().st_size > 0
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.warning("pick_best_frame ffmpeg error: %s", stderr[-300:])
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("pick_best_frame failed: %s", exc)
        return False


def search_fallback_image(query: str, out_png: str, w: int = _WIDTH, h: int = _HEIGHT) -> bool:
    """Fetch a topical vertical photo from Pixabay into *out_png*.

    Free tier, reuses PIXABAY_API_KEY (same key as the music source). Returns
    False when there is no key, no hit, or the download/normalize fails — the
    caller then simply produces no thumbnail. Never raises.
    """
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        logger.info("thumbnail fallback skipped — PIXABAY_API_KEY not set.")
        return False
    try:
        params = {
            "key": key,
            "q": query or "abstract background",
            "image_type": "photo",
            "orientation": "vertical",
            "per_page": 3,
            "safesearch": "true",
        }
        resp = requests.get(_PIXABAY_API_URL, params=params, timeout=_PIXABAY_TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", []) or []
        if not hits:
            logger.info("thumbnail fallback — no Pixabay hits for '%s'.", query)
            return False
        url = hits[0].get("largeImageURL") or hits[0].get("webformatURL")
        if not url:
            return False

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            raw_path = tmp.name
            img = requests.get(url, timeout=_PIXABAY_TIMEOUT)
            img.raise_for_status()
            tmp.write(img.content)

        try:
            video = _cover(ffmpeg.input(raw_path), w, h)
            (
                ffmpeg
                .output(video, out_png, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        finally:
            Path(raw_path).unlink(missing_ok=True)
        return Path(out_png).exists() and Path(out_png).stat().st_size > 0
    except Exception as exc:  # noqa: BLE001 — fallback is best-effort
        logger.warning("search_fallback_image failed for '%s': %s", query, exc)
        return False


# ---------------------------------------------------------------------------
# Compositing — burn the headline over the background (Pillow)
# ---------------------------------------------------------------------------

def _resolve_font(font_key: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font for *font_key*, trying OS-specific candidates.

    Falls back across the candidate list and finally to Pillow's bundled font, so
    a missing font never breaks rendering. ``"auto"`` maps to the default key.
    """
    key = font_key if font_key in _FONT_CANDIDATES else _DEFAULT_FONT_KEY
    for path in _FONT_CANDIDATES[key]:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    # Last resort — keeps rendering alive even with no TrueType fonts installed.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _norm_hex(color: Optional[str], default: str) -> str:
    """Normalize a user/LLM hex string to ``#RRGGBB``; fall back to *default*."""
    if color and re.match(r"^#?[0-9A-Fa-f]{6}$", color.strip()):
        c = color.strip()
        return c if c.startswith("#") else f"#{c}"
    return default


def _contrast_text(hex_color: str) -> str:
    """Return black or white — whichever reads better over *hex_color*."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    # Perceived luminance (ITU-R BT.601).
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if lum > 0.6 else "#FFFFFF"


def _wrap_lines_px(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Word-wrap *text* so each line's rendered width is ≤ *max_width* pixels."""
    words = re.sub(r"\s+", " ", text.strip()).split()
    lines: List[str] = []
    current = ""

    def _w(s: str) -> int:
        return int(font.getbbox(s)[2] - font.getbbox(s)[0])

    for word in words:
        candidate = (current + " " + word).strip() if current else word
        if current and _w(candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _line_metrics(font: ImageFont.FreeTypeFont, lines: List[str]) -> Tuple[List[Tuple[int, int]], int]:
    """Per-line (width, height) and the uniform line height for *lines*."""
    sizes: List[Tuple[int, int]] = []
    for ln in lines:
        box = font.getbbox(ln or " ")
        sizes.append((int(box[2] - box[0]), int(box[3] - box[1])))
    # Use the font's ascent+descent for a stable line height (independent of glyphs).
    ascent, descent = font.getmetrics()
    return sizes, ascent + descent


def _draw_caption(
    base: Image.Image,
    lines: List[str],
    *,
    style: str,
    accent: str,
    text_color: Optional[str],
    font: ImageFont.FreeTypeFont,
    position: str,
) -> Image.Image:
    """Composite the caption onto *base* (RGB) and return a new RGB image.

    Drawing happens on an RGBA overlay so translucent fills (the "box" band) blend
    correctly, then the overlay is flattened back onto the frame.
    """
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    sizes, line_h = _line_metrics(font, lines)
    line_gap = int(line_h * 0.28)
    line_step = line_h + line_gap
    block_h = len(lines) * line_step - line_gap

    if position == "top":
        block_top = _MARGIN
    else:
        block_top = max(_MARGIN, _HEIGHT - _MARGIN - block_h)

    cx = _WIDTH // 2
    pad_x, pad_y = 36, 18           # padding inside bubble/highlight pills
    stroke = max(3, _FONT_SIZE // 22)

    def _fill_rgba(hex_color: str, alpha: int) -> Tuple[int, int, int, int]:
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)

    # "box" draws one shared band behind every line.
    if style == "box":
        band_top = block_top - pad_y - 6
        band_bot = block_top + block_h + pad_y + 6
        draw.rectangle([0, max(0, band_top), _WIDTH, min(_HEIGHT, band_bot)],
                       fill=_fill_rgba("#000000", int(_BOX_ALPHA * 255)))

    for i, line in enumerate(lines):
        lw, _ = sizes[i]
        ly = block_top + i * line_step
        text_x = cx - lw // 2

        if style == "bubble":
            radius = (line_h + pad_y * 2) // 2
            draw.rounded_rectangle(
                [cx - lw // 2 - pad_x, ly - pad_y, cx + lw // 2 + pad_x, ly + line_h + pad_y],
                radius=radius, fill=_fill_rgba(accent, 255),
            )
            fill = text_color or _contrast_text(accent)
            draw.text((text_x, ly), line, font=font, fill=fill)
        elif style == "highlight":
            draw.rectangle(
                [cx - lw // 2 - pad_x // 2, ly - pad_y // 2,
                 cx + lw // 2 + pad_x // 2, ly + line_h + pad_y // 2],
                fill=_fill_rgba(accent, 255),
            )
            fill = text_color or _contrast_text(accent)
            draw.text((text_x, ly), line, font=font, fill=fill)
        elif style == "box":
            fill = text_color or accent
            draw.text((text_x, ly), line, font=font, fill=fill)
        else:  # "plain" — outlined text, no background
            fill = text_color or "#FFFFFF"
            draw.text(
                (text_x, ly), line, font=font, fill=fill,
                stroke_width=stroke, stroke_fill="#000000",
            )

    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def compose_thumbnail(
    bg_png: str,
    spec: ThumbnailSpec,
    out_path: str,
    *,
    style: str = "auto",
    text_color: Optional[str] = None,
    font: str = "auto",
) -> str:
    """Render ``spec.headline`` over *bg_png* in the chosen caption style → JPG.

    ``style="auto"`` uses the LLM-suggested ``spec.style``; an explicit style wins.
    """
    final_style = spec.style if (style == "auto" or style not in _DRAWN_STYLES) else style
    accent = _norm_hex(spec.accent_color, "#FFCC00")
    text_fill = _norm_hex(text_color, None) if text_color else None

    pil_font = _resolve_font(font, _FONT_SIZE)
    lines = _wrap_lines_px(spec.headline, pil_font, _WIDTH - 2 * _MARGIN)

    base = Image.open(bg_png).convert("RGB")
    if base.size != (_WIDTH, _HEIGHT):
        base = base.resize((_WIDTH, _HEIGHT))

    result = _draw_caption(
        base, lines,
        style=final_style, accent=accent, text_color=text_fill,
        font=pil_font, position=spec.text_position,
    )
    result.save(out_path, format="JPEG", quality=90)
    return out_path


# ---------------------------------------------------------------------------
# Orchestrator — used by both the node and the edit worker
# ---------------------------------------------------------------------------

def generate_thumbnail(
    clip_meta: Dict[str, Any],
    video_path: Optional[str],
    out_path: str,
    *,
    headline_override: Optional[str] = None,
    accent_override: Optional[str] = None,
    text_color: Optional[str] = None,
    style: str = "auto",
    font: str = "auto",
    user_context: Optional[str] = None,
) -> Optional[str]:
    """Produce one thumbnail JPG at *out_path*. Returns the path, or None on failure.

    Steps: LLM spec → best video frame (fallback to Pixabay) → composite headline.
    The overrides let the edit endpoint take manual control of the caption while
    still using the LLM for everything else:
      * ``headline_override`` / ``accent_override`` / ``text_color`` — text + colors
      * ``style`` — "auto" (use the LLM-suggested style) or one of bubble/highlight/box/plain
      * ``font`` — "auto" (Impact) or impact/arial/condensed
    """
    spec = generate_spec(clip_meta, user_context=user_context)
    if headline_override and headline_override.strip():
        spec.headline = headline_override.strip()[:_HEADLINE_MAX_CHARS]
    if accent_override and accent_override.strip():
        spec.accent_color = accent_override.strip()

    out_path = str(out_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        bg_png = str(Path(tmpdir) / "bg.png")

        got_bg = pick_best_frame(video_path, bg_png) if video_path else False
        if not got_bg:
            logger.info("thumbnail: no usable frame — trying Pixabay '%s'.", spec.search_query)
            got_bg = search_fallback_image(spec.search_query, bg_png)
        if not got_bg:
            logger.warning("thumbnail: no background available; skipping.")
            return None

        try:
            compose_thumbnail(
                bg_png, spec, out_path,
                style=style, text_color=text_color, font=font,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("thumbnail compose failed: %s", exc)
            return None

    return out_path if Path(out_path).exists() else None


__all__ = [
    "ThumbnailSpec",
    "ThumbnailStyle",
    "ThumbnailFont",
    "THUMBNAIL_SYSTEM",
    "generate_spec",
    "pick_best_frame",
    "search_fallback_image",
    "compose_thumbnail",
    "generate_thumbnail",
]
