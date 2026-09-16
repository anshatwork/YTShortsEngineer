"""NATS JetStream adapter for :class:`~los.events.broker.Broker`.

Durable streams give per-consumer offsets and replay-from-offset-0 — the properties event sourcing
needs. The stream captures ``<prefix>.>`` so every event type lands in one replayable log; each
subscriber is a durable pull/push consumer that acks on success (redelivery on failure → at-least-
once, which is safe because every consumer is idempotent).

Import of ``nats`` is lazy so the package (and the in-memory dev/test path) has no hard dependency
on the client library.
"""

from __future__ import annotations

import logging
from typing import Any

from los.domain_shared.envelope import Event
from los.events.broker import Broker, Handler

logger = logging.getLogger(__name__)


class NatsBroker(Broker):
    def __init__(self, url: str, stream: str, subject_prefix: str = "events") -> None:
        self._url = url
        self._stream = stream
        self._prefix = subject_prefix
        self._nc: Any = None
        self._js: Any = None

    async def start(self) -> None:
        import nats  # lazy

        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()
        # Idempotent stream creation capturing all event subjects.
        try:
            await self._js.add_stream(name=self._stream, subjects=[f"{self._prefix}.>"])
            logger.info("created JetStream stream %s (%s.>)", self._stream, self._prefix)
        except Exception:
            # Already exists (or race) — fine; JetStream add_stream is not natively idempotent.
            logger.debug("JetStream stream %s already present", self._stream)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None

    async def publish(self, event: Event) -> None:
        if self._js is None:
            raise RuntimeError("NatsBroker.start() not called")
        subject = event.subject(self._prefix)
        # Msg-Id dedup header: JetStream drops duplicates within the stream's dedup window.
        await self._js.publish(
            subject,
            event.to_json().encode("utf-8"),
            headers={"Nats-Msg-Id": event.event_id},
        )
        logger.info("published %s to %s (event_id=%s)", event.type, subject, event.event_id)

    async def subscribe(self, event_type: str, durable: str, handler: Handler) -> None:
        if self._js is None:
            raise RuntimeError("NatsBroker.start() not called")
        subject = f"{self._prefix}.{event_type}"

        async def _cb(msg: Any) -> None:
            try:
                event = Event.from_json(msg.data)
                await handler(event)
                await msg.ack()
            except Exception:
                logger.exception("handler failed for %s; leaving unacked for redelivery", subject)

        await self._js.subscribe(subject, durable=durable, cb=_cb, manual_ack=True)
        logger.info("subscribed durable=%s to %s", durable, subject)
