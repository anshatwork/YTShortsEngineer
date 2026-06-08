"""
agents/long_to_shorts/srt_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Minimal SRT parser for user-supplied .srt files. Produces the same timed
segment dicts ({"text", "start", "duration"}) that SubtitlesNode burns via its
ASS builder (subtitles_node._build_ass).

Parses standard SubRip blocks of the form::

    1
    00:00:01,000 --> 00:00:04,500
    Hello world
    second line

into a list of timed-segment dicts compatible with
``state["timed_transcript"]`` and ``SubtitlesNode._slice_timed_segments``::

    {"text": str, "start": float, "duration": float}

Timestamps are kept in *absolute* source-video time (seconds); SubtitlesNode
re-zeros them per clip.  No third-party dependency.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

# HH:MM:SS,mmm  (comma or dot as the millisecond separator)
_TS_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})"
)
_ARROW = "-->"


def _ts_to_seconds(ts: str) -> float:
    """Convert an SRT timestamp 'HH:MM:SS,mmm' to float seconds."""
    match = _TS_RE.search(ts)
    if not match:
        raise ValueError(f"Unrecognised SRT timestamp: {ts!r}")
    h = int(match.group("h"))
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = int(match.group("ms").ljust(3, "0"))  # pad '5' -> '500'
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(path: str | Path) -> List[Dict[str, Any]]:
    """
    Parse an .srt file into a list of ``{"text", "start", "duration"}`` dicts.

    Robust to:
      • optional BOM / index lines
      • CRLF or LF line endings
      • blank lines between blocks
      • comma or dot millisecond separators

    Segments without a parsable ``-->`` time line or with empty text are skipped.
    """
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    # Split into blocks on one-or-more blank lines.
    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip())

    segments: List[Dict[str, Any]] = []
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue

        # Find the time line (the one containing '-->'); index line is optional.
        time_idx = next((i for i, ln in enumerate(lines) if _ARROW in ln), None)
        if time_idx is None:
            continue

        start_raw, _, end_raw = lines[time_idx].partition(_ARROW)
        try:
            start = _ts_to_seconds(start_raw.strip())
            end = _ts_to_seconds(end_raw.strip())
        except ValueError:
            continue

        text = " ".join(ln.strip() for ln in lines[time_idx + 1:]).strip()
        if not text:
            continue

        duration = max(0.0, end - start)
        segments.append({"text": text, "start": start, "duration": duration})

    return segments


__all__ = ["parse_srt"]
