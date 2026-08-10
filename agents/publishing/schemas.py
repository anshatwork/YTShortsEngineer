"""
agents/publishing/schemas.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Structured schemas for the Autonomous Publishing Agent — the *typed contracts*
between its stages. Kept dependency-free (pydantic only) so both the graph nodes
(``agents``) and the API models (``api``) can import them without any upward
dependency.

Design rule for the Eval Agent: **no free-form text drives control flow** — the
graph branches only on the structured fields here (``passed``, ``overall_score``,
per-dimension scores). Prose lives in ``reasoning`` / ``recommendations`` for the
human, never as a parsing target.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — Discovery
# ---------------------------------------------------------------------------

class VideoCandidate(BaseModel):
    """A candidate source video. Mirrors the fields the YouTube search tool
    returns; defined here (not imported from the API layer) to keep the graph
    free of upward dependencies."""

    video_id: str
    title: str = ""
    url: str = ""
    channel: str = ""
    description: str = ""
    thumbnail: str = ""
    published_at: str = ""
    duration_seconds: int = 0
    duration_label: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class DiscoveryRecommendation(BaseModel):
    """One ranked, *explainable* source-video recommendation shown at the first
    human gate. Every field answers "why should I approve this?"."""

    video: VideoCandidate
    rank: int = 0
    why_selected: str = Field(default="", description="Plain-language justification.")
    expected_clip_quality: str = Field(
        default="medium", description="low | medium | high — predicted clip yield."
    )
    hook_potential: int = Field(default=5, ge=0, le=10, description="Viral-hook potential (0-10).")
    topic_relevance: int = Field(default=5, ge=0, le=10, description="Fit to the request (0-10).")
    scores: Dict[str, float] = Field(
        default_factory=dict, description="Raw ranker sub-scores (keyword/engagement/…)."
    )


class DiscoveryExplanation(BaseModel):
    """LLM-inferred explanation for a single candidate (the ``parse`` target used
    by the discovery agent to enrich a ranked video)."""

    why_selected: str = ""
    expected_clip_quality: str = "medium"
    hook_potential: int = Field(default=5, ge=0, le=10)
    topic_relevance: int = Field(default=5, ge=0, le=10)


# ---------------------------------------------------------------------------
# Stage 3 — Automatic clip scoring (cull before the expensive Eval)
# ---------------------------------------------------------------------------

class ScoreCard(BaseModel):
    """A structured, mostly-deterministic score for one generated clip."""

    clip_id: str
    overall: float = Field(default=0.0, description="Weighted composite (0-100).")
    factors: Dict[str, float] = Field(
        default_factory=dict,
        description="Per-factor sub-scores: hook, coherence, clarity, completeness, "
                    "length_fit, title_quality, caption_quality, visual_change.",
    )
    kept: bool = Field(default=False, description="Advanced into evaluation?")
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Stage 4 — Evaluation (the Eval Agent's only output)
# ---------------------------------------------------------------------------

class DimensionScore(BaseModel):
    name: str
    score: int = Field(ge=0, le=10)
    reasoning: str = ""


class EvalReport(BaseModel):
    """The Eval Agent's structured verdict for one clip. Strict JSON only."""

    clip_id: Optional[str] = None
    overall_score: int = Field(default=0, ge=0, le=100)
    passed: bool = False
    dimensions: List[DimensionScore] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(
        default_factory=list,
        description="Actionable fixes targeted at a specific artifact "
                    "(title/description/hashtags/thumbnail_frame).",
    )
    # Set true when the revision budget was exhausted and we proceed best-effort;
    # surfaced to the human at the upload gate so they know quality is borderline.
    best_effort: bool = False

    def dimension(self, name: str) -> Optional[DimensionScore]:
        for d in self.dimensions:
            if d.name == name:
                return d
        return None


class EvalVerdict(BaseModel):
    """The raw ``parse`` target the Eval LLM returns (no clip_id/best_effort —
    those are stamped by the node)."""

    overall_score: int = Field(default=0, ge=0, le=100)
    dimensions: List[DimensionScore] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


# Dimensions the Eval Agent must score (the rubric). Kept here so the node, the
# prompt, and any tests share one source of truth.
EVAL_DIMENSIONS = (
    "hook", "title", "description", "hashtags", "thumbnail_frame", "music_fit",
    "opening", "ending", "watchability", "educational_value", "completeness",
    "context_preservation", "clarity", "length_fit",
)


__all__ = [
    "VideoCandidate",
    "DiscoveryRecommendation",
    "DiscoveryExplanation",
    "ScoreCard",
    "DimensionScore",
    "EvalReport",
    "EvalVerdict",
    "EVAL_DIMENSIONS",
]
