"""
agents/publishing/scoring_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 3 — Automatic clip scoring. Replaces the human "pick a clip" step with a
structured, mostly-deterministic score per clip, then keeps the top-K into the
(expensive, LLM-backed) evaluation stage. Doing the cheap cull first keeps the
Eval Agent — and the Ollama GPU — off clips that were never going to win.

Deterministic by design (no LLM here): fast, reproducible, and it means scoring
never queues inference behind the human-blocking eval work.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

from agents.publishing._logging_utils import node_stage
from agents.publishing.schemas import ScoreCard
from agents.publishing.state import PublishingClipState

logger = logging.getLogger(__name__)

# Factor weights (sum need not be 1; we normalise). Hook + watch-completeness
# dominate; visual_change is a neutral placeholder until scene data is wired.
_WEIGHTS = {
    "hook": 3.0,
    "length_fit": 2.0,
    "completeness": 2.0,
    "title_quality": 1.5,
    "caption_quality": 1.0,
    "clarity": 1.5,
    "visual_change": 0.5,
}

_IDEAL_MIN_S = 15.0
_IDEAL_MAX_S = 60.0
_SENTENCE_END = re.compile(r"[.!?…\"')\]]\s*$")


def _keep_count() -> int:
    return max(1, int(os.getenv("PUBLISH_SCORE_KEEP", "3")))


def _duration(clip: Dict[str, Any]) -> float:
    tr = clip.get("timestamp_range") or [0.0, 0.0]
    try:
        return max(0.0, float(tr[1]) - float(tr[0]))
    except Exception:  # noqa: BLE001
        return 0.0


def _length_fit(duration: float) -> float:
    if duration <= 0:
        return 3.0
    if _IDEAL_MIN_S <= duration <= _IDEAL_MAX_S:
        return 10.0
    if duration < _IDEAL_MIN_S:
        return max(2.0, 10.0 - (_IDEAL_MIN_S - duration) * 0.5)
    # too long — Shorts hard-cap is ~60s; penalise steeply past 90s
    over = duration - _IDEAL_MAX_S
    return max(1.0, 10.0 - over * 0.15)


def _title_quality(title: str) -> float:
    t = (title or "").strip()
    if not t or t.lower().startswith("clip "):
        return 2.0
    n = len(t)
    if n > 70:
        return 5.0
    if n < 12:
        return 6.0
    return 9.0


def _caption_quality(clip: Dict[str, Any]) -> float:
    tags = clip.get("hashtags") or []
    summary = (clip.get("summary") or "").strip()
    score = 4.0
    score += min(4.0, len(tags))          # up to 5 tags → +4
    if summary:
        score += 2.0
    return min(10.0, score)


def _completeness(clip: Dict[str, Any]) -> float:
    summary = (clip.get("summary") or "").strip()
    hook = (clip.get("hook_text") or "").strip()
    score = 5.0
    if summary and _SENTENCE_END.search(summary):
        score += 3.0
    if hook:
        score += 2.0
    return min(10.0, score)


def _clarity(clip: Dict[str, Any], transcript: str) -> float:
    """Words-per-second sanity from any transcript excerpt we can find; neutral
    when we can't measure it (degrade-not-fail)."""
    if not transcript:
        return 6.0
    duration = _duration(clip)
    if duration <= 0:
        return 6.0
    wps = len(transcript.split()) / duration
    # Comfortable narration is ~2-3.5 wps; punish extremes (silence / word-salad).
    if 1.5 <= wps <= 3.5:
        return 9.0
    if wps < 1.0 or wps > 5.0:
        return 4.0
    return 7.0


def _hook(clip: Dict[str, Any]) -> float:
    try:
        return max(0.0, min(10.0, float(clip.get("hook_score", 5.0))))
    except Exception:  # noqa: BLE001
        return 5.0


def _score_clip(clip: Dict[str, Any], transcript: str) -> ScoreCard:
    duration = _duration(clip)
    factors = {
        "hook": _hook(clip),
        "length_fit": _length_fit(duration),
        "completeness": _completeness(clip),
        "title_quality": _title_quality(clip.get("title", "")),
        "caption_quality": _caption_quality(clip),
        "clarity": _clarity(clip, transcript),
        "visual_change": 5.0,
    }
    total_w = sum(_WEIGHTS.values())
    weighted = sum(factors[k] * _WEIGHTS[k] for k in _WEIGHTS)
    overall = round((weighted / total_w) * 10.0, 1)  # 0-10 → 0-100
    return ScoreCard(
        clip_id=str(clip.get("clip_id", "")),
        overall=overall,
        factors={k: round(v, 1) for k, v in factors.items()},
        reasoning=(
            f"hook={factors['hook']:.0f}/10, len={duration:.0f}s, "
            f"caption={factors['caption_quality']:.0f}/10"
        ),
    )


def scoring_node(state: PublishingClipState) -> Dict[str, Any]:
    with node_stage(state, "scoring"):
        return _scoring_impl(state)


def _scoring_impl(state: PublishingClipState) -> Dict[str, Any]:
    clips: List[Dict[str, Any]] = state.get("clips") or []
    if not clips:
        return {"scored_clips": [], "shortlist_ids": [], "current_step": "scoring_empty"}

    transcript = state.get("transcript") or ""
    cards = [_score_clip(c, transcript) for c in clips]
    cards.sort(key=lambda c: c.overall, reverse=True)

    keep = _keep_count()
    shortlist_ids = [c.clip_id for c in cards[:keep]]
    kept = set(shortlist_ids)
    for c in cards:
        c.kept = c.clip_id in kept

    logger.info(
        "[publish:%s] scored %d clips → shortlist %s",
        state.get("job_id", "?"), len(cards), shortlist_ids,
    )
    return {
        "scored_clips": [c.model_dump() for c in cards],
        "shortlist_ids": shortlist_ids,
        "current_step": "scored",
    }


__all__ = ["scoring_node"]
