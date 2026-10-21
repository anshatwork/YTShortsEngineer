"""
agents/publishing/revise_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The revision step of the generator→eval→revise loop. When the Eval Agent fails
the selected clip and the revision budget isn't spent, this node regenerates the
**text metadata** the eval flagged (title / description / hook text / hashtags)
using the eval's structured ``recommendations`` as the brief, then hands control
back to the Eval Agent for re-scoring.

Scope (Phase 1): text metadata only — the artifact most eval feedback targets.
Regenerating the thumbnail *frame* is a video op deferred to a later phase; the
recommendation is preserved in the eval report so the human still sees it.

Loop safety: ``revision_count`` is incremented **even if regeneration fails**, so
the loop is always bounded (never infinite).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agents.publishing._logging_utils import node_stage
from agents.publishing.state import PublishingClipState
from core.inference import Priority

logger = logging.getLogger(__name__)

_REVISE_CACHE_VERSION = 1
_TITLE_MAX = 50
_HOOK_MAX = 55

_REVISE_SYSTEM = """\
You are a short-form video metadata editor. You are given a clip's current
metadata and a list of specific reviewer recommendations. Rewrite ONLY the
metadata to address the recommendations while staying faithful to the clip's
actual content. Rules:
- title: ≤50 characters, punchy, curiosity-driven, no emojis, no all-caps.
- summary: one strong sentence for the description.
- hook_text: ≤55 characters, a bold on-screen opener distinct from the title.
- hashtags: exactly 5, lowercase, no '#', no spaces within a tag.
Return ONLY the structured object."""

_REVISE_USER = """\
Current metadata:
- title: {title}
- summary: {summary}
- hook_text: {hook_text}
- hashtags: {hashtags}

Reviewer weaknesses:
{weaknesses}

Reviewer recommendations (address these):
{recommendations}"""


class RevisedMetadata(BaseModel):
    title: str
    summary: str
    hook_text: str
    hashtags: List[str]


def _bullets(items: List[str]) -> str:
    return "\n".join(f"- {x}" for x in items) or "- (none)"


def _find(clips: List[Dict[str, Any]], clip_id: Optional[str]) -> Optional[Dict[str, Any]]:
    for c in clips:
        if c.get("clip_id") == clip_id:
            return c
    return None


def revise_node(state: PublishingClipState) -> Dict[str, Any]:
    with node_stage(state, "revise"):
        return _revise_impl(state)


def _revise_impl(state: PublishingClipState) -> Dict[str, Any]:
    clips: List[Dict[str, Any]] = list(state.get("clips") or [])
    count = int(state.get("revision_count", 0)) + 1  # bound the loop no matter what
    selected_id = state.get("selected_clip_id")
    selected_eval = state.get("selected_eval") or {}
    clip = _find(clips, selected_id)

    if clip is None:
        logger.warning("[publish:%s] revise: selected clip %s not found", state.get("job_id", "?"), selected_id)
        return {"revision_count": count, "current_step": "revise_skipped"}

    recs = selected_eval.get("recommendations") or []
    weaknesses = selected_eval.get("weaknesses") or []
    payload = _REVISE_USER.format(
        title=clip.get("title") or "(none)",
        summary=clip.get("summary") or "(none)",
        hook_text=clip.get("hook_text") or "(none)",
        hashtags=", ".join(clip.get("hashtags") or []) or "(none)",
        weaknesses=_bullets(weaknesses),
        recommendations=_bullets(recs),
    )

    try:
        from tools.llm.inference import get_inference_client

        revised: RevisedMetadata = get_inference_client().parse(
            payload, RevisedMetadata, system=_REVISE_SYSTEM,
            task_class="revise", priority=Priority.CRITICAL,
            cache_op="publish_revise", cache_version=_REVISE_CACHE_VERSION,
            group=state.get("job_id"),
        )
        # Apply, enforcing hard length caps as a safety net.
        clip["title"] = (revised.title or clip.get("title") or "").strip()[:_TITLE_MAX]
        clip["summary"] = (revised.summary or clip.get("summary") or "").strip()
        clip["hook_text"] = (revised.hook_text or clip.get("hook_text") or "").strip()[:_HOOK_MAX]
        if revised.hashtags:
            clip["hashtags"] = [h.lstrip("#").strip() for h in revised.hashtags][:5]
        logger.info("[publish:%s] revised metadata for %s (attempt %d)",
                    state.get("job_id", "?"), selected_id, count)
        step = "revised"
    except Exception as exc:  # noqa: BLE001 — degrade: keep old metadata, still count
        logger.warning("[publish:%s] revise LLM failed for %s (%s); keeping metadata",
                       state.get("job_id", "?"), selected_id, exc)
        step = "revise_failed"

    return {"clips": clips, "revision_count": count, "current_step": step}


__all__ = ["revise_node"]
