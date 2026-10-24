"""Atomic JSON persistence for the append-only Event_Log.

The Event_Log is the single source of truth (Req 1.1); this module writes it to
the gitignored file ``backend/store/event_log.json`` (Req 1.4) and reloads it on
startup (Req 1.5). Writes are atomic: each event is serialized via
``model_dump(mode="json")`` into a list, dumped to a temporary file in the same
directory, flushed and fsynced, then swapped into place with ``os.replace`` so a
reader never observes a half-written file.

Loading a missing file yields an empty log. Loading a corrupt file (bad JSON, a
non-list top level, or any item that fails ``Event`` validation) raises
``ValueError`` wrapping the cause, so startup fails loudly rather than silently
resetting the log (Req 1.5).

Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from shared.schema import Event

__all__ = ["DEFAULT_PATH", "save", "load"]

# Default on-disk location: backend/store/event_log.json (gitignored).
DEFAULT_PATH = Path(__file__).resolve().parent / "event_log.json"


def save(events: list[Event], path: Path | str = DEFAULT_PATH) -> None:
    """Atomically persist ``events`` to ``path`` as a JSON list.

    Each event is serialized with ``model_dump(mode="json")``. The payload is
    written to a ``NamedTemporaryFile`` in the same directory as ``path`` (so
    the final rename stays on one filesystem), flushed and fsynced to durably
    hit disk, then moved into place with ``os.replace`` for an atomic swap.
    Parent directories are created if missing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = [event.model_dump(mode="json") for event in events]

    # delete=False so we control the lifetime: on success os.replace consumes
    # the temp file; on failure we remove it in the finally block.
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with tmp:
            json.dump(serialized, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # The replace did not happen (or an earlier step failed); clean up the
        # temp file so we never leave orphaned ``*.tmp`` litter behind.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def load(path: Path | str = DEFAULT_PATH) -> list[Event]:
    """Load and validate the Event_Log from ``path``.

    Returns ``[]`` when the file does not exist. Otherwise the file is parsed as
    JSON whose top level must be a list, and every item is validated with
    ``Event.model_validate``. Any corruption (bad JSON, a non-list top level, or
    an item that fails validation) raises ``ValueError`` wrapping the cause.
    """
    path = Path(path)
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read event log at {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"event log at {path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"event log at {path} must be a JSON list, got {type(data).__name__}"
        )

    events: list[Event] = []
    for index, item in enumerate(data):
        try:
            events.append(Event.model_validate(item))
        except Exception as exc:  # pydantic ValidationError and friends
            raise ValueError(
                f"event log at {path} has an invalid event at index {index}: "
                f"{exc}"
            ) from exc

    return events
