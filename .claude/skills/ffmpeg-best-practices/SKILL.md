---
name: ffmpeg-best-practices
description: Best practices for FFmpeg/video work in this repo — encoding params, the four invocation styles, Windows/Docker font & path gotchas, stream mapping, caching. Use when writing or reviewing any FFmpeg, MoviePy, or yt-dlp media code.
---

# FFmpeg Best Practices

Context: `docs/claude/tools.md`, `agents.md`. FFmpeg is invoked **four ways** here — don't add a
fifth: raw `subprocess` (clipping_logic, audio_mixer, subtitles), `ffmpeg-python` (top_text,
intro_attach, thumbnail, TTS transcode), MoviePy (layout_engine, editor_engine), and yt-dlp
postprocessor (download_audio).

## Encoding defaults (match the pipeline)
- Video: `libx264`, ~8000k, 60fps (`CLIP_FORCE_FPS`), 1080×1920 for portrait, preset from
  `CLIP_X264_PRESET`.
- Audio: `aac` @192k.
- **Always** on final outputs: `-pix_fmt yuv420p` and `-movflags +faststart` (browser + mobile
  playback; without them you get green/garbled or non-streaming files).

## Do
- [ ] Resolve the binary via `imageio_ffmpeg.get_ffmpeg_exe()` → PATH fallback (see
      `audio_mixer._resolve_ffmpeg_bin`). Use `ffmpeg.probe` (ffmpeg-python) for probing —
      **imageio bundles no ffprobe**.
- [ ] Copy the video stream (`-c:v copy`) when only audio changes (audio_mixer pattern). Don't
      re-encode video needlessly.
- [ ] Handle the no-audio-track case explicitly (probe first; intro_attach has a video-only branch).
- [ ] For long clips, prefer split-encode-concat (closed-GOP parts → concat demuxer copy) as
      clipping_logic does; single-pass for short clips.
- [ ] Cache expensive renders through the CAS (`materialize_blob("clip_extract", version=…)`); bump
      the version constant when the encode changes.
- [ ] Capture and log the ffmpeg stderr tail on failure.

## Windows / Docker gotchas
- [ ] Subtitle/ASS burn-in: run with `cwd=<dir>` and a **bare filename** in `-vf ass=<file>` to
      dodge `C:\`/`:` escaping (copy `subtitles_node`).
- [ ] Fonts must exist on the box: Arial on Windows (`SUBTITLES_FONT_NAME`), DejaVu in Docker.
      `caption_generator.py` hardcodes `C:\Windows\Fonts\impact.ttf` — this is portability debt;
      don't copy the hardcode into new code, add a resolver.
- [ ] Detect silent libass font failures by scanning stderr for `fontselect`/`glyph`/`no usable font`.
- [ ] Escape `drawtext` text (`\ ' : %`) — reuse `_escape_drawtext`.

## Verify
- [ ] Probe the output: it exists, is non-trivially sized (>1KB guard like subtitles_node), and has
      the expected dimensions + audio stream.
- [ ] Test on the tiny fixture `assets/ailover.mp4` (the integration path in
      `test_long_to_shorts.py`).
