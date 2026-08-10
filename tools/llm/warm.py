"""
tools/llm/warm.py
~~~~~~~~~~~~~~~~~~
Ollama binding for the single-GPU model manager (Phase 2). Provides the concrete
warm/evict calls (via Ollama's ``keep_alive`` on ``/api/generate``) and a
process-wide :class:`~core.inference.gpu.GpuModelManager` configured with them.

Layering: ``tools → core`` (allowed). ``core/inference/gpu.py`` stays generic;
this module supplies the Ollama-specific adapter and the singleton the inference
client + app lifespan use.

Enabled only when ``INFERENCE_WARM_ENABLED`` is truthy AND the active provider is
Ollama — otherwise every call here is a cheap no-op, so it is always safe to
wire in.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from typing import Optional

from core.inference.gpu import GpuModelManager

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    if os.getenv("INFERENCE_WARM_ENABLED", "false").lower() in ("0", "false", "no", ""):
        return False
    return os.getenv("LLM_PROVIDER", "claude").lower() == "ollama"


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _post_generate(model: str, keep_alive) -> None:
    """Hit Ollama /api/generate with an empty prompt to load (keep_alive>0) or
    unload (keep_alive=0) *model*. Short timeout; failures are swallowed by the
    caller (warm/evict are best-effort)."""
    payload = json.dumps({"model": model, "prompt": "", "keep_alive": keep_alive}).encode()
    req = urllib.request.Request(
        f"{_base_url()}/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # model load can be slow
        resp.read()


def _warm(model: str) -> None:
    _post_generate(model, os.getenv("INFERENCE_WARM_KEEPALIVE", "10m"))


def _evict(model: str) -> None:
    _post_generate(model, 0)


_manager: Optional[GpuModelManager] = None
_manager_lock = threading.Lock()


def get_gpu_manager() -> Optional[GpuModelManager]:
    """Return the configured manager, or None when warming is disabled/not Ollama."""
    global _manager
    if not _enabled():
        return None
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = GpuModelManager(
                    warm_fn=_warm,
                    evict_fn=_evict,
                    idle_timeout_s=float(os.getenv("INFERENCE_IDLE_TIMEOUT_S", "300")),
                )
    return _manager


def start_warm_pool() -> None:
    """Start idle eviction and preload the medium (eval) tier. No-op if disabled."""
    mgr = get_gpu_manager()
    if mgr is None:
        return
    mgr.start()
    medium = os.getenv("INFERENCE_MODEL_MEDIUM") or os.getenv("OLLAMA_MODEL")
    if medium:
        # Warm off-thread so startup isn't blocked on a cold model load.
        threading.Thread(target=mgr.warm, args=(medium,), name="gpu-warm", daemon=True).start()


def stop_warm_pool() -> None:
    mgr = get_gpu_manager()
    if mgr is not None:
        mgr.stop()


__all__ = ["get_gpu_manager", "start_warm_pool", "stop_warm_pool"]
