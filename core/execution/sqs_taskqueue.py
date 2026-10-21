"""Durable SQS task queue for hosted worker deployments."""

from __future__ import annotations

import importlib
import json
import os
from typing import Any, Callable

from core.execution.taskqueue import TaskQueue


def _type_name(value: type) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _encode(value: Any) -> Any:
    if hasattr(value, "model_dump") and hasattr(value.__class__, "model_validate"):
        return {"__pydantic__": _type_name(value.__class__), "data": value.model_dump(mode="json")}
    if isinstance(value, tuple):
        return {"__tuple__": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    return value


def _resolve(name: str) -> Any:
    module_name, qualname = name.split(":", 1)
    value: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "__tuple__" in value:
        return tuple(_decode(item) for item in value["__tuple__"])
    if "__pydantic__" in value:
        return _resolve(value["__pydantic__"]).model_validate(value["data"])
    return {key: _decode(item) for key, item in value.items()}


def encode_task(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if "<locals>" in getattr(func, "__qualname__", ""):
        raise TypeError("SQS tasks must use a top-level callable")
    return json.dumps({
        "callable": f"{func.__module__}:{func.__qualname__}",
        "args": _encode(args),
        "kwargs": _encode(kwargs),
    }, separators=(",", ":"))


def decode_task(body: str) -> tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]:
    payload = json.loads(body)
    func = _resolve(payload["callable"])
    return func, tuple(_decode(payload.get("args", []))), _decode(payload.get("kwargs", {}))


class SqsTaskQueue(TaskQueue):
    def __init__(self, queue_url: str | None = None) -> None:
        import boto3

        self.queue_url = queue_url or os.environ["TASK_QUEUE_URL"]
        self._client = boto3.client("sqs", region_name=os.getenv("AWS_REGION"))

    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        body = encode_task(func, args, kwargs)
        max_bytes = int(os.getenv("TASK_QUEUE_MAX_MESSAGE_BYTES", "250000"))
        if len(body.encode("utf-8")) > max_bytes:
            raise ValueError("SQS task payload is too large; pass an ID instead of a large object")
        self._client.send_message(QueueUrl=self.queue_url, MessageBody=body)


__all__ = ["SqsTaskQueue", "encode_task", "decode_task"]
