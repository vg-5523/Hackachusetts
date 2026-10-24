"""Append-only in-memory Event_Log backed by disk, all-or-nothing.

This module owns the live Event_Log (Req 1.1): the single, ordered,
append-only source of truth. It keeps the events in memory for fast reads and
mirrors them to ``backend/store/event_log.json`` via :mod:`backend.store.persist`
so the log survives restarts.

``append`` is strictly all-or-nothing (Req 1.6). Before an event joins the log
it must clear three gates, in order:

1. ``validate_event`` (from :mod:`backend.store.validate`) accepts its ``kind``
   and ``payload`` shape, otherwise it raises ``ValueError``.
2. Its ``id`` is not already present in the log; a duplicate raises
   ``ValueError`` naming the offending id.
3. Persistence succeeds. We build the prospective new list
   (``existing + [event]``) and hand the whole thing to ``persist.save``. Only
   when that returns do we commit the event to the in-memory list.

If any gate fails the in-memory list and the on-disk file are both left
exactly as they were, and the error propagates to the caller. Because we
persist the prospective list *before* mutating memory, the file and memory can
never drift: either both gain the event or neither does.

Reads (:func:`events`) hand back a shallow copy of the list, oldest first, so a
caller can never mutate the Store's internal list by holding the return value.

Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

from shared.schema import Event

from . import persist
from .validate import validate_event

__all__ = ["append", "events", "load_from_disk", "reset"]


# The live, in-memory Event_Log: ordered oldest-first, append-only in normal
# operation. ``reset`` and ``load_from_disk`` replace it wholesale; ``append``
# only ever grows it by one, and only after persistence has succeeded.
_events: list[Event] = []


def append(event: Event) -> Event:
    """Validate, de-duplicate, persist, then append ``event`` to the log.

    The four steps run in order and the whole operation is all-or-nothing:

    1. ``validate_event(event)`` — raises ``ValueError`` on an unknown kind or a
       payload that does not match that kind's shape.
    2. Duplicate-id check — if any event already in the log shares ``event.id``,
       raise ``ValueError`` naming the duplicate id.
    3. Persist — build ``new_events = _events + [event]`` and call
       ``persist.save(new_events)`` (default path ``persist.DEFAULT_PATH``). Any
       failure here propagates.
    4. Commit — only once persistence has succeeded, append ``event`` to the
       in-memory ``_events``.

    If step 1, 2, or 3 fails, ``_events`` and the on-disk file are both left
    unchanged and the raised error propagates. Returns the appended ``event`` on
    success.
    """
    # Gate 1: kind / payload shape. Raises ValueError naming the bad field.
    validate_event(event)

    # Gate 2: reject a duplicate id without touching memory or disk.
    for existing in _events:
        if existing.id == event.id:
            raise ValueError(f"id: duplicate event id {event.id!r}")

    # Gate 3: persist the prospective full log first. If this raises, memory is
    # still untouched below and persist.save left the file intact (its write is
    # atomic), so the log and file stay in sync.
    new_events = _events + [event]
    persist.save(new_events)

    # Gate 4 (commit): persistence succeeded, so it is now safe to grow memory.
    # Append in place so any module holding a reference to ``_events`` via this
    # module sees the update.
    _events.append(event)
    return event


def events() -> list[Event]:
    """Return a shallow copy of the in-memory Event_Log, oldest first.

    The copy means callers can iterate, slice, or discard the result without
    mutating the Store's internal list; the ``Event`` objects themselves are
    shared, which is safe because events are immutable records once appended.
    """
    return list(_events)


def load_from_disk() -> None:
    """Replay the persisted Event_Log into memory (startup hook).

    Replaces the in-memory ``_events`` with whatever ``persist.load()`` returns
    from the default path. A missing file loads as an empty log; a corrupt file
    raises ``ValueError`` (from ``persist.load``) so startup fails loudly rather
    than silently discarding history. This does not write to disk.
    """
    global _events
    _events = persist.load()


def reset(events: list[Event] | None = None) -> None:
    """Replace the in-memory Event_Log for tests. Does not touch disk.

    With no argument (or ``None``) the in-memory log is cleared to empty. With a
    list it is replaced by a shallow copy of that list so later mutation of the
    caller's list does not leak into the Store. This is an in-memory operation
    only: it never reads or writes ``event_log.json``, so a test can set up log
    state without persistence side effects (pair it with a temp
    ``persist.DEFAULT_PATH`` if an ``append`` under test must also persist).
    """
    global _events
    _events = [] if events is None else list(events)
