"""
core.execution
~~~~~~~~~~~~~~~
Execution-layer abstractions that decouple the pipeline from the concrete
in-process runtime so it can scale to distributed workers without rewrites:

  * eventbus   — pub/sub for real-time progress (in-process now, Redis later)
  * taskqueue  — background job submission (ThreadPool now, Celery/Temporal later)
  * lifecycle  — the job/stage state machine (allowed transitions in one place)

Each module exposes an interface plus a default implementation selected by env,
so production backends are config-only swaps.
"""

from core.execution.eventbus import Event, EventBus, get_event_bus
from core.execution.taskqueue import TaskQueue, get_task_queue
from core.execution import lifecycle

__all__ = [
    "Event",
    "EventBus",
    "get_event_bus",
    "TaskQueue",
    "get_task_queue",
    "lifecycle",
]
