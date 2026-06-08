"""
agents/long_to_shorts/subtitles_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SubtitlesNode – burn styled subtitles into each extracted clip.

Subtitle source (in priority order)
-------------------------------------
1.  ``state["timed_transcript"]``  — a list of
    ``{"text": str, "start": float, "duration": float}`` entries produced by
    ``tools.youtube.transcript.fetch_timed_segments`` (YouTube captions API).
    When this is present **no Whisper model is loaded or run**.

2.  Whisper fallback — if the state has no timed transcript (e.g. local video
    workflow without YouTube captions), each clip is auto-transcribed with
    OpenAI Whisper as before.

For every clip in generated_clips:
  1.  Obtains per-clip subtitle segments (see above).
  2.  Writes a temporary .srt file.
  3.  Burns the subtitles into the video using ffmpeg's ``ass`` filter from a
      generated ASS file. The ASS file sets PlayResX/PlayResY to the clip's
      real resolution (so font sizes map to real pixels) and emits per-word
      Dialogue events that highlight the word currently being spoken.
  4.  Writes the result to  <OUTPUT_DIR>/clips/<clip_id>_sub.mp4  and
      updates clip["path"] to the new path.
  5.  Cleans up the temporary .ass file.

Clips without a valid path are skipped unchanged.

Sizing note
-----------
We render from a generated ASS file with ``PlayResX``/``PlayResY`` set to the
clip's actual dimensions. This is deliberate: the older ``subtitles=...:
force_style=...`` path gave libass *no* script resolution, so it assumed its
default 384×288 canvas and upscaled — turning FontSize=40 into ~14% of the
frame height (≈265px on a 1920 frame, "the whole screen"). With PlayResY = real
height, FontSize is in real pixels.

Configuration via environment variables (all optional; per-job state overrides
these where available — see ``_subtitles_impl``):
    ADD_SUBTITLES              – "1"/"true" to enable (default: disabled)
    SUBTITLES_WHISPER_MODEL    – Whisper model size (default: "base")
    SUBTITLES_POSITION         – top | middle | bottom (default: bottom)
    SUBTITLES_SIZE             – small | medium | large (default: medium)
    SUBTITLES_FONT_NAME        – font face (default: Arial)
    SUBTITLES_FONT_COLOR       – ASS hex color for primary text (default: &HFFFFFF – white)
    SUBTITLES_OUTLINE_COLOR    – ASS hex color for outline (default: &H000000 – black)
    SUBTITLES_OUTLINE_WIDTH    – integer, outline width in pixels (default: 2)
    SUBTITLES_HIGHLIGHT        – "1"/"true" to highlight the spoken word (default: on)
    SUBTITLES_HIGHLIGHT_COLOR  – ASS hex color for the active word (default: &H00FFFF – yellow)
"""

import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python (used for probe only)

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config
# ---------------------------------------------------------------------------

_WHISPER_MODEL: str    = os.getenv("SUBTITLES_WHISPER_MODEL", "base")
# FontName is REQUIRED for libass to resolve a face on Windows. Without it the
# subtitles filter silently renders nothing (ffmpeg still exits 0).
_FONT_NAME: str        = os.getenv("SUBTITLES_FONT_NAME", "Arial")
_FONT_COLOR: str       = os.getenv("SUBTITLES_FONT_COLOR", "&HFFFFFF")
_OUTLINE_COLOR: str    = os.getenv("SUBTITLES_OUTLINE_COLOR", "&H000000")
_OUTLINE_WIDTH: int    = int(os.getenv("SUBTITLES_OUTLINE_WIDTH", "2"))
_HIGHLIGHT_COLOR: str  = os.getenv("SUBTITLES_HIGHLIGHT_COLOR", "&H00FFFF")  # ASS BGR → yellow
_HIGHLIGHT_ENABLED: bool = os.getenv("SUBTITLES_HIGHLIGHT", "1").strip().lower() in ("1", "true", "yes")
_MAX_WORKERS: int      = 2   # Whisper is CPU-heavy; limit parallelism

_FPS: int             = 60
_VIDEO_CODEC: str     = "libx264"
_AUDIO_CODEC: str     = "aac"
_VIDEO_BITRATE: str   = "8000k"
_AUDIO_BITRATE: str   = "192k"

# --- Position & size mapping ------------------------------------------------
# Position → ASS V4+ Style "Alignment" (numpad layout, centre column):
#   bottom → 2, middle → 5, top → 8.  MarginV is the gap from the top/bottom
# edge (ignored by libass for vertically-centred alignments).
_POSITION_ALIGNMENT: Dict[str, int] = {"bottom": 2, "middle": 5, "top": 8}
_POSITION_MARGIN_V:  Dict[str, int] = {"bottom": 80, "middle": 0, "top": 80}
_DEFAULT_POSITION = "bottom"

# Size → FontSize as a fraction of PlayResY (resolution-independent). On a
# 1920-tall portrait frame these resolve to ≈67 / 86 / 111 px.
_SIZE_FACTOR: Dict[str, float] = {"small": 0.035, "medium": 0.045, "large": 0.058}
_DEFAULT_SIZE = "medium"


# ---------------------------------------------------------------------------
# ASS helpers
# ---------------------------------------------------------------------------

def _seconds_to_ass_ts(seconds: float) -> str:
    """Convert a float seconds value to ASS timestamp format H:MM:SS.cc."""
    seconds = max(0.0, seconds)
    hours   = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs    = int(seconds % 60)
    centis  = int(round((seconds - int(seconds)) * 100))
    if centis == 100:        # rounding can push us to the next second
        centis = 0
        secs += 1
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    """Escape characters that have special meaning inside an ASS event body."""
    # Braces start override blocks; backslash starts escapes — neutralise both
    # so caption text never accidentally turns into formatting tags.
    return (
        text.replace("\\", "\\\\")
            .replace("{", "(")
            .replace("}", ")")
    )


def _approx_word_timings(text: str, start: float, end: float):
    """
    Approximate per-word [start, end] windows within a segment by distributing
    the segment's duration across its words proportional to word length.

    Returns a list of (word, w_start, w_end) tuples. Word timing from YouTube
    captions / parsed SRT is only segment-level, so this gives a "good enough"
    karaoke sync without per-word transcription.
    """
    words = text.split()
    if not words:
        return []
    total_chars = sum(len(w) for w in words)
    duration = max(end - start, 0.0)
    out = []
    t = start
    for w in words:
        share = (len(w) / total_chars) if total_chars else (1.0 / len(words))
        w_end = t + duration * share
        out.append((w, t, w_end))
        t = w_end
    # Pin the final word's end to the segment end to absorb rounding drift.
    if out:
        last_w, last_s, _ = out[-1]
        out[-1] = (last_w, last_s, end)
    return out


def _build_ass(
    segments: List[Dict],
    play_res_w: int,
    play_res_h: int,
    font_size: int,
    alignment: int,
    margin_v: int,
) -> str:
    """
    Build a full ASS subtitle document from segment dicts.

    Accepted segment formats (same as before):
      • Whisper output — keys "start", "end", "text"
      • YouTube captions — keys "start", "duration", "text" (end = start+duration)

    Segments are first sorted and *de-overlapped* (each segment's end is clamped
    to the next segment's start) — YouTube captions routinely overlap, which
    would otherwise stack two lines / two highlights on screen at once.

    When highlighting is enabled each segment produces:
      • one persistent **base** event (layer 0) showing the whole line in the
        normal colour for the full segment, so the line never flickers; and
      • one **highlight** event per word (layer 1) showing the whole line with
        the active word recoloured via ``{\\c<HILITE>}word{\\r}``.

    The highlight events are made strictly non-overlapping (each ends one
    centisecond before the next word starts). This is the key fix for the
    "two words highlighted" artefact: libass renders event end times
    *inclusively*, so contiguous events would both be live on the boundary
    frame and paint two different highlighted words over the same line.
    """
    margin_lr = max(int(play_res_w * 0.06), 20)  # keep lines off the edges

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"             # libass smart auto-wrap — no manual \\N needed
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {play_res_w}\n"
        f"PlayResY: {play_res_h}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{_FONT_NAME},{font_size},{_FONT_COLOR},&H000000FF,"
        f"{_OUTLINE_COLOR},&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{_OUTLINE_WIDTH},0,{alignment},{margin_lr},{margin_lr},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    events: List[str] = []

    def _dialogue(layer: int, start: float, end: float, body: str) -> str:
        return (
            f"Dialogue: {layer},{_seconds_to_ass_ts(start)},{_seconds_to_ass_ts(end)},"
            f"Default,,0,0,0,,{body}\n"
        )

    # --- Normalise: drop empties, sort by start, clamp out overlaps ----------
    norm: List[Dict[str, float]] = []
    raw = sorted(
        (
            {
                "text": (s.get("text") or "").strip(),
                "start": float(s["start"]),
                "end": float(s["end"]) if "end" in s
                       else float(s["start"]) + float(s.get("duration", 2.0)),
            }
            for s in segments
            if (s.get("text") or "").strip()
        ),
        key=lambda s: s["start"],
    )
    for i, s in enumerate(raw):
        end = s["end"]
        if i + 1 < len(raw):
            end = min(end, raw[i + 1]["start"])  # de-overlap with next caption
        if end > s["start"]:
            norm.append({**s, "end": end})

    _HL_GAP = 0.01  # 1 centisecond — separates consecutive highlight events

    for seg in norm:
        start, end, text = seg["start"], seg["end"], seg["text"]

        if not _HIGHLIGHT_ENABLED:
            events.append(_dialogue(0, start, end, _ass_escape(text)))
            continue

        # Base layer: full line, normal colour, always on for the whole segment.
        events.append(_dialogue(0, start, end, _ass_escape(text)))

        # Highlight layer: one non-overlapping event per word.
        words = _approx_word_timings(text, start, end)
        for idx, (_, w_start, w_end) in enumerate(words):
            hl_end = w_end - _HL_GAP
            if hl_end <= w_start:        # ultra-short word — keep it visible
                hl_end = w_end
            parts = []
            for j, (wj, _, _) in enumerate(words):
                tok = _ass_escape(wj)
                parts.append(f"{{\\c{_HIGHLIGHT_COLOR}}}{tok}{{\\r}}" if j == idx else tok)
            events.append(_dialogue(1, w_start, hl_end, " ".join(parts)))

    return header + "".join(events)


# ---------------------------------------------------------------------------
# Helper: slice global timed segments to a clip's time window
# ---------------------------------------------------------------------------

def _slice_timed_segments(
    timed_segments: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> List[Dict[str, Any]]:
    """
    Return a *new* list of timed segments that overlap with [clip_start, clip_end],
    with timestamps re-zeroed relative to *clip_start* (so they line up with
    the extracted clip which starts at t=0).

    Any segment that is at least partially within the clip window is included.
    """
    sliced: List[Dict[str, Any]] = []
    for seg in timed_segments:
        s_start = float(seg["start"])
        duration = float(seg.get("duration", 2.0))
        s_end   = s_start + duration

        # Skip segments entirely outside the clip window
        if s_end <= clip_start or s_start >= clip_end:
            continue

        # Re-zero the timestamps relative to clip_start
        rel_start = max(s_start - clip_start, 0.0)
        rel_end   = min(s_end - clip_start, clip_end - clip_start)

        sliced.append({
            "text":     seg["text"],
            "start":    rel_start,
            "end":      rel_end,
            "duration": rel_end - rel_start,
        })

    return sliced


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _burn_subtitles(
    clip: ClipObject,
    clips_dir: Path,
    timed_segments: Optional[List[Dict[str, Any]]],
    position: str = _DEFAULT_POSITION,
    size: str = _DEFAULT_SIZE,
) -> ClipObject:
    """
    Obtain subtitle segments and burn them into *clip*.

    If *timed_segments* is provided (YouTube captions already in state), the
    global segments are sliced to the clip's time window — **no Whisper**.
    Otherwise Whisper is loaded and run on the clip file as a fallback.

    *position* (top|middle|bottom) and *size* (small|medium|large) drive the
    generated ASS Style alignment/margins and font size.

    Returns updated ClipObject with path pointing to *_sub.mp4.
    On failure, returns original clip unchanged.
    """
    clip_id   = clip["clip_id"]
    main_path = clip.get("path")

    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    if not main_path or not Path(main_path).exists():
        logger.warning(
            f"SubtitlesNode: skipping {clip_id} — clip path missing or not found."
        )
        return updated

    out_path = str(clips_dir / f"{clip_id}_sub.mp4")
    clip_start, clip_end = clip["timestamp_range"]

    try:
        # ------------------------------------------------------------------
        # Obtain segments
        # ------------------------------------------------------------------
        if timed_segments:
            segments = _slice_timed_segments(timed_segments, clip_start, clip_end)
            logger.debug(
                f"  {clip_id}: using {len(segments)} timed-transcript segments "
                f"(sliced from global captions, no Whisper)"
            )
            if not segments:
                logger.warning(
                    f"  {clip_id}: no caption segments overlap "
                    f"[{clip_start:.1f}s → {clip_end:.1f}s] — skipping subtitles."
                )
                return updated
        else:
            # Fallback: run Whisper on the clip file
            import whisper

            logger.debug(f"  {clip_id}: loading Whisper '{_WHISPER_MODEL}' model …")
            model = whisper.load_model(_WHISPER_MODEL)

            logger.debug(f"  {clip_id}: transcribing {Path(main_path).name} …")
            result   = model.transcribe(main_path, verbose=False)
            segments = result.get("segments", [])

            if not segments:
                logger.warning(
                    f"  {clip_id}: Whisper returned no segments — skipping subtitles."
                )
                return updated

        # ------------------------------------------------------------------
        # Probe the clip once: read dimensions (for ASS PlayResX/Y, which
        # makes FontSize map to real pixels) and detect an audio stream.
        # ------------------------------------------------------------------
        main_abs = os.path.abspath(main_path)
        out_abs  = os.path.abspath(out_path)

        probe = ffmpeg.probe(main_abs)
        streams = probe["streams"]
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"), None
        )
        play_res_w = int(video_stream["width"]) if video_stream else 1080
        play_res_h = int(video_stream["height"]) if video_stream else 1920

        # Resolve position/size → ASS Style parameters.
        alignment = _POSITION_ALIGNMENT.get(position, _POSITION_ALIGNMENT[_DEFAULT_POSITION])
        margin_v  = _POSITION_MARGIN_V.get(position, _POSITION_MARGIN_V[_DEFAULT_POSITION])
        factor    = _SIZE_FACTOR.get(size, _SIZE_FACTOR[_DEFAULT_SIZE])
        font_size = max(round(play_res_h * factor), 12)

        # ------------------------------------------------------------------
        # Write ASS
        # ------------------------------------------------------------------
        ass_content = _build_ass(
            segments, play_res_w, play_res_h, font_size, alignment, margin_v
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ass", delete=False, encoding="utf-8"
        ) as ass_file:
            ass_file.write(ass_content)
            srt_path = ass_file.name  # name reused by the cleanup block below

        logger.debug(
            f"  {clip_id}: ASS written to {srt_path} "
            f"({len(segments)} segments, {play_res_w}x{play_res_h}, "
            f"font={font_size}, align={alignment}, pos={position}, size={size})"
        )

        # ------------------------------------------------------------------
        # Burn subtitles via ffmpeg  (subprocess — bypasses ffmpeg-python's
        # filter-value backslash-escaping which corrupts Windows paths)
        # ------------------------------------------------------------------
        # Windows-safe subtitle path handling.  The ffmpeg ass/subtitles filter
        # path is a minefield of escaping: a drive-letter colon (C:) is split
        # by the filtergraph parser (two passes), so even an escaped "\:"
        # survives pass 1 only to be re-split in pass 2 — ffmpeg then reads the
        # tail as the filter's 2nd positional arg and errors out.
        #
        # We sidestep the whole problem: run ffmpeg with cwd set to the ASS's
        # directory and reference it by *bare filename* (e.g. tmpXXXX.ass) —
        # no colon, no backslash, nothing to escape.  Because cwd changes, the
        # input/output must be absolute.  cwd= is per-subprocess and
        # thread-safe (unlike os.chdir), so it's safe in the ThreadPoolExecutor.
        srt_dir  = os.path.dirname(os.path.abspath(srt_path))
        srt_name = os.path.basename(srt_path)

        # All styling lives in the ASS file, so the filter is just `ass=<file>`.
        filter_str = f"ass={srt_name}"

        cmd: List[str] = [
            "ffmpeg", "-y",
            "-i", main_abs,
            "-vf", filter_str,
            "-vcodec", _VIDEO_CODEC,
            "-r", str(_FPS),
            "-b:v", _VIDEO_BITRATE,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]
        if has_audio:
            cmd += ["-acodec", _AUDIO_CODEC, "-b:a", _AUDIO_BITRATE]
        cmd.append(out_abs)

        proc = subprocess.run(cmd, capture_output=True, cwd=srt_dir)
        stderr_txt = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exited {proc.returncode}\n{stderr_txt[-600:]}"
            )

        # libass failures (e.g. no usable font) are *silent* — ffmpeg still
        # exits 0 but draws nothing. Surface those warnings so a "subtitles
        # don't appear" run is diagnosable from the logs.
        lowered = stderr_txt.lower()
        if any(tok in lowered for tok in ("fontselect", "glyph", "no usable font")):
            logger.warning(
                f"  ! {clip_id}: libass font warning during subtitle burn — "
                f"text may not render. Set SUBTITLES_FONT_NAME to an installed "
                f"font.\n    {stderr_txt[-400:]}"
            )
        else:
            logger.debug(f"  {clip_id}: ffmpeg stderr tail:\n{stderr_txt[-400:]}")

        # Confirm the output actually exists and is non-trivial before we point
        # the clip at it (guards against a 0-byte / failed write slipping past).
        if not Path(out_path).exists() or Path(out_path).stat().st_size < 1024:
            raise RuntimeError(
                f"subtitled output missing or empty: {out_path}"
            )

        updated["path"] = out_path
        logger.info(
            f"  ✓ {clip_id}: subtitles burned ({len(segments)} segments) "
            f"→ {Path(out_path).name}"
        )

    except (ffmpeg.Error, RuntimeError) as exc:
        logger.error(
            f"  ✗ {clip_id}: ffmpeg error in SubtitlesNode.\n    {exc}"
        )
    except ImportError:
        logger.error(
            "  ✗ SubtitlesNode: openai-whisper is not installed. "
            "Run: pip install openai-whisper"
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error in SubtitlesNode – {exc}")
    finally:
        # Clean up temp ASS file (variable named srt_path for historical reasons)
        try:
            if "srt_path" in dir() and Path(srt_path).exists():
                os.remove(srt_path)
        except OSError:
            pass

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def subtitles_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: burn subtitles into each clip.

    Subtitle source (priority):
      1. state["timed_transcript"] — YouTube captions sliced to each clip's
         window.  Fast, no Whisper model loaded.
      2. Whisper fallback — transcribes each clip file individually.

    Enabled when ADD_SUBTITLES env var is "1"/"true" OR state["add_subtitles"]
    is True.

    Input state keys used:
        generated_clips    – List[ClipObject] from TopTextNode / ContentGenNode
        add_subtitles      – boolean feature flag (optional, overridden by env var)
        subtitle_position  – top|middle|bottom (optional; env SUBTITLES_POSITION)
        subtitle_size      – small|medium|large (optional; env SUBTITLES_SIZE)
        timed_transcript   – optional list of timed caption dicts from YouTube

    Output state keys:
        generated_clips – updated with new path (pointing to *_sub.mp4)
        current_step
    """
    with node_stage(state, "subtitles"):
        return _subtitles_impl(state)


def _subtitles_impl(state: LongToShortsState) -> Dict[str, Any]:
    # Per-job state is the source of truth (set by API runner and CLI). The
    # process-global env var is only a fallback for callers that don't populate
    # state — relying on env alone races across concurrent jobs in the executor.
    state_flag = state.get("add_subtitles")
    if state_flag is None:
        enabled = os.getenv("ADD_SUBTITLES", "").strip().lower() in ("1", "true", "yes")
    else:
        enabled = bool(state_flag)

    if not enabled:
        logger.info("SubtitlesNode: not enabled — skipping.")
        return {"current_step": "subtitles_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("SubtitlesNode: no clips to process.")
        return {"generated_clips": [], "current_step": "subtitles_skipped"}

    # Resolve position/size: per-job state first, env var fallback, then default.
    position = state.get("subtitle_position") or os.getenv("SUBTITLES_POSITION") or _DEFAULT_POSITION
    size     = state.get("subtitle_size") or os.getenv("SUBTITLES_SIZE") or _DEFAULT_SIZE
    position = position if position in _POSITION_ALIGNMENT else _DEFAULT_POSITION
    size     = size if size in _SIZE_FACTOR else _DEFAULT_SIZE

    # Prefer the per-run clips_dir set by ClippingLogicNode; fall back to the
    # legacy flat layout only when this node runs in isolation.
    clips_dir = state.get("clips_dir")
    output_dir = Path(clips_dir) if clips_dir else Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Retrieve timed transcript from state (may be None for local video paths)
    timed_segments: Optional[List[Dict[str, Any]]] = state.get("timed_transcript")

    style_note = f"pos={position}, size={size}, highlight={'on' if _HIGHLIGHT_ENABLED else 'off'}"
    if timed_segments:
        logger.info(
            f"SubtitlesNode: burning subtitles into {len(clips)} clip(s) "
            f"using YouTube captions ({len(timed_segments)} segments, no Whisper) [{style_note}]"
        )
    else:
        logger.info(
            f"SubtitlesNode: burning subtitles into {len(clips)} clip(s) "
            f"using Whisper fallback (whisper={_WHISPER_MODEL}) [{style_note}]"
        )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(
                _burn_subtitles, clip, output_dir, timed_segments, position, size
            ): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"SubtitlesNode: worker raised unexpectedly: {exc}")
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(
        1 for c in final_clips
        if c.get("path") and "_sub.mp4" in (c.get("path") or "")
    )
    logger.info(
        f"SubtitlesNode: {successful}/{len(clips)} clips got subtitles burned."
    )

    return {
        "generated_clips": final_clips,
        "current_step":    "subtitles_burned",
    }
