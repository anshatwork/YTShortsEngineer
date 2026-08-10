"""
agents/publishing/eval_agent_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 4 — the Eval Agent. Its ONLY job is evaluation; it never generates
content. For each shortlisted clip it asks the LLM (medium tier, CRITICAL
priority — the human is blocked on this) for a strict structured verdict across
the rubric dimensions, then:

  * derives ``passed`` purely from the numbers (overall ≥ threshold AND no
    dimension below the hard-fail floor) — never from prose;
  * selects the single best clip by ``overall_score``.

Degrade-not-fail: if the LLM errors, synthesise a neutral verdict from the clip's
existing hook score so the workflow always advances (the human still gates the
upload).

All calls route through the inference scheduler and are cached (``publish_eval``)
so an unchanged clip is never re-evaluated across revision loops.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agents.publishing._logging_utils import node_stage
from agents.publishing.schemas import (
    EVAL_DIMENSIONS,
    DimensionScore,
    EvalReport,
    EvalVerdict,
)
from agents.publishing.state import PublishingClipState
from core.inference import Priority

logger = logging.getLogger(__name__)

# Bump when the rubric / prompt meaning changes (invalidates cached verdicts).
_EVAL_CACHE_VERSION = 1

_EVAL_SYSTEM = """\
You are a ruthless short-form video quality evaluator. You NEVER rewrite or
generate content — you only score what you are given and explain why.

Score the clip on each of these dimensions from 0 to 10 (10 = excellent):
{dimensions}

Then give an overall_score from 0 to 100 (holistic publish-readiness), plus:
- strengths: what already works (concrete, 2-4 bullets)
- weaknesses: what holds it back (concrete, 2-4 bullets)
- recommendations: SPECIFIC, actionable fixes each targeting ONE artifact — a
  title, description, hashtags, or thumbnail_frame. Phrase so a generator could
  act on it directly. Do not suggest re-shooting or re-clipping.

Be strict and consistent. Return ONLY the structured object; no prose outside it."""

_EVAL_SYSTEM_FILLED = _EVAL_SYSTEM.format(
    dimensions="\n".join(f"- {d}" for d in EVAL_DIMENSIONS)
)

_EVAL_USER = """\
Clip metadata to evaluate:
- title: {title}
- description: {summary}
- on-screen hook text: {hook_text}
- hashtags: {hashtags}
- duration_seconds: {duration:.0f}
- prior hook score (0-10): {hook_score}
- background music theme: {music_theme}

Transcript excerpt (may be partial):
\"\"\"
{excerpt}
\"\"\""""


def _pass_threshold() -> int:
    return int(os.getenv("EVAL_PASS_THRESHOLD", "70"))


def _min_dimension() -> int:
    return int(os.getenv("EVAL_MIN_DIMENSION", "3"))


def _duration(clip: Dict[str, Any]) -> float:
    tr = clip.get("timestamp_range") or [0.0, 0.0]
    try:
        return max(0.0, float(tr[1]) - float(tr[0]))
    except Exception:  # noqa: BLE001
        return 0.0


def _excerpt(clip: Dict[str, Any], state: PublishingClipState) -> str:
    """Best-effort transcript excerpt for the clip window."""
    timed = state.get("timed_transcript")
    tr = clip.get("timestamp_range") or [0.0, 0.0]
    if timed:
        try:
            start, end = float(tr[0]), float(tr[1])
            words: List[str] = []
            for seg in timed:
                s = float(seg.get("start", 0))
                if start <= s <= end:
                    words.append(str(seg.get("text", "")))
            if words:
                return " ".join(words)[:1500]
        except Exception:  # noqa: BLE001
            pass
    return (clip.get("summary") or "")[:1500]


def _compute_passed(overall: int, dims: List[DimensionScore]) -> bool:
    if overall < _pass_threshold():
        return False
    floor = _min_dimension()
    return all(d.score >= floor for d in dims)


def _neutral_report(clip: Dict[str, Any]) -> EvalReport:
    """Fallback verdict from the existing hook score (degrade-not-fail)."""
    try:
        hook = float(clip.get("hook_score", 5.0))
    except Exception:  # noqa: BLE001
        hook = 5.0
    overall = int(max(0, min(100, round(hook * 10))))
    dims = [DimensionScore(name=d, score=int(round(hook)), reasoning="heuristic (eval LLM unavailable)")
            for d in EVAL_DIMENSIONS]
    return EvalReport(
        clip_id=str(clip.get("clip_id", "")),
        overall_score=overall,
        passed=_compute_passed(overall, dims),
        dimensions=dims,
        strengths=["Generated successfully"],
        weaknesses=["Could not run full evaluation"],
        recommendations=[],
    )


def _evaluate_clip(clip: Dict[str, Any], state: PublishingClipState) -> EvalReport:
    from tools.llm.inference import get_inference_client

    payload = _EVAL_USER.format(
        title=clip.get("title") or "(none)",
        summary=clip.get("summary") or "(none)",
        hook_text=clip.get("hook_text") or "(none)",
        hashtags=", ".join(clip.get("hashtags") or []) or "(none)",
        duration=_duration(clip),
        hook_score=clip.get("hook_score", "?"),
        music_theme=clip.get("music_theme") or "(none)",
        excerpt=_excerpt(clip, state),
    )
    try:
        verdict: EvalVerdict = get_inference_client().parse(
            payload, EvalVerdict, system=_EVAL_SYSTEM_FILLED,
            task_class="eval", priority=Priority.CRITICAL,
            cache_op="publish_eval", cache_version=_EVAL_CACHE_VERSION,
            group=state.get("job_id"),
        )
    except Exception as exc:  # noqa: BLE001 — degrade, don't fail the workflow
        logger.warning("[publish:%s] eval LLM failed for %s (%s); using neutral verdict",
                       state.get("job_id", "?"), clip.get("clip_id"), exc)
        return _neutral_report(clip)

    overall = int(max(0, min(100, verdict.overall_score)))
    dims = verdict.dimensions or []
    return EvalReport(
        clip_id=str(clip.get("clip_id", "")),
        overall_score=overall,
        passed=_compute_passed(overall, dims),
        dimensions=dims,
        strengths=verdict.strengths,
        weaknesses=verdict.weaknesses,
        recommendations=verdict.recommendations,
    )


def eval_agent_node(state: PublishingClipState) -> Dict[str, Any]:
    with node_stage(state, "eval"):
        return _eval_impl(state)


def _eval_impl(state: PublishingClipState) -> Dict[str, Any]:
    clips: List[Dict[str, Any]] = state.get("clips") or []
    shortlist = set(state.get("shortlist_ids") or [c.get("clip_id") for c in clips])
    to_eval = [c for c in clips if c.get("clip_id") in shortlist] or clips
    if not to_eval:
        return {"eval_reports": [], "selected_clip_id": None, "current_step": "eval_empty"}

    reports = [_evaluate_clip(c, state) for c in to_eval]
    best = max(reports, key=lambda r: r.overall_score)

    logger.info(
        "[publish:%s] evaluated %d clips → best=%s score=%d passed=%s",
        state.get("job_id", "?"), len(reports), best.clip_id, best.overall_score, best.passed,
    )
    return {
        "eval_reports": [r.model_dump() for r in reports],
        "selected_clip_id": best.clip_id,
        "selected_eval": best.model_dump(),
        "current_step": "evaluated",
    }


__all__ = ["eval_agent_node"]
