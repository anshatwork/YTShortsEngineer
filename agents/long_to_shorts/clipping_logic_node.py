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
import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ffmpeg  # ffmpeg-python

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# Bump to invalidate cached extracted clips when the ffmpeg encode changes.
# v2: split-encode-concat parts (closed-GOP), single full-range audio mux,
#     configurable preset and fps.
_CLIP_EXTRACT_CACHE_VERSION: int = 2


# ---------------------------------------------------------------------------
# Tunables (read via os.getenv so they work even if Settings fails to load;
# declared/documented in core/config.py)
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Number of parallel ffmpeg part encoders. 0 -> os.cpu_count().
_CLIP_WORKERS: int = _env_int("CLIP_WORKER_THREADS", 0) or (os.cpu_count() or 4)
# libx264 internal threads per part — kept small so part-parallelism (not
# intra-encode threads) drives CPU utilisation and total load stays bounded.
_FFMPEG_THREADS_PER_PART: int = _env_int("FFMPEG_THREADS_PER_PART", 2)
# Part planning.
_PART_TARGET_SECONDS: float = _env_float("CLIP_PART_TARGET_SECONDS", 20.0)
_PART_MIN_SECONDS: float = _env_float("CLIP_PART_MIN_SECONDS", 45.0)
_MAX_PARTS_PER_CLIP: int = _env_int("CLIP_MAX_PARTS", 8)
# Encode quick wins.
_X264_PRESET: str = os.getenv("CLIP_X264_PRESET", "medium") or "medium"
# Output fps; 0 -> preserve source fps (omit -r).
_FORCE_FPS: int = _env_int("CLIP_FORCE_FPS", _FPS)


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
        # CLI runs have no job_id. Derive a DETERMINISTIC run_id from the inputs
        # (source + mode + top_n + transcript) instead of a random hex suffix, so
        # re-running the same CLI command reuses the same output directory and the
        # content-addressable cache makes the whole run idempotent.
        from core.cache.keys import file_signature, hash_text, make_key
        fingerprint = make_key(
            "cli_run", 1,
            {
                "src": file_signature(state.get("source_video_path", "")),
                "mode": state.get("clip_mode", "portrait"),
                "top_n": state.get("top_n_clips", 5),
                "transcript": hash_text(state.get("transcript", "") or ""),
            },
        )
        run_id = f"run_{fingerprint[:16]}"

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
# Shared filtergraph builders
# ---------------------------------------------------------------------------

def _build_portrait_video(inp: Any) -> Any:
    """Scale the source to fit inside _OUT_W × _OUT_H keeping aspect ratio,
    then pad to exactly _OUT_W × _OUT_H with black bars. Never crops or
    enlarges. ``force_divisible_by=2`` avoids odd-pixel encode errors."""
    return (
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


def _build_clip_video(inp: Any, clip_mode: str) -> Any:
    """Return the processed video stream for *clip_mode*.

    "fullscreen" keeps native resolution; "portrait" applies scale+pad.
    """
    if clip_mode == "fullscreen":
        return inp.video
    return _build_portrait_video(inp)


def _fps_kwargs(fps: int) -> dict:
    """``{'r': fps}`` when fps > 0, else ``{}`` to preserve the source fps."""
    return {"r": fps} if fps and fps > 0 else {}


# ---------------------------------------------------------------------------
# Single-pass extractors (used when a clip is short enough not to be split)
# ---------------------------------------------------------------------------

def extract_9_16_clip(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    *,
    has_audio: bool = True,
    preset: str = _X264_PRESET,
    fps: int = _FORCE_FPS,
) -> None:
    """
    Extract a 9:16 clip from *input_file* in a single ffmpeg pass, fitting the
    entire source frame inside a 1080×1920 canvas without cropping any content.

    Args:
        input_file:  Absolute path to the source video.
        output_file: Absolute path for the output .mp4 clip.
        start:       Start time in seconds.
        end:         End time in seconds.
        has_audio:   Whether to map an audio stream.
        preset:      libx264 preset.
        fps:         Output frame rate; 0 preserves the source fps.

    Raises:
        ffmpeg.Error: On encoding failure.
        ValueError:   If start >= end.
    """
    _extract_single_pass(
        input_file, output_file, start, end, "portrait",
        has_audio=has_audio, preset=preset, fps=fps,
    )


def extract_fullscreen_clip(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    *,
    has_audio: bool = True,
    preset: str = _X264_PRESET,
    fps: int = _FORCE_FPS,
) -> None:
    """
    Extract a clip from *input_file* at its **native resolution** in a single
    ffmpeg pass — no scaling, no padding, no reframing.
    """
    _extract_single_pass(
        input_file, output_file, start, end, "fullscreen",
        has_audio=has_audio, preset=preset, fps=fps,
    )


def _extract_single_pass(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    clip_mode: str,
    *,
    has_audio: bool,
    preset: str,
    fps: int,
) -> None:
    """Extract a full clip (video + optional audio) in one ffmpeg pass."""
    duration = end - start
    if duration <= 0:
        raise ValueError(f"Invalid segment: start={start}s >= end={end}s")

    logger.debug(
        f"ffmpeg [{clip_mode}]: {os.path.basename(input_file)} "
        f"[{start:.2f}s → {end:.2f}s] ({duration:.2f}s) → {os.path.basename(output_file)}"
    )

    inp = ffmpeg.input(input_file, ss=start, t=duration)
    video = _build_clip_video(inp, clip_mode)

    common = dict(
        vcodec=_VIDEO_CODEC,
        preset=preset,
        video_bitrate=_VIDEO_BITRATE,
        pix_fmt="yuv420p",        # Required by WMP, YouTube, and most devices
        movflags="+faststart",    # Move moov atom to start for streaming / YT upload
        **_fps_kwargs(fps),
    )
    if has_audio:
        out = ffmpeg.output(
            video, inp.audio, output_file,
            acodec=_AUDIO_CODEC, audio_bitrate=_AUDIO_BITRATE, **common,
        )
    else:
        out = ffmpeg.output(video, output_file, **common)

    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


# ---------------------------------------------------------------------------
# Part-based extraction (split → parallel encode → lossless concat)
# ---------------------------------------------------------------------------

def _plan_parts(start: float, end: float) -> List[Tuple[float, float]]:
    """Divide ``[start, end]`` into time-based parts for parallel encoding.

    Clips shorter than ``_PART_MIN_SECONDS`` are returned as a single part so
    they take the single-pass path (no concat overhead). The last part's end
    is pinned exactly to ``end`` so no frames are lost to rounding.
    """
    duration = end - start
    if duration < _PART_MIN_SECONDS or _MAX_PARTS_PER_CLIP <= 1:
        return [(start, end)]
    n = min(_MAX_PARTS_PER_CLIP, max(2, round(duration / _PART_TARGET_SECONDS)))
    step = duration / n
    parts: List[Tuple[float, float]] = []
    for i in range(n):
        s = start + i * step
        e = end if i == n - 1 else start + (i + 1) * step
        parts.append((s, e))
    return parts


def _encode_video_part(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
    clip_mode: str,
    preset: str,
    fps: int,
    threads: int,
) -> None:
    """Encode a single VIDEO-ONLY part with a closed GOP so the parts can be
    concatenated losslessly with the concat demuxer (``-c copy``)."""
    duration = end - start
    if duration <= 0:
        raise ValueError(f"Invalid part: start={start}s >= end={end}s")

    inp = ffmpeg.input(input_file, ss=start, t=duration)
    video = _build_clip_video(inp, clip_mode)

    # Closed GOP: force a keyframe at least every `keyint` frames and disable
    # scenecut/open-GOP so no B-frames reference across a concat boundary.
    keyint = max(1, int(round((fps if fps and fps > 0 else 30) * 2)))
    out = ffmpeg.output(
        video,
        output_file,
        vcodec=_VIDEO_CODEC,
        preset=preset,
        video_bitrate=_VIDEO_BITRATE,
        pix_fmt="yuv420p",
        g=keyint,
        threads=threads,
        an=None,  # video only — audio is encoded once over the full range
        **{"x264-params": f"scenecut=0:keyint={keyint}:min-keyint={keyint}"},
        **_fps_kwargs(fps),
    )
    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


def _encode_audio_track(
    input_file: str,
    output_file: str,
    start: float,
    end: float,
) -> None:
    """Encode the clip's audio once over the full ``[start, end]`` range so
    there are no per-part AAC priming gaps."""
    duration = end - start
    inp = ffmpeg.input(input_file, ss=start, t=duration)
    out = ffmpeg.output(
        inp.audio,
        output_file,
        acodec=_AUDIO_CODEC,
        audio_bitrate=_AUDIO_BITRATE,
        vn=None,  # audio only
    )
    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


def _concat_parts(
    part_files: List[str],
    audio_file: Optional[str],
    dest: str,
    list_path: Path,
) -> None:
    """Concatenate video *part_files* losslessly and mux the single *audio_file*.

    Uses the ffmpeg concat demuxer with stream copy, so the join is near-instant
    and re-encode-free. Paths in the list are written *absolute* with forward
    slashes: the concat demuxer resolves relative entries against the list file's
    own directory (not the process cwd), so a project-relative part path would be
    doubled onto the list dir. Absolute paths sidestep that (-safe 0 allows them);
    forward slashes are accepted on Windows and avoid backslash escaping."""
    lines = [f"file '{Path(p).resolve().as_posix()}'\n" for p in part_files]
    list_path.write_text("".join(lines), encoding="utf-8")

    cmd: List[str] = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
    ]
    if audio_file:
        cmd += ["-i", audio_file, "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0"]
    cmd += ["-c", "copy", "-movflags", "+faststart"]
    if audio_file:
        cmd += ["-shortest"]
    cmd += [dest]

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"concat failed: {stderr[-1000:]}")


def _produce_clip(
    dest: Path,
    source: str,
    start: float,
    end: float,
    clip_mode: str,
    has_audio: bool,
    preset: str,
    fps: int,
    parts_pool: ThreadPoolExecutor,
    tmp_dir: Path,
) -> None:
    """Produce the final clip at *dest*.

    Plans parts; for a single part falls back to a single-pass extract. For
    multiple parts, encodes video parts (and the full-range audio) in parallel
    on the shared *parts_pool*, then concatenates losslessly into *dest*.
    Temp artifacts under *tmp_dir* are always cleaned up.
    """
    parts = _plan_parts(start, end)

    if len(parts) == 1:
        _extract_single_pass(
            source, str(dest), start, end, clip_mode,
            has_audio=has_audio, preset=preset, fps=fps,
        )
        return

    try:
        _produce_clip_chunked(
            dest, source, start, end, clip_mode, has_audio,
            preset, fps, parts_pool, tmp_dir, parts,
        )
    except Exception as exc:  # noqa: BLE001
        # The chunked split-encode-concat path is an optimization; if it fails on
        # a particular source (odd timebase / VFR / concat quirk), degrade to the
        # proven single-pass encoder rather than failing the whole clip. Slower,
        # but it produces a correct clip — the optimization never regresses
        # reliability versus the original behavior.
        logger.warning(
            "chunked extraction failed (%s); falling back to single-pass for %s",
            exc, dest.name, exc_info=True,
        )
        _extract_single_pass(
            source, str(dest), start, end, clip_mode,
            has_audio=has_audio, preset=preset, fps=fps,
        )


def _produce_clip_chunked(
    dest: Path,
    source: str,
    start: float,
    end: float,
    clip_mode: str,
    has_audio: bool,
    preset: str,
    fps: int,
    parts_pool: ThreadPoolExecutor,
    tmp_dir: Path,
    parts: List[Tuple[float, float]],
) -> None:
    """Encode *parts* in parallel and concatenate them losslessly into *dest*."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        part_files: List[str] = [
            str(tmp_dir / f"p{idx:03d}.mp4") for idx in range(len(parts))
        ]
        futures: List[Future] = []
        for (ps, pe), pf in zip(parts, part_files):
            futures.append(parts_pool.submit(
                _encode_video_part,
                source, pf, ps, pe, clip_mode, preset, fps,
                _FFMPEG_THREADS_PER_PART,
            ))

        audio_file: Optional[str] = None
        if has_audio:
            audio_file = str(tmp_dir / "audio.m4a")
            futures.append(parts_pool.submit(
                _encode_audio_track, source, audio_file, start, end,
            ))

        # Surface the first failure; all futures are awaited so no part keeps
        # running while we tear down.
        done, _ = wait(futures)
        for fut in done:
            fut.result()  # re-raises any encode error

        _concat_parts(part_files, audio_file, str(dest), tmp_dir / "concat_list.txt")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Per-clip worker (runs inside thread pool)
# ---------------------------------------------------------------------------

def _process_clip(
    clip: ClipObject,
    clips_dir: Path,
    clip_mode: str = "portrait",
    has_audio: bool = True,
    parts_pool: Optional[ThreadPoolExecutor] = None,
) -> ClipObject:
    """
    Extract a single clip in the requested *clip_mode*.
    Returns an updated ClipObject.  On failure *path* stays None and an
    error is logged.

    clip_mode:
        "portrait"   – 9:16 letterbox/pillarbox (default)
        "fullscreen" – Native resolution, no reframing

    parts_pool:
        Shared executor onto which the clip's parallel parts are submitted.
        When None (e.g. direct unit-test calls) a private single-worker pool
        is used so the clip still encodes correctly.
    """
    clip_id = clip["clip_id"]
    source = clip["source_video_path"]
    start, end = clip["timestamp_range"]

    output_path = clips_dir / f"{clip_id}.mp4"
    tmp_dir = clips_dir / ".parts" / clip_id
    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    preset = _X264_PRESET
    fps = _FORCE_FPS

    def _produce(dest: Path) -> None:
        pool = parts_pool
        own_pool: Optional[ThreadPoolExecutor] = None
        if pool is None:
            own_pool = ThreadPoolExecutor(max_workers=_CLIP_WORKERS)
            pool = own_pool
        try:
            _produce_clip(
                dest, source, start, end, clip_mode, has_audio,
                preset, fps, pool, tmp_dir,
            )
        finally:
            if own_pool is not None:
                own_pool.shutdown()

    try:
        # Content-addressable extraction: identical (source, range, mode, preset,
        # fps) reuses a previously-rendered clip from the CAS instead of
        # re-encoding — across jobs, and (once on object storage) across machines.
        # Also gives the idempotency "skip if a valid output already exists"
        # guarantee.
        from core.cache import get_cache
        from core.cache.keys import file_signature
        cache_inputs = {
            "src": file_signature(source),
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "mode": clip_mode,
            "has_audio": bool(has_audio),
            "preset": preset,
            "fps": int(fps),
        }
        result = get_cache().materialize_blob(
            "clip_extract", _CLIP_EXTRACT_CACHE_VERSION,
            cache_inputs, output_path, _produce, ext=".mp4",
        )
        updated["path"] = str(output_path)
        logger.info(
            f"  {'⟳' if result.hit else '✓'} {clip_id}: "
            f"{'reused cached' if result.hit else 'extracted'} [{clip_mode}] → "
            f"{output_path.name} ({end - start:.1f}s)"
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        reason = stderr.strip().splitlines()[-1] if stderr.strip() else str(exc)
        updated["error"] = f"ffmpeg failed: {reason}"  # type: ignore[typeddict-unknown-key]
        logger.error(
            f"  ✗ {clip_id}: ffmpeg failed.\n"
            f"    Reason: {stderr[-1000:]}",
            exc_info=True,
        )
    except Exception as exc:
        updated["error"] = str(exc)  # type: ignore[typeddict-unknown-key]
        logger.error(f"  ✗ {clip_id}: unexpected error – {exc}", exc_info=True)

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
        f"[mode={clip_mode}] (split into parallel parts, {_CLIP_WORKERS} part "
        f"workers, preset={_X264_PRESET}, fps={_FORCE_FPS or 'source'}) → {output_dir}"
    )

    # --- Map phase: each clip is split into parts that run on one shared,
    # bounded pool, so total concurrent ffmpeg processes stay ≈ _CLIP_WORKERS
    # regardless of clip count × part count. Clips are coordinated
    # sequentially; one clip's parts already saturate the pool. ---
    results: List[Optional[ClipObject]] = [None] * len(segments_to_process)

    parts_pool = ThreadPoolExecutor(max_workers=_CLIP_WORKERS)
    try:
        for idx, clip in enumerate(segments_to_process):
            try:
                results[idx] = _process_clip(
                    clip,
                    output_dir,
                    clip_mode,
                    source_info[clip["source_video_path"]][1],  # has_audio
                    parts_pool,
                )
            except Exception as exc:
                logger.error(f"ClippingLogicNode: worker raised unexpectedly: {exc}")
                results[idx] = segments_to_process[idx]  # keep original (path=None)
    finally:
        parts_pool.shutdown()

    # Only keep clips that were successfully extracted
    successful: List[ClipObject] = [
        r for r in results if r is not None and r.get("path") is not None
    ]

    logger.info(
        f"ClippingLogicNode: {len(successful)}/{len(segments_to_process)} clips extracted successfully."
    )

    # Make a partial failure obvious — otherwise a job "succeeds" while silently
    # dropping clips. Name the ones that failed so they're easy to trace.
    if successful and len(successful) < len(segments_to_process):
        succeeded_ids = {c["clip_id"] for c in successful}
        failed_ids = [
            c["clip_id"] for c in segments_to_process
            if c["clip_id"] not in succeeded_ids
        ]
        logger.warning(
            "ClippingLogicNode: PARTIAL FAILURE — %d of %d clip(s) failed: %s "
            "(see the per-clip ✗ tracebacks above)",
            len(failed_ids), len(segments_to_process), ", ".join(failed_ids),
        )

    if not successful:
        # Surface the actual ffmpeg reason(s) so the job error is debuggable
        # instead of a generic "all failed". De-duplicate identical reasons.
        reasons: List[str] = []
        for r in results:
            reason = r.get("error") if isinstance(r, dict) else None  # type: ignore[union-attr]
            if reason and reason not in reasons:
                reasons.append(reason)
        detail = f"  Reason: {reasons[0]}" if reasons else ""
        if len(reasons) > 1:
            detail += f" (+{len(reasons) - 1} other distinct error(s))"
        return {
            "generated_clips": [],
            "current_step": "clipping_failed",
            "error": (
                f"All {len(segments_to_process)} clip(s) failed to extract."
                + (f"\n{detail}" if detail else "")
            ),
            "clips_dir": clips_dir_str,
            "run_id": run_id,
        }

    return {
        "generated_clips": successful,
        "current_step": "clipping_complete",
        "clips_dir": clips_dir_str,
        "run_id": run_id,
    }
