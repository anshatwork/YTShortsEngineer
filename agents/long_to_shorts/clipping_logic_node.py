"""
agents/long_to_shorts/clipping_logic_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ClippingLogicNode – ffmpeg-python clip extraction (Map phase).

For each ClipObject produced by AnalyzeVideoNode:
  1.  Extracts the segment in one of two modes controlled by state["clip_mode"]:

      "portrait"   (default) – Scale/pad to 9:16 (1080×1920) with letterbox bars.
                                Standard YouTube Shorts format.

      "fullscreen" – Copy the clip at its native resolution without any
                     scaling or padding.  Useful when the source is already
                     portrait or you want to keep the original frame.

  2.  Re-encodes at 60 fps / 8 Mbps video + 192 kbps AAC audio
      for maximum Shorts quality.
  3.  All clips are processed concurrently via ThreadPoolExecutor.
  4.  On ffmpeg failure, the clip is logged and skipped; the node
      never raises, so the pipeline continues with successful clips.
  5.  Segments shorter than MIN_CLIP_DURATION_SECONDS (30s) are skipped
      so we don't produce very short clips when the LLM returns small ranges.
  6.  Source video is probed once before threading; timestamps are clamped
      to [0, duration] so out-of-bounds ranges produce a clear warning rather
      than a silent ffmpeg failure.

Output clips are written to  <OUTPUT_DIR>/clips/<clip_id>.mp4
"""

import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ffmpeg  # ffmpeg-python

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_WORKERS: int = 4          # Parallel ffmpeg processes
_VIDEO_BITRATE: str = "8000k"  # High-quality for Shorts
_AUDIO_BITRATE: str = "192k"
_FPS: int = 60                 # YouTube Shorts supports 60 fps
_VIDEO_CODEC: str = "libx264"
_AUDIO_CODEC: str = "aac"

# 9:16 output frame dimensions for YouTube Shorts
_OUT_W: int = 1080
_OUT_H: int = 1920
_PAD_COLOR: str = "black"

# Minimum clip duration (seconds). Matches MIN_SEGMENT_SECONDS in analyze_video_node.
# Segments below this are logged as a warning but still processed.
MIN_CLIP_DURATION_SECONDS: float = 35.0

_VALID_CLIP_MODES = {"portrait", "fullscreen"}


# ---------------------------------------------------------------------------
# Per-run output directory resolver
# ---------------------------------------------------------------------------

def _resolve_clips_dir(state: LongToShortsState) -> Tuple[Path, str]:
    """Return ``(clips_dir, run_id)`` for this pipeline invocation.

    Isolates outputs per run so concurrent API jobs and successive CLI runs
    do not overwrite each other:

      * API path  – ``state["job_id"]`` is set by ``api/runner.py`` and is used
        verbatim as the ``run_id``.
      * CLI path  – no job_id, so a fresh ``run_<YYYYMMDD_HHMMSS>_<hex>`` is
        generated.  Hex suffix avoids same-second collisions across processes.

    The resolved directory is ``OUTPUT_DIR/jobs/<run_id>/clips``.
    """
    run_id = state.get("job_id") or state.get("run_id")
    if not run_id:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{stamp}_{secrets.token_hex(3)}"

    base = Path(os.getenv("OUTPUT_DIR", "output"))
    clips_dir = base / "jobs" / run_id / "clips"
    return clips_dir, run_id


# ---------------------------------------------------------------------------
# Source-video probe helper
# ---------------------------------------------------------------------------

def _validate_source(path: str) -> tuple:
    """Probe *path* once and return (duration_seconds, has_audio).

    Raises RuntimeError with the ffmpeg stderr if the file cannot be read,
    so the caller gets a clear error instead of every worker failing silently.
    """
    if not path or not Path(path).exists():
        raise RuntimeError(f"Source video not found: '{path}'")
    try:
        info = ffmpeg.probe(path)
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise RuntimeError(
            f"Cannot read source video '{path}': {stderr[-600:]}"
        ) from exc
    duration = float(info["format"].get("duration", 0))
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    return duration, has_audio


# ---------------------------------------------------------------------------
# Core ffmpeg helper
# ---------------------------------------------------------------------------

def extract_9_16_clip(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    *,
    has_audio: bool = True,
) -> None:
    """
    Extract a 9:16 clip from *input_file*, fitting the entire source frame
    inside a 1080×1920 canvas without cropping any content.

    The source video (typically 16:9) is scaled down so it fits entirely
    within the 9:16 output frame while preserving its original aspect ratio.
    Any remaining canvas space is filled with black bars (letterbox for
    landscape sources, pillarbox for portrait sources that are taller than
    9:16).  No pixel from the source is ever discarded.

    Audio is preserved by passing both streams explicitly to output().
    If the source has no audio, output is video-only.

    Args:
        input_file:  Absolute path to the source video.
        output_file: Absolute path for the output .mp4 clip.
        start:       Start time in seconds.
        end:         End time in seconds.

    Raises:
        ffmpeg.Error: On encoding failure.
        ValueError:   If start >= end.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError(
            f"Invalid segment: start={start}s >= end={end}s"
        )

    logger.debug(
        f"ffmpeg: {os.path.basename(input_file)} "
        f"[{start:.2f}s → {end:.2f}s] ({duration:.2f}s) → {os.path.basename(output_file)}"
    )

    inp = ffmpeg.input(input_file, ss=start, t=duration)

    # Scale the source to fit inside _OUT_W × _OUT_H while keeping its
    # aspect ratio, then pad the canvas to exactly _OUT_W × _OUT_H.
    # The `force_original_aspect_ratio=decrease` flag ensures the video
    # is never enlarged beyond the frame and never cropped.
    # The `force_divisible_by=2` on scale avoids odd-pixel encode errors.
    video = (
        inp.video
        .filter(
            "scale",
            w=_OUT_W,
            h=_OUT_H,
            force_original_aspect_ratio="decrease",
            force_divisible_by=2,
        )
        .filter(
            "pad",
            w=_OUT_W,
            h=_OUT_H,
            x="(ow-iw)/2",
            y="(oh-ih)/2",
            color=_PAD_COLOR,
        )
    )

    if has_audio:
        audio = inp.audio
        out = ffmpeg.output(
            video,
            audio,
            output_file,
            vcodec=_VIDEO_CODEC,
            acodec=_AUDIO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            audio_bitrate=_AUDIO_BITRATE,
            pix_fmt="yuv420p",        # Required by WMP, YouTube, and most devices
            movflags="+faststart",    # Move moov atom to start for streaming / YT upload
        )
    else:
        out = ffmpeg.output(
            video,
            output_file,
            vcodec=_VIDEO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            pix_fmt="yuv420p",
            movflags="+faststart",
        )

    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


# ---------------------------------------------------------------------------
# Fullscreen (native-resolution) clip extractor
# ---------------------------------------------------------------------------

def extract_fullscreen_clip(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    *,
    has_audio: bool = True,
) -> None:
    """
    Extract a clip from *input_file* at its **native resolution** — no
    scaling, no padding, no reframing.  Use this when the source is already
    portrait or when you want to preserve the original frame exactly.

    Args:
        input_file:  Absolute path to the source video.
        output_file: Absolute path for the output .mp4 clip.
        start:       Start time in seconds.
        end:         End time in seconds.

    Raises:
        ffmpeg.Error: On encoding failure.
        ValueError:   If start >= end.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError(
            f"Invalid segment: start={start}s >= end={end}s"
        )

    logger.debug(
        f"ffmpeg (fullscreen): {os.path.basename(input_file)} "
        f"[{start:.2f}s → {end:.2f}s] ({duration:.2f}s) → {os.path.basename(output_file)}"
    )

    inp = ffmpeg.input(input_file, ss=start, t=duration)

    if has_audio:
        out = ffmpeg.output(
            inp.video,
            inp.audio,
            output_file,
            vcodec=_VIDEO_CODEC,
            acodec=_AUDIO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            audio_bitrate=_AUDIO_BITRATE,
            pix_fmt="yuv420p",
            movflags="+faststart",
        )
    else:
        out = ffmpeg.output(
            inp.video,
            output_file,
            vcodec=_VIDEO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            pix_fmt="yuv420p",
            movflags="+faststart",
        )

    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


# ---------------------------------------------------------------------------
# Per-clip worker (runs inside thread pool)
# ---------------------------------------------------------------------------

def _process_clip(
    clip: ClipObject,
    clips_dir: Path,
    clip_mode: str = "portrait",
    has_audio: bool = True,
) -> ClipObject:
    """
    Extract a single clip in the requested *clip_mode*.
    Returns an updated ClipObject.  On failure *path* stays None and an
    error is logged.

    clip_mode:
        "portrait"   – 9:16 letterbox/pillarbox (default)
        "fullscreen" – Native resolution, no reframing
    """
    clip_id = clip["clip_id"]
    source = clip["source_video_path"]
    start, end = clip["timestamp_range"]

    output_path = clips_dir / f"{clip_id}.mp4"
    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    try:
        if clip_mode == "fullscreen":
            extract_fullscreen_clip(
                input_file=source,
                output_file=str(output_path),
                start=start,
                end=end,
                has_audio=has_audio,
            )
        else:
            extract_9_16_clip(
                input_file=source,
                output_file=str(output_path),
                start=start,
                end=end,
                has_audio=has_audio,
            )
        updated["path"] = str(output_path)
        logger.info(
            f"  ✓ {clip_id}: extracted [{clip_mode}] → {output_path.name} "
            f"({end - start:.1f}s)"
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.error(
            f"  ✗ {clip_id}: ffmpeg failed.\n"
            f"    Reason: {stderr[-1000:]}"
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error – {exc}")

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def clipping_logic_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: extract clips in parallel (Map phase).

    Input state keys used:
        analyzed_segments – List[ClipObject] from AnalyzeVideoNode
        source_video_path – fallback if clip.source_video_path is empty
        clip_mode         – "portrait" (default) or "fullscreen"
        job_id            – when present (API runs), used as run_id

    Output state keys:
        generated_clips – List[ClipObject] with path set for successful clips
        clips_dir       – Resolved per-run output directory; downstream nodes
                          (intro, subtitles, top_text) write into the same dir
        run_id          – job_id for API runs, generated for CLI runs
        current_step
    """
    with node_stage(state, "clipping_logic"):
        return _clipping_logic_impl(state)


def _clipping_logic_impl(state: LongToShortsState) -> Dict[str, Any]:
    segments: List[ClipObject] = state.get("analyzed_segments", [])
    fallback_source: str = state.get("source_video_path", "")
    clip_mode: str = state.get("clip_mode", "portrait")

    # Resolve per-run output directory up front so it is available on every
    # return path — downstream nodes read clips_dir from state.
    output_dir, run_id = _resolve_clips_dir(state)
    clips_dir_str = str(output_dir)

    if not segments:
        logger.warning("ClippingLogicNode: no segments to process.")
        return {
            "generated_clips": [],
            "current_step": "clipping_skipped",
            "clips_dir": clips_dir_str,
            "run_id": run_id,
        }

    # Validate and normalise clip_mode
    if clip_mode not in _VALID_CLIP_MODES:
        logger.warning(
            f"ClippingLogicNode: unknown clip_mode '{clip_mode}', defaulting to 'portrait'."
        )
        clip_mode = "portrait"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Fill in missing source_video_path from state-level fallback
    for clip in segments:
        if not clip.get("source_video_path"):
            clip["source_video_path"] = fallback_source  # type: ignore[typeddict-item]

    # --- Pre-validate unique source files (probe once, fail fast) ---
    source_info: dict = {}  # path -> (duration, has_audio)
    unique_sources = {c["source_video_path"] for c in segments}
    for src in unique_sources:
        try:
            source_info[src] = _validate_source(src)
        except RuntimeError as exc:
            logger.error(f"ClippingLogicNode: {exc}")
            return {
                "generated_clips": [],
                "current_step": "clipping_failed",
                "error": str(exc),
                "clips_dir": clips_dir_str,
                "run_id": run_id,
            }

    # --- Clamp timestamps to [0, duration] and filter degenerate clips ---
    segments_to_process: List[ClipObject] = []
    for clip in segments:
        clip_id = clip["clip_id"]
        start, end = clip["timestamp_range"]
        video_duration, has_audio = source_info[clip["source_video_path"]]

        clamped_start = max(0.0, start)
        clamped_end = min(video_duration, end) if video_duration > 0 else end

        if clamped_start != start or clamped_end != end:
            logger.warning(
                f"  {clip_id}: timestamps clamped "
                f"[{start:.1f}s→{end:.1f}s] → [{clamped_start:.1f}s→{clamped_end:.1f}s] "
                f"(video duration: {video_duration:.1f}s)"
            )
            clip = dict(clip)  # type: ignore[assignment]
            clip["timestamp_range"] = (clamped_start, clamped_end)  # type: ignore[typeddict-item]

        duration = clamped_end - clamped_start
        if duration <= 0:
            logger.error(
                f"  {clip_id}: skipped — zero/negative duration after clamping "
                f"({clamped_start:.1f}s → {clamped_end:.1f}s)"
            )
            continue

        if duration < MIN_CLIP_DURATION_SECONDS:
            logger.warning(
                f"  {clip_id}: segment is {duration:.1f}s "
                f"(below {MIN_CLIP_DURATION_SECONDS:.0f}s target) — processing anyway "
                f"[{clamped_start:.1f}s → {clamped_end:.1f}s]"
            )

        segments_to_process.append(clip)

    if not segments_to_process:
        return {
            "generated_clips": [],
            "current_step": "clipping_failed",
            "error": "All segments were skipped after timestamp validation.",
            "clips_dir": clips_dir_str,
            "run_id": run_id,
        }

    logger.info(
        f"ClippingLogicNode: extracting {len(segments_to_process)} clips "
        f"[mode={clip_mode}] (max {_MAX_WORKERS} parallel workers) → {output_dir}"
    )

    # --- Map phase: parallel ffmpeg extraction ---
    results: List[Optional[ClipObject]] = [None] * len(segments_to_process)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(
                _process_clip,
                clip,
                output_dir,
                clip_mode,
                source_info[clip["source_video_path"]][1],  # has_audio
            ): idx
            for idx, clip in enumerate(segments_to_process)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"ClippingLogicNode: worker raised unexpectedly: {exc}")
                results[idx] = segments_to_process[idx]  # keep original (path=None)

    # Only keep clips that were successfully extracted
    successful: List[ClipObject] = [
        r for r in results if r is not None and r.get("path") is not None
    ]

    logger.info(
        f"ClippingLogicNode: {len(successful)}/{len(segments_to_process)} clips extracted successfully."
    )

    if not successful:
        return {
            "generated_clips": [],
            "current_step": "clipping_failed",
            "error": f"All {len(segments_to_process)} clip(s) failed to extract.",
            "clips_dir": clips_dir_str,
            "run_id": run_id,
        }

    return {
        "generated_clips": successful,
        "current_step": "clipping_complete",
        "clips_dir": clips_dir_str,
        "run_id": run_id,
    }
