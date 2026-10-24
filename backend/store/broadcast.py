"""In-process pub/sub for SSE fan-out.

A minimal, dependency-free broadcaster: publishers call :func:`publish`
(safe from synchronous code) and each subscriber gets its own
``asyncio.Queue``. :func:`subscribe` is an async generator that yields
``(kind, data)`` tuples and cleans up its queue when the consumer stops
iterating, so a disconnected subscriber never leaks.

Used by the Store to fan ``record`` / ``flags`` / ``clocks`` updates out to
SSE clients, but the payloads are intentionally generic: ``kind`` is a free
-form string and ``data`` is a plain ``dict``.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, Set, Tuple

__all__ = ["publish", "subscribe", "subscriber_count", "_reset"]

# Bound each subscriber queue so a slow/stalled consumer can never make the
# publisher grow memory without limit. When a queue is full we drop the oldest
# item to make room for the newest, keeping the stream fresh and never blocking.
_MAX_QUEUE_SIZE = 1000

# Module-level registry of active subscriber queues.
_subscribers: Set["asyncio.Queue[Tuple[str, Dict]]"] = set()


def publish(kind: str, data: Dict) -> None:
    """Fan ``(kind, data)`` out to every currently-subscribed queue.

    Safe to call from synchronous code: it never awaits and never blocks the
    publisher. Delivery is best-effort — if a subscriber's queue is full the
    oldest pending item is dropped to make room for the newest one.
    """
    item: Tuple[str, Dict] = (kind, data)
    # Iterate over a snapshot so a subscriber unregistering concurrently does
    # not mutate the set mid-iteration.
    for queue in list(_subscribers):
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop the oldest item, then retry once. If it still fails (racing
            # consumer refilled it), skip this subscriber for this event.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                continue


async def subscribe() -> AsyncIterator[Tuple[str, Dict]]:
    """Yield ``(kind, data)`` events until the consumer stops iterating.

    Registers a fresh queue, then loops awaiting new items. When the consumer
    breaks out of the loop, is cancelled, or the generator is closed, the queue
    is removed from the registry so it stops receiving (and holding) events.
    """
    queue: "asyncio.Queue[Tuple[str, Dict]]" = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    _subscribers.add(queue)
    try:
        while True:
            item = await queue.get()
            yield item
    finally:
        # GeneratorExit, cancellation, or normal teardown all land here.
        _subscribers.discard(queue)


def subscriber_count() -> int:
    """Return the number of currently-registered subscribers (for tests)."""
    return len(_subscribers)


def _reset() -> None:
    """Drop all subscribers. Test helper to isolate module state."""
    _subscribers.clear()
