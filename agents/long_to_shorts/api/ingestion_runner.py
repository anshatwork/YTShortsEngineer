"""
agents/long_to_shorts/api/ingestion_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Background-thread orchestrator for the KG ingestion sub-graph — the analogue of
runner.py for clip jobs. Enqueued on the task queue via
``task_queue.enqueue(run_ingestion, ingestion_job_id, asset_id, user_id)``.

Resolves the asset's source (downloading a YouTube URL if needed, reusing the
same cached helpers as the clip pipeline), invokes ``ingestion_app``, then writes
status/stats back to the ingestion job store and flips the asset to 'ingested'.
Idempotent (content-hash keys + CAS) and degrade-not-fail. Credits for a metered
ingest are refunded on failure.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_URL_PREFIXES = ("http://", "https://", "www.", "youtu")


def _looks_like_url(uri: str) -> bool:
    return uri.lower().startswith(_URL_PREFIXES)


def _refund_ingest_credits(ingestion_job_id: str, user_id: str | None) -> None:
    from agents.long_to_shorts.api.credits import refund_for_op
    refund_for_op(user_id, "ingest", key=f"refund:ingest:{ingestion_job_id}")


def run_ingestion(ingestion_job_id: str, asset_id: str, user_id: str | None = None) -> None:
    """Execute the ingestion pipeline for *asset_id* and persist results."""
    from core.logging_config import job_log_context

    with job_log_context(ingestion_job_id):
        _run_ingestion_impl(ingestion_job_id, asset_id, user_id)


def _run_ingestion_impl(ingestion_job_id: str, asset_id: str, user_id: str | None) -> None:
    from agents.ingestion import ingestion_app
    from agents.long_to_shorts.api.asset_store import asset_store
    from agents.long_to_shorts.api.ingestion_job_store import ingestion_job_store

    ingestion_job_store.update(ingestion_job_id, status="running")

    asset = asset_store.get(asset_id)
    if asset is None:
        ingestion_job_store.update(ingestion_job_id, status="failed", error="asset not found")
        _refund_ingest_credits(ingestion_job_id, user_id)
        return

    try:
        asset_store.set_status(asset_id, status="ingesting")

        transcript = None
        timed_segments: list = []
        if _looks_like_url(asset.uri):
            from run_clipping_workflow import get_youtube_inputs

            source_path, transcript, timed_segments = get_youtube_inputs(asset.uri)
        else:
            source_path = asset.uri
            if not Path(source_path).exists():
                raise FileNotFoundError(f"asset source not found: {source_path}")

        initial_state = {
            "job_id": ingestion_job_id,
            "asset_id": asset_id,
            "owner_id": user_id,
            "source_path": str(Path(source_path).resolve()),
            "media_type": asset.media_type,
            "uri": asset.uri,
            "title": asset.title,
            "filename": asset.filename,
            "transcript": transcript,
            "timed_transcript": timed_segments,
            "current_node": "initialized",
        }

        # Bind the caller's BYOK LLM credential for entity extraction (same as clips).
        from tools.llm.credentials import llm_credential_context
        from agents.long_to_shorts.api.runner import _resolve_byok_credential

        cred = _resolve_byok_credential(user_id, ingestion_job_id)
        logger.info("[ingest:%s] invoking ingestion pipeline …", ingestion_job_id)
        with llm_credential_context(cred):
            final_state = ingestion_app.invoke(initial_state)

        if final_state.get("error"):
            raise RuntimeError(f"Ingestion error: {final_state['error']}")

        stats = final_state.get("stats") or {}
        content_hash = final_state.get("content_hash")
        asset_store.set_status(asset_id, status="ingested", content_hash=content_hash)
        ingestion_job_store.update(
            ingestion_job_id, status="done", current_node="done", stats=stats
        )
        logger.info("[ingest:%s] done — stats=%s", ingestion_job_id, stats)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[ingest:%s] failed: %s", ingestion_job_id, exc)
        asset_store.set_status(asset_id, status="failed")
        ingestion_job_store.update(ingestion_job_id, status="failed", error=str(exc))
        _refund_ingest_credits(ingestion_job_id, user_id)


__all__ = ["run_ingestion"]
