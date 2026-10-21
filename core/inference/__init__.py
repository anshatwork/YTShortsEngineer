"""
core/inference
~~~~~~~~~~~~~~~
Generic, priority-aware inference scheduler + metrics. LLM-agnostic by design so
``core`` never imports upward; the LLM-specific client lives in
``tools/llm/inference.py`` and submits closures here.

    from core.inference import get_scheduler, Priority
    fut = get_scheduler().submit(do_work, priority=Priority.CRITICAL)
    result = fut.result()
"""

from core.inference.metrics import Metrics, get_metrics
from core.inference.scheduler import (
    InferenceCancelled,
    InferenceScheduler,
    Priority,
    get_scheduler,
)

__all__ = [
    "get_scheduler",
    "InferenceScheduler",
    "Priority",
    "InferenceCancelled",
    "get_metrics",
    "Metrics",
]
