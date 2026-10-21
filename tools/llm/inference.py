"""
tools/llm/inference.py
~~~~~~~~~~~~~~~~~~~~~~~~
The inference **client** — the single entry point graph nodes use for LLM calls.
Nothing in the pipeline should call ``get_llm()`` directly any more; everything
goes through here so that:

  * calls are **scheduled** (priority-ordered, bounded concurrency) via the
    generic ``core.inference`` scheduler — the single choke point protecting the
    local Ollama GPU;
  * identical prompts are served **cache-first** from the CAS (``core.cache``)
    and never occupy a GPU slot;
  * the right **model tier** (small/medium/large) is chosen per task class so the
    largest model never runs when a smaller one suffices;
  * a per-job **BYOK credential** is carried across to the scheduler worker
    thread (the ``current_llm_credential`` contextvar does not cross threads).

Layering: ``tools → core`` (allowed). The scheduler itself is LLM-agnostic in
``core/inference``; this module is the LLM adapter that submits closures to it.

Usage (mirrors ``get_llm().parse``)::

    from tools.llm.inference import get_inference_client
    from core.inference import Priority

    report = get_inference_client().parse(
        payload, EvalReport, system=_EVAL_SYSTEM,
        task_class="eval", priority=Priority.CRITICAL,
        cache_op="publish_eval", cache_version=1,
    )
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from core.cache import get_cache, hash_text
from core.inference import Priority, get_metrics, get_scheduler
from tools.llm.base import _extract_json

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Serialises the per-call OLLAMA_* env swap so concurrent workers (if
# max_concurrency > 1) never clobber each other's model routing. On a single-GPU
# box concurrency is 1, so this is effectively free.
_env_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------

# task_class -> tier. Anything unmapped falls back to "medium".
_TASK_TIERS = {
    "metadata": "small",
    "content": "small",
    "score": "small",
    "discovery": "small",
    "eval": "medium",
    "analysis": "medium",
    "revise": "medium",
    "plan": "large",
}

# Per-tier generation budget (num_predict) — eval/plan need more room than a
# one-line title. Applied via OLLAMA_MAX_TOKENS for the duration of the call.
_TIER_MAX_TOKENS = {"small": 512, "medium": 1024, "large": 2048}


class ModelRegistry:
    """Resolves the model + token budget for a task class.

    Model *routing* only bites when the effective provider is local Ollama
    (the intended production deployment). On Claude/BYOK the provider uses its
    own single model — routing then only informs the cache key + token budget.
    """

    def tier(self, task_class: str) -> str:
        return _TASK_TIERS.get(task_class, "medium")

    def ollama_model(self, task_class: str) -> str:
        tier = self.tier(task_class)
        env = {
            "small": os.getenv("INFERENCE_MODEL_SMALL"),
            "medium": os.getenv("INFERENCE_MODEL_MEDIUM"),
            "large": os.getenv("INFERENCE_MODEL_LARGE"),
        }[tier]
        # Fall back to whatever the plain Ollama path would use.
        return env or os.getenv("OLLAMA_MODEL") or "llama3.1:8b"

    def max_tokens(self, task_class: str) -> int:
        return _TIER_MAX_TOKENS.get(self.tier(task_class), 1024)

    def effective_model_id(self, task_class: str, cred=None) -> str:
        """The model id used in the cache key — mirrors ``_llm_cache._model_id``
        but honours per-task Ollama routing so tiers don't collide in the cache.

        *cred* is passed explicitly (captured on the caller thread) so the value
        is identical whether computed on the caller or the scheduler worker."""
        from tools.llm.credentials import local_only
        if local_only():
            # Kill-switch on: everything routes to local Ollama; the cache key must
            # reflect the Ollama tier model, not any BYOK/Claude id.
            return self.ollama_model(task_class)
        if cred is None:
            from tools.llm.credentials import current_llm_credential
            cred = current_llm_credential.get()
        if cred is not None:
            return cred.model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        provider = os.getenv("LLM_PROVIDER", "claude").lower()
        if provider == "claude":
            return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        if provider == "ollama":
            return self.ollama_model(task_class)
        if provider == "glm":
            return os.getenv("GLM_MODEL", "glm-4.5-flash")
        if provider == "openrouter":
            return os.getenv("OPENROUTER_MODEL", "openrouter/free")
        return os.getenv("LLM_MODEL_ID") or os.getenv("HF_MODEL_ID") or "default"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _cache_prompt(system: Optional[str], prompt: str, schema: Optional[type]) -> str:
    """Canonical text hashed for the cache key. Includes the schema so an
    output-shape change is a cache miss even without a version bump."""
    parts = [system or "", prompt]
    if schema is not None:
        try:
            import json

            parts.append(json.dumps(schema.model_json_schema(), sort_keys=True))
        except Exception:  # noqa: BLE001
            parts.append(getattr(schema, "__name__", "schema"))
    return "\x00".join(parts)


def _max_retries() -> int:
    return int(os.getenv("INFERENCE_MAX_RETRIES", "2"))


def _capture_credential():
    """Read the BYOK credential bound to THIS thread. Captured at submit time so
    it can be rebound inside the scheduler worker (contextvars don't cross threads)."""
    from tools.llm.credentials import current_llm_credential, local_only
    if local_only():
        return None  # kill-switch: never rebind a hosted-provider credential
    return current_llm_credential.get()


class InferenceClient:
    """Cache-first, priority-scheduled, model-routed LLM client."""

    def __init__(self) -> None:
        self._registry = ModelRegistry()
        self._metrics = get_metrics()

    # -- public API --------------------------------------------------------

    def parse(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system: Optional[str] = None,
        task_class: str = "metadata",
        priority: Priority = Priority.INTERACTIVE,
        cache_op: str,
        cache_version: int,
        group: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> T:
        """Structured output — cached as validated JSON, parsed on the way out."""
        cred = _capture_credential()  # capture on THIS thread; rebind in the worker
        raw = self._cached(
            _cache_prompt(system, prompt, schema),
            cache_op=cache_op, cache_version=cache_version, task_class=task_class,
            run=lambda: self._invoke_parse(prompt, schema, system, task_class, cred),
            priority=priority, group=group, timeout=timeout, cred=cred,
        )
        try:
            return schema.model_validate_json(raw)
        except Exception:  # noqa: BLE001 — tolerate fenced/older cached text
            return schema.model_validate_json(_extract_json(raw))

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        task_class: str = "metadata",
        priority: Priority = Priority.INTERACTIVE,
        cache_op: str,
        cache_version: int,
        group: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Free-text completion — cached raw."""
        full = f"{system}\n\n{prompt}" if system else prompt
        cred = _capture_credential()
        return self._cached(
            _cache_prompt(system, prompt, None),
            cache_op=cache_op, cache_version=cache_version, task_class=task_class,
            run=lambda: self._invoke_generate(full, task_class, cred),
            priority=priority, group=group, timeout=timeout, cred=cred,
        )

    # -- cache-first wrapper ----------------------------------------------

    def _cached(self, cache_text, *, cache_op, cache_version, task_class,
                run, priority, group, timeout, cred=None) -> str:
        model_id = self._registry.effective_model_id(task_class, cred)
        inputs = {"model": model_id, "prompt": hash_text(cache_text)}
        missed = {"v": False}

        def _compute():
            missed["v"] = True
            fut = get_scheduler().submit(run, priority=priority, group=group)
            return {"text": fut.result(timeout=timeout)}

        value = get_cache().get_or_compute_json(cache_op, cache_version, inputs, _compute)
        if missed["v"]:
            self._metrics.record_cache_miss()
        else:
            self._metrics.record_cache_hit()
        return value["text"]

    # -- the closures that run ON the scheduler worker thread --------------

    def _invoke_parse(self, prompt, schema, system, task_class, cred) -> str:
        obj = self._with_routing(
            task_class, cred, lambda llm: llm.parse(prompt, schema, system=system)
        )
        return obj.model_dump_json()

    def _invoke_generate(self, full_prompt, task_class, cred) -> str:
        return self._with_routing(task_class, cred, lambda llm: llm.generate(full_prompt))

    def _with_routing(self, task_class, cred, call):
        """Run *call(llm)* on this worker thread with the BYOK credential rebound,
        the routed Ollama model/token budget applied, retries + metrics.

        *cred* is captured on the caller's thread (parse/generate) because the
        ``current_llm_credential`` contextvar does not cross into the scheduler
        worker thread where this actually executes."""
        from tools.llm import get_llm
        from tools.llm.credentials import llm_credential_context

        model_id = self._registry.effective_model_id(task_class, cred)
        attempts = _max_retries() + 1
        last_exc: Optional[Exception] = None

        for attempt in range(attempts):
            t0 = time.perf_counter()
            try:
                with self._route_env(task_class, cred):
                    with llm_credential_context(cred):
                        result = call(get_llm())
                self._metrics.record_completion(
                    model=model_id, latency_s=time.perf_counter() - t0, ok=True
                )
                self._note_gpu_use(model_id, cred)
                return result
            except Exception as exc:  # noqa: BLE001 — retry transient, then surface
                last_exc = exc
                self._metrics.record_completion(
                    model=model_id, latency_s=time.perf_counter() - t0, ok=False
                )
                if attempt + 1 < attempts:
                    self._metrics.record_retry()
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        "inference attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt + 1, attempts, exc, backoff,
                    )
                    time.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    def _note_gpu_use(self, model_id, cred) -> None:
        """Record model residency for the single-GPU manager (Phase 2). Only the
        infra Ollama path has a manager; BYOK/Claude has none. Best-effort."""
        if cred is not None:
            return
        try:
            from tools.llm.warm import get_gpu_manager
            mgr = get_gpu_manager()
            if mgr is not None:
                mgr.note_use(model_id)
        except Exception:  # noqa: BLE001
            pass

    def _route_env(self, task_class, cred):
        """Context manager: temporarily set OLLAMA_MODEL / OLLAMA_MAX_TOKENS for the
        routed tier (infra path only — never touch env on the BYOK path)."""
        registry = self._registry

        class _Ctx:
            def __enter__(_self):
                _self._token = None
                if cred is not None:
                    return  # BYOK uses the user's provider; no local routing
                _env_lock.acquire()
                _self._saved = {
                    "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL"),
                    "OLLAMA_MAX_TOKENS": os.environ.get("OLLAMA_MAX_TOKENS"),
                }
                os.environ["OLLAMA_MODEL"] = registry.ollama_model(task_class)
                os.environ["OLLAMA_MAX_TOKENS"] = str(registry.max_tokens(task_class))
                _self._token = True

            def __exit__(_self, *exc):
                if _self._token:
                    for k, v in _self._saved.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
                    _env_lock.release()
                return False

        return _Ctx()


_client: Optional[InferenceClient] = None
_client_lock = threading.Lock()


def scheduler_enabled() -> bool:
    """Whether existing pipeline nodes route their LLM calls through the scheduler.
    Default on; a safety valve (set INFERENCE_SCHEDULER_ENABLED=0) restores the
    old direct-``get_llm()`` behaviour."""
    return os.getenv("INFERENCE_SCHEDULER_ENABLED", "1").lower() not in ("0", "false", "no", "")


def run_scheduled(fn, *, priority: Priority = Priority.INTERACTIVE, group=None, timeout=None):
    """Run *fn* (a zero-arg callable already closed over a BYOK-bound ``llm``)
    on the inference scheduler and block for its result.

    This is the low-ceremony migration path for the existing clip-pipeline nodes:
    they keep their own ``cached_llm_text`` memoization (so cache keys are
    unchanged) and only submit the real model call here for global concurrency
    control. No model-tier routing is applied — the ambient model is used, so
    behaviour and cache keys match the pre-scheduler pipeline exactly."""
    fut = get_scheduler().submit(fn, priority=priority, group=group)
    return fut.result(timeout=timeout)


def get_inference_client() -> InferenceClient:
    """Return the process-wide inference client (created on first use)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = InferenceClient()
    return _client


__all__ = [
    "InferenceClient",
    "ModelRegistry",
    "get_inference_client",
    "run_scheduled",
    "scheduler_enabled",
]
