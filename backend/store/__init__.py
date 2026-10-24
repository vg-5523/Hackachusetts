"""Store module: append-only event log and derived patient record.

Phase 1 stubs with the public signatures from the design (Components and
Interfaces > store). Real behaviour is wired in Phase 2 (Account D).
"""

from collections.abc import AsyncIterator

from shared.schema import Event, Flag, PatientRecord, Utterance

# In-memory append-only event log (single source of truth).
_events: list[Event] = []


def append(event: Event) -> Event:
    """Append an event to the in-memory log and return it."""
    _events.append(event)
    return event


def events() -> list[Event]:
    """Return a copy of the event log, oldest first."""
    return list(_events)


def derive(events: list[Event]) -> tuple[PatientRecord, list[Flag]]:
    """Fold events into a PatientRecord and its flags."""
    return (PatientRecord(), [])


def facts_from(
    utt: Utterance, old: PatientRecord, new: PatientRecord
) -> list[Event]:
    """Diff two records into `fact` events for the given utterance."""
    return []


async def subscribe() -> AsyncIterator[tuple[str, dict]]:
    """Yield `(kind, data)` updates to a subscriber. Stub yields nothing."""
    if False:
        yield  # pragma: no cover - makes this a valid async generator
    return
