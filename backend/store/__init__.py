"""Store package: append-only Event_Log and the derived patient record.

This package is the single source of truth (Req 1.1). The real behaviour lives
in focused sibling modules; this ``__init__`` is the thin public facade that
keeps the EXACT Phase 1 signatures (``append`` / ``events`` / ``derive`` /
``facts_from`` / async ``subscribe``) so ``backend/main.py`` and every existing
caller keep working unchanged, while delegating the work to:

- :mod:`backend.store.log` — the in-memory, disk-backed, all-or-nothing log
  (``append`` / ``events`` / ``load_from_disk`` / ``reset``).
- :mod:`backend.store.derive` — the one pure fold ``derive(events)``.
- :mod:`backend.store.facts` — ``facts_from(utt, old, new)`` record diff.
- :mod:`backend.store.broadcast` — SSE pub/sub (``publish`` / async
  ``subscribe``).
- :mod:`backend.store.persist` — atomic JSON persistence.

Startup replay is explicit, not implicit. Importing this package performs NO
disk I/O: a corrupt or unreadable ``event_log.json`` must not be able to break a
plain ``import backend.store`` (which FastAPI does at module load). Instead the
caller (``backend/main.py``, under ``SCRIBE_MODE=live``) calls
:func:`load_from_disk` once at startup to replay the persisted log into memory.

Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from shared.schema import Event, Flag, PatientRecord

from . import broadcast
from .broadcast import subscribe
from .derive import derive
from .facts import facts_from
from .log import events, load_from_disk, reset
from .log import append as _log_append

__all__ = [
    "append",
    "events",
    "derive",
    "facts_from",
    "subscribe",
    "load_from_disk",
    "reset",
    "current_state",
]


def append(event: Event) -> Event:
    """Append ``event`` to the Event_Log, then broadcast the derived state.

    Delegates to :func:`backend.store.log.append`, which is all-or-nothing
    (validate -> dedupe id -> persist -> commit in memory). Once the event is
    durably appended, the newly-derived ``(record, flags)`` is published so SSE
    subscribers see the update: ``derive(events())`` is recomputed and pushed as
    a ``record`` message plus a ``flags`` message.

    Clocks are built in ``main.py``, so publishing ``record`` + ``flags`` here
    is sufficient; this module deliberately does not import ``main``.

    Broadcasting is best-effort and never breaks ``append``: the event is
    already persisted and committed by the time we publish, so any failure in
    deriving or publishing is swallowed rather than propagated. Returns the
    appended ``event``.
    """
    appended = _log_append(event)

    # Best-effort fan-out. The event is already persisted + committed, so a
    # failure here must not surface to the caller or undo the append.
    try:
        record, flags = derive(events())
        broadcast.publish("record", record.model_dump(mode="json"))
        broadcast.publish(
            "flags", [flag.model_dump(mode="json") for flag in flags]
        )
    except Exception:
        # Swallow: the log is the source of truth and is already updated. A
        # broken broadcast only costs a live SSE refresh, which the next append
        # (or a client reconnect reading GET endpoints) recovers.
        pass

    return appended


def current_state() -> tuple[PatientRecord, list[Flag]]:
    """Convenience: derive the current ``(record, flags)`` from the live log."""
    return derive(events())
