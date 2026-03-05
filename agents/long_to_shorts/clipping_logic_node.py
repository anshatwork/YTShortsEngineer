"""
agents/long_to_shorts/clipping_logic_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ClippingLogicNode – ffmpeg-python 9:16 clip extraction (Map phase).

For each ClipObject produced by AnalyzeVideoNode:
  1.  Scales the source video to fit entirely within a 9:16 frame
      (1080×1920) preserving the original aspect ratio, then pads the
      remaining space with black bars — no content is ever cropped.
      For a standard 16:9 source this produces horizontal black bars
      above and below the video (letterbox style).
  2.  Re-encodes at 60 fps / 8 Mbps video + 192 kbps AAC audio
      for maximum Shorts quality.
  3.  All clips are processed concurrently via ThreadPoolExecutor.
  4.  On ffmpeg failure, the clip is logged and skipped; the node
      never raises, so the pipeline continues with successful clips.
  5.  Segments shorter than MIN_CLIP_DURATION_SECONDS (30s) are skipped
      so we don't produce very short clips when the LLM returns small ranges.

Output clips are written to  <OUTPUT_DIR>/clips/<clip_id>.mp4
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python

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


# ---------------------------------------------------------------------------
# Core ffmpeg helper
# ---------------------------------------------------------------------------

def extract_9_16_clip(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
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

    has_audio = any(
        s.get("codec_type") == "audio"
        for s in ffmpeg.probe(input_file)["streams"]
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
# Per-clip worker (runs inside thread pool)
# ---------------------------------------------------------------------------

def _process_clip(clip: ClipObject, clips_dir: Path) -> ClipObject:
    """
    Extract a single clip.  Returns an updated ClipObject.
    On failure, *path* stays None and an error is logged.
    """
    clip_id = clip["clip_id"]
    source = clip["source_video_path"]
    start, end = clip["timestamp_range"]

    output_path = clips_dir / f"{clip_id}.mp4"
    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    try:
        extract_9_16_clip(
            input_file=source,
            output_file=str(output_path),
            start=start,
            end=end,
        )
        updated["path"] = str(output_path)
        logger.info(
            f"  ✓ {clip_id}: extracted → {output_path.name} "
            f"({end - start:.1f}s)"
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.error(
            f"  ✗ {clip_id}: ffmpeg failed.\n"
            f"    Reason: {stderr[-300:]}"  # last 300 chars of stderr
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error – {exc}")

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def clipping_logic_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: extract 9:16 clips in parallel (Map phase).

    Input state keys used:
        analyzed_segments – List[ClipObject] from AnalyzeVideoNode
        source_video_path – fallback if clip.source_video_path is empty

    Output state keys:
        generated_clips – List[ClipObject] with path set for successful clips
        current_step
    """
    segments: List[ClipObject] = state.get("analyzed_segments", [])
    fallback_source: str = state.get("source_video_path", "")

    if not segments:
        logger.warning("ClippingLogicNode: no segments to process.")
        return {
            "generated_clips": [],
            "current_step": "clipping_skipped",
        }

    # Ensure output directory exists
    output_dir = Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fill in missing source_video_path from state-level fallback
    for clip in segments:
        if not clip.get("source_video_path"):
            clip["source_video_path"] = fallback_source  # type: ignore[typeddict-item]

    # Log a warning for any segment still under the minimum after AnalyzeVideoNode's
    # duration guarantee — this should never happen, but we process them anyway
    # rather than dropping them (a short clip is better than no clip).
    segments_to_process: List[ClipObject] = []
    for clip in segments:
        start, end = clip["timestamp_range"]
        duration = end - start
        if duration < MIN_CLIP_DURATION_SECONDS:
            logger.warning(
                f"  {clip['clip_id']}: segment is {duration:.1f}s "
                f"(below {MIN_CLIP_DURATION_SECONDS:.0f}s target) — processing anyway "
                f"[{start:.1f}s → {end:.1f}s]"
            )
        segments_to_process.append(clip)

    logger.info(
        f"ClippingLogicNode: extracting {len(segments_to_process)} clips "
        f"(max {_MAX_WORKERS} parallel workers) → {output_dir}"
    )

    # --- Map phase: parallel ffmpeg extraction ---
    results: List[Optional[ClipObject]] = [None] * len(segments_to_process)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_process_clip, clip, output_dir): idx
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

    return {
        "generated_clips": successful,
        "current_step": "clipping_complete",
    }
