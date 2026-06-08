"""
run_clipping_workflow.py
========================
REAL end-to-end workflow: Long-to-Shorts clip generation from a local video
or a YouTube URL.

Usage
-----
    # Local video
    python run_clipping_workflow.py [VIDEO_PATH] [TRANSCRIPT_TEXT_OR_PATH] [TOP_N]
        [--subtitles] [--subtitle-position {top,middle,bottom}]
        [--subtitle-size {small,medium,large}] [--top-text] [--no-intro] [--fullscreen]

    # YouTube URL
    python run_clipping_workflow.py <YouTube-URL> [TOP_N]
        [--subtitles] [--subtitle-position {top,middle,bottom}]
        [--subtitle-size {small,medium,large}] [--top-text] [--no-intro] [--fullscreen]

Optional feature flags
----------------------
    --subtitles    Burn auto-generated subtitles onto each clip.
                   For YouTube URLs, subtitles are built from the already-fetched
                   captions (no Whisper).  For local videos, Whisper is used as
                   a fallback.  The spoken word is highlighted in sync with the
                   captions (approximate per-word timing).
    --subtitle-position {top,middle,bottom}
                   Vertical placement of the captions (default: bottom).
    --subtitle-size {small,medium,large}
                   Caption font-size preset (default: medium).
    --top-text     Overlay the LLM hook text at the top of each clip
    --no-intro     Skip the title-card intro prepended by IntroAttachNode
    --fullscreen   Clip at the video's native resolution (no 9:16 reframing).
                   Default: portrait 9:16 (1080×1920) with letterbox bars.

Defaults
--------
    VIDEO_PATH  = assets/ailover.mp4
    TOP_N       = 3
    intro       = ON   (disable with --no-intro)
    subtitles   = OFF  (enable with --subtitles; pos=bottom, size=medium)
    top-text    = OFF  (enable with --top-text)
    clip-mode   = portrait 9:16  (switch to native res with --fullscreen)

How it works (YouTube URL path)
--------------------------------
1. Detects that the first argument is a YouTube URL.
2. Extracts the video ID and downloads the video to output/downloads/<id>.mp4
   using tools.youtube.downloader (yt-dlp under the hood).
3. Fetches the transcript from YouTube captions via youtube-transcript-api
   (no Whisper, no OAuth required).  Timed segments are also stored so
   SubtitlesNode can burn them without re-running Whisper.
4. Runs the full LangGraph Long-to-Shorts pipeline:
      AnalyzeVideoNode → ClippingLogicNode → ContentGenNode
        → TopTextNode → SubtitlesNode → IntroAttachNode
5. Prints a summary of every clip with path, hook score, title, summary,
   hook overlay text, and hashtags.
6. All clips are written to  output/clips/

How it works (local video path)
---------------------------------
1. Probes the video with ffmpeg to confirm it is readable.
2. Accepts a transcript string or path to a .txt file.
   If no transcript is supplied, it uses Whisper (base model) to auto-transcribe
   the first 10 minutes of audio from the video.
3–6. Same as above.  Subtitles use Whisper (no timed transcript available).

Dependencies already in requirements.txt:
    ffmpeg-python, openai-whisper (for auto-transcription / subtitle fallback),
    yt-dlp, youtube-transcript-api
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

# ------------------------------------------------------------------
# Ensure the project root is on sys.path when run directly
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ------------------------------------------------------------------
# Load .env  (optional – graceful if missing)
# ------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[ENV] .env loaded")
except ImportError:
    print("[ENV] python-dotenv not installed; relying on shell environment")

# ------------------------------------------------------------------
# Pretty-print helpers
# ------------------------------------------------------------------
SEP  = "=" * 68
SEP2 = "-" * 68

def section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg: str):
    print(f"  ✓  {msg}")

def warn(msg: str):
    print(f"  ⚠  {msg}")

def err(msg: str):
    print(f"  ✗  {msg}")

def info(msg: str):
    print(f"     {msg}")


# ------------------------------------------------------------------
# YouTube URL detection helper
# ------------------------------------------------------------------

_YT_URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/",
    re.IGNORECASE,
)


def is_youtube_url(s: str) -> bool:
    """Return True if *s* looks like a YouTube URL."""
    return bool(_YT_URL_RE.search(s))


# ------------------------------------------------------------------
# Step 0 (YouTube path): Download video + fetch transcript from YT
# ------------------------------------------------------------------

def get_youtube_inputs(url: str) -> tuple[str, str, list]:
    """
    Download a YouTube video and fetch its transcript.

    Returns:
        (local_video_path, transcript_text, timed_segments)

        timed_segments is a list of {"text", "start", "duration"} dicts
        from youtube-transcript-api.  Passed to SubtitlesNode so it can burn
        subtitles without re-running Whisper.
    """
    from tools.youtube.transcript import extract_video_id, fetch_transcript, fetch_timed_segments
    from tools.youtube.downloader import download_video

    section("STEP 0 — YouTube: downloading video and fetching transcript")
    info(f"URL: {url}")

    # Parse video ID
    video_id = extract_video_id(url)
    ok(f"Video ID : {video_id}")

    # Download destination
    downloads_dir = Path("output") / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(downloads_dir / f"{video_id}.mp4")

    if Path(video_path).exists():
        warn(f"Video already cached at {video_path}; skipping download.")
    else:
        info(f"Downloading to {video_path} …")
        download_video(url, video_path)
        ok(f"Downloaded → {video_path}")

    # Fetch timed segments (keeps start/duration for subtitle alignment)
    info("Fetching YouTube transcript (timed segments) …")
    timed_segments: list = []
    transcript = ""
    try:
        timed_segments = fetch_timed_segments(url)
        transcript = " ".join(
            seg["text"].strip() for seg in timed_segments if seg.get("text")
        )
        ok(f"Transcript fetched via YouTube captions  ({len(transcript)} chars, "
           f"{len(timed_segments)} timed segments)")
        info(f"Preview: {transcript[:200]}…")
    except RuntimeError as yt_exc:
        warn(f"YouTube transcript unavailable: {yt_exc}")
        warn("Falling back to Whisper auto-transcription …")
        transcript = _whisper_transcribe(video_path)
        timed_segments = []  # no timed data available from Whisper path here

    # Save transcript to disk for debugging / inspection
    _save_transcript(transcript, video_id)

    return video_path, transcript, timed_segments


def _save_transcript(transcript: str, name: str) -> None:
    """Write *transcript* to output/transcripts/<name>.txt for inspection."""
    transcripts_dir = Path("output") / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{name}.txt"
    out_path.write_text(transcript, encoding="utf-8")
    ok(f"Transcript saved → {out_path}")


# ------------------------------------------------------------------
# Step 1: Probe the video
# ------------------------------------------------------------------

def probe_video(video_path: str) -> dict:
    """Return ffmpeg probe dict; raise if file is unreadable."""
    import ffmpeg
    section("STEP 1 — Probing video")
    print(f"  Path : {video_path}")
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    probe = ffmpeg.probe(video_path)
    fmt   = probe["format"]
    duration = float(fmt.get("duration", 0))
    size_mb  = int(fmt.get("size", 0)) / (1024 * 1024)

    _MIN_DURATION_SECONDS = 30
    if duration < _MIN_DURATION_SECONDS:
        raise ValueError(
            f"Video must be at least {_MIN_DURATION_SECONDS} seconds long; "
            f"got {duration:.1f}s. Path: {video_path}"
        )

    ok(f"Duration  : {duration:.1f}s  ({duration / 60:.1f} min)")
    ok(f"File size : {size_mb:.1f} MB")
    ok(f"Format    : {fmt.get('format_name', '?')}")

    for s in probe["streams"]:
        codec_type = s.get("codec_type", "?")
        codec_name = s.get("codec_name", "?")
        if codec_type == "video":
            w, h   = s.get("width", "?"), s.get("height", "?")
            fps    = s.get("r_frame_rate", "?/1")
            try:
                num, den = fps.split("/")
                fps_val = f"{int(num)//int(den)} fps"
            except Exception:
                fps_val = fps
            ok(f"Video     : {codec_name}  {w}x{h}  {fps_val}")
        elif codec_type == "audio":
            sr = s.get("sample_rate", "?")
            ok(f"Audio     : {codec_name}  {sr} Hz")

    return probe


# ------------------------------------------------------------------
# Shared Whisper helper (used by both paths as a fallback)
# ------------------------------------------------------------------

def _whisper_transcribe(video_path: str, max_minutes: int = 10) -> str:
    """
    Auto-transcribe *video_path* using Whisper (base model).
    Extracts the first *max_minutes* of audio, runs Whisper, and returns
    the transcript string.
    """
    import ffmpeg as _ffmpeg
    import tempfile

    warn(f"Auto-transcribing first {max_minutes} min of audio with Whisper …")
    warn("This may take 30–120 seconds depending on hardware.")

    tmp_audio = tempfile.mktemp(suffix=".wav")
    info(f"Extracting audio → {tmp_audio}")
    (
        _ffmpeg
        .input(video_path, ss=0, t=max_minutes * 60)
        .output(tmp_audio, ac=1, ar=16000, format="wav")
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )
    ok(f"Audio extracted ({max_minutes} min segment)")

    import whisper
    info("Loading Whisper base model …")
    model = whisper.load_model("base")
    info("Transcribing …")
    t0 = time.time()
    result = model.transcribe(tmp_audio)
    elapsed = time.time() - t0
    text = result.get("text", "").strip()

    ok(f"Whisper done in {elapsed:.1f}s  ({len(text)} chars)")
    info(f"Preview: {text[:200]}…")

    try:
        os.remove(tmp_audio)
    except OSError:
        pass

    return text


# ------------------------------------------------------------------
# Step 2: Get transcript
# ------------------------------------------------------------------

def get_transcript(transcript_arg: str | None, video_path: str, max_minutes: int = 10) -> str:
    """
    Return a transcript string.
    Priority:
      1. transcript_arg is a .txt path → read file
      2. transcript_arg is non-empty text → use directly
      3. transcript_arg is None → auto-transcribe with Whisper
    """
    section("STEP 2 — Getting transcript")

    if transcript_arg:
        p = Path(transcript_arg)
        if p.exists() and p.suffix == ".txt":
            text = p.read_text(encoding="utf-8")
            ok(f"Loaded transcript from {p.name}  ({len(text)} chars)")
            return text
        else:
            ok(f"Using provided transcript text  ({len(transcript_arg)} chars)")
            return transcript_arg

    text = _whisper_transcribe(video_path, max_minutes)
    _save_transcript(text, Path(video_path).stem)
    return text


# ------------------------------------------------------------------
# Step 3: Run the LangGraph pipeline
# ------------------------------------------------------------------

def run_pipeline(
    video_path: str,
    transcript: str,
    top_n: int,
    add_subtitles: bool = False,
    add_top_text: bool = False,
    add_intro: bool = True,
    clip_mode: str = "portrait",
    subtitle_position: str = "bottom",
    subtitle_size: str = "medium",
    timed_transcript: list | None = None,
) -> dict:
    from agents.long_to_shorts import long_to_shorts_app

    section("STEP 3 — Running LangGraph Long-to-Shorts pipeline")
    info(f"Source video : {video_path}")
    info(f"Transcript   : {len(transcript)} chars")
    info(f"Top-N clips  : {top_n}")
    info(f"Clip mode    : {clip_mode}")
    info(f"Options      : intro={'ON' if add_intro else 'OFF'}  "
         f"top-text={'ON' if add_top_text else 'OFF'}  "
         f"subtitles={'ON' if add_subtitles else 'OFF'}")
    if add_subtitles:
        info(f"Subtitle sty : position={subtitle_position}  size={subtitle_size}")
    if timed_transcript:
        info(f"Timed segs   : {len(timed_transcript)} (subtitles will skip Whisper)")
    print()

    # Apply feature flags to environment so each node can read them
    os.environ["ADD_INTRO"]      = "1" if add_intro      else "0"
    os.environ["ADD_TOP_TEXT"]   = "1" if add_top_text   else "0"
    os.environ["ADD_SUBTITLES"]  = "1" if add_subtitles  else "0"
    os.environ["SUBTITLES_POSITION"] = subtitle_position
    os.environ["SUBTITLES_SIZE"]     = subtitle_size

    initial_state = {
        "source_video_path": str(Path(video_path).resolve()),
        "transcript":        transcript,
        "top_n_clips":       top_n,
        "add_top_text":      add_top_text,
        "add_subtitles":     add_subtitles,
        "subtitle_position": subtitle_position,
        "subtitle_size":     subtitle_size,
        "add_intro":         add_intro,
        "clip_mode":         clip_mode,
        "timed_transcript":  timed_transcript or [],
        "analyzed_segments": [],
        "generated_clips":   [],
        "current_step":      "initialized",
        "error":             None,
    }

    t0 = time.time()
    print("  [3a] AnalyzeVideoNode running …")
    final_state = long_to_shorts_app.invoke(initial_state)
    elapsed = time.time() - t0

    ok(f"Pipeline completed in {elapsed:.1f}s")
    ok(f"Final step   : {final_state.get('current_step', '?')}")
    if final_state.get("error"):
        err(f"Pipeline error: {final_state['error']}")

    return final_state


# ------------------------------------------------------------------
# Step 4: Print results summary
# ------------------------------------------------------------------

def print_results(final_state: dict):
    section("STEP 4 — Results")

    analyzed = final_state.get("analyzed_segments", [])
    clips    = final_state.get("generated_clips", [])

    print(f"\n  Segments analysed : {len(analyzed)}")
    print(f"  Clips extracted   : {len(clips)}")

    if not clips:
        warn("No clips were generated. Check logs above for errors.")
        return

    print(f"\n{SEP2}")
    print(f"  {'ID':<10} {'Score':>5}  {'Range':>18}  {'Path'}")
    print(SEP2)
    for clip in clips:
        start, end = clip["timestamp_range"]
        rang = f"{start:.1f}s → {end:.1f}s"
        path = clip.get("path") or "NOT EXTRACTED"
        print(f"  {clip['clip_id']:<10} {clip['hook_score']:>5.1f}  {rang:>18}  {path}")
    print(SEP2)

    print()
    for clip in clips:
        print(f"  {clip['clip_id']}")
        title     = clip.get("title")     or "(no title)"
        summary   = clip.get("summary")   or "(no summary)"
        hook_text = clip.get("hook_text") or "(none)"
        hashtags  = clip.get("hashtags")  or []
        print(f"    Title    : {title}")
        print(f"    Summary  : {summary}")
        print(f"    Hook     : {hook_text}")
        if hashtags:
            print(f"    Hashtags : {' '.join('#' + t for t in hashtags)}")
        print()

    print(SEP)
    ok(f"Clips directory: {Path('output/clips').resolve()}")
    print(SEP)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_clipping_workflow",
        description=(
            "Long-to-Shorts clip generation from a local video or a YouTube URL.\n\n"
            "YouTube mode:  run_clipping_workflow.py <URL> [TOP_N] [flags]\n"
            "Local mode:    run_clipping_workflow.py [VIDEO] [TRANSCRIPT] [TOP_N] [flags]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Positional arguments (all optional for backward compatibility)
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="YouTube URL or local video path (default: assets/ailover.mp4)",
    )
    parser.add_argument(
        "second",
        nargs="?",
        default=None,
        help=(
            "TOP_N (YouTube mode) or transcript text/path (local mode). "
            "Defaults: TOP_N=3, no transcript (auto-transcribed with Whisper)."
        ),
    )
    parser.add_argument(
        "third",
        nargs="?",
        default=None,
        help="TOP_N for local mode (default: 3)",
    )

    # Feature flags
    parser.add_argument(
        "--subtitles",
        action="store_true",
        default=False,
        help=(
            "Burn subtitles onto each clip. For YouTube URLs the already-fetched "
            "captions are used (no Whisper). For local videos Whisper is the fallback."
        ),
    )
    parser.add_argument(
        "--subtitle-position",
        choices=["top", "middle", "bottom"],
        default="bottom",
        dest="subtitle_position",
        help="Vertical placement of burned subtitles (default: bottom). Only used with --subtitles.",
    )
    parser.add_argument(
        "--subtitle-size",
        choices=["small", "medium", "large"],
        default="medium",
        dest="subtitle_size",
        help="Font size preset for burned subtitles (default: medium). Only used with --subtitles.",
    )
    parser.add_argument(
        "--top-text",
        action="store_true",
        default=False,
        dest="top_text",
        help="Overlay the LLM-generated hook text at the top of each clip",
    )
    parser.add_argument(
        "--no-intro",
        action="store_true",
        default=False,
        dest="no_intro",
        help="Skip the title-card intro that IntroAttachNode prepends",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        default=False,
        dest="fullscreen",
        help=(
            "Clip at native resolution (no 9:16 reframing). "
            "Default: portrait 9:16 (1080×1920) letterbox."
        ),
    )

    return parser


def main():
    parser = _build_arg_parser()
    args   = parser.parse_args()

    add_intro     = not args.no_intro
    add_subtitles = args.subtitles
    add_top_text  = args.top_text
    clip_mode     = "fullscreen" if args.fullscreen else "portrait"
    subtitle_position = args.subtitle_position
    subtitle_size     = args.subtitle_size

    first_arg = args.source

    if first_arg and is_youtube_url(first_arg):
        # ------------------------------------------------------------------
        # YouTube URL mode
        # second positional = TOP_N (if present)
        # ------------------------------------------------------------------
        yt_url = first_arg
        try:
            top_n = int(args.second) if args.second is not None else 3
        except ValueError:
            top_n = 3

        print(SEP)
        print("  LONG-TO-SHORTS CLIP GENERATION WORKFLOW  [YouTube URL mode]")
        print(f"  URL       : {yt_url}")
        print(f"  Top-N     : {top_n}")
        print(f"  Clip mode : {clip_mode}")
        print(f"  Intro     : {'ON' if add_intro else 'OFF'}")
        print(f"  Top-text  : {'ON' if add_top_text else 'OFF'}")
        print(f"  Subtitles : {'ON' if add_subtitles else 'OFF'}"
              + (f"  (pos={subtitle_position}, size={subtitle_size})" if add_subtitles else ""))
        print(SEP)

        try:
            video_path, transcript, timed_segments = get_youtube_inputs(yt_url)
            probe_video(video_path)

            section("STEP 2 — Transcript")
            ok(f"Using YouTube transcript  ({len(transcript)} chars)")

            final_state = run_pipeline(
                video_path, transcript, top_n,
                add_subtitles=add_subtitles,
                add_top_text=add_top_text,
                add_intro=add_intro,
                clip_mode=clip_mode,
                subtitle_position=subtitle_position,
                subtitle_size=subtitle_size,
                timed_transcript=timed_segments,
            )
            print_results(final_state)

        except FileNotFoundError as exc:
            err(str(exc)); sys.exit(1)
        except (ValueError, RuntimeError) as exc:
            err(str(exc)); sys.exit(1)
        except KeyboardInterrupt:
            warn("Interrupted by user."); sys.exit(0)
        except Exception as exc:
            import traceback
            err(f"Unexpected error: {exc}")
            traceback.print_exc()
            sys.exit(1)

    else:
        # ------------------------------------------------------------------
        # Local video mode
        # positional layout: source=VIDEO, second=TRANSCRIPT, third=TOP_N
        # ------------------------------------------------------------------
        video_path     = first_arg or "assets/ailover.mp4"
        transcript_arg = args.second if args.second is not None else None
        try:
            top_n = int(args.third) if args.third is not None else 3
        except ValueError:
            top_n = 3

        print(SEP)
        print("  LONG-TO-SHORTS CLIP GENERATION WORKFLOW  [local video mode]")
        print(f"  Video     : {video_path}")
        print(f"  Top-N     : {top_n}")
        print(f"  Clip mode : {clip_mode}")
        print(f"  Intro     : {'ON' if add_intro else 'OFF'}")
        print(f"  Top-text  : {'ON' if add_top_text else 'OFF'}")
        print(f"  Subtitles : {'ON' if add_subtitles else 'OFF'}"
              + (f"  (pos={subtitle_position}, size={subtitle_size})" if add_subtitles else ""))
        print(SEP)

        try:
            probe_video(video_path)
            transcript = get_transcript(transcript_arg, video_path)

            final_state = run_pipeline(
                video_path, transcript, top_n,
                add_subtitles=add_subtitles,
                add_top_text=add_top_text,
                add_intro=add_intro,
                clip_mode=clip_mode,
                subtitle_position=subtitle_position,
                subtitle_size=subtitle_size,
                timed_transcript=None,  # local path: no timed captions
            )
            print_results(final_state)

        except FileNotFoundError as exc:
            err(str(exc)); sys.exit(1)
        except ValueError as exc:
            err(str(exc)); sys.exit(1)
        except KeyboardInterrupt:
            warn("Interrupted by user."); sys.exit(0)
        except Exception as exc:
            import traceback
            err(f"Unexpected error: {exc}")
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
