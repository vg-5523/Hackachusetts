"""Atomic JSON persistence for the append-only Event_Log.

The Event_Log is the single source of truth (Req 1.1); this module writes it to
the gitignored file ``backend/store/event_log.json`` (Req 1.4) and reloads it on
startup (Req 1.5). The normal write path is atomic: events are serialized via
``model_dump(mode="json")`` into a list, dumped to a temporary file in the same
directory, flushed and fsynced, then swapped into place with ``os.replace`` so a
reader never observes a half-written file.

Resilient write (live mode must never fail an utterance on a disk hiccup):
``save`` retries the ``os.replace`` swap up to 5 times with a 50 ms wait between
tries (transient Windows sharing/AV locks are the common cause). If every
retry still fails, it falls back to a plain in-place write of ``path``. If that
also fails, it logs a warning and returns WITHOUT raising, so the caller
(:mod:`backend.store.log`) still keeps the event in memory and the request
succeeds. The on-disk log may then lag memory until the next successful write;
that is the accepted tradeoff for never failing a live request on disk trouble.

Loading a missing file yields an empty log. Loading a corrupt file (bad JSON, a
non-list top level, or any item that fails ``Event`` validation) raises
``ValueError`` wrapping the cause, so startup fails loudly rather than silently
resetting the log (Req 1.5).

Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path

from shared.schema import Event

__all__ = ["DEFAULT_PATH", "save", "load", "REPLACE_RETRIES", "REPLACE_WAIT_S"]

logger = logging.getLogger(__name__)

# Default on-disk location: backend/store/event_log.json (gitignored).
DEFAULT_PATH = Path(__file__).resolve().parent / "event_log.json"

# os.replace retry policy: up to 5 attempts, 50 ms apart.
REPLACE_RETRIES = 5
REPLACE_WAIT_S = 0.05


def save(events: list[Event], path: Path | str | None = None) -> None:
    """Persist ``events`` to ``path`` as a JSON list, resiliently.

    Strategy, in order:

    1. Write the payload to a temp file in ``path``'s directory (flush + fsync),
       then ``os.replace`` it into place. Retry the replace up to
       ``REPLACE_RETRIES`` (5) times, waiting ``REPLACE_WAIT_S`` (50 ms) between
       tries, to ride out a transient lock on the destination.
    2. If every replace attempt fails, fall back to a plain write of ``path``
       (truncate + write the same JSON directly).
    3. If the plain write also fails, log a warning and return without raising,
       so a live request is never failed by a disk problem and the event is kept
       in memory by the caller.

    The happy path is still atomic. Only a persistent disk failure degrades to
    the non-atomic write, and only a total failure degrades to "memory only".

    ``path`` defaults to ``None`` and is resolved to the module-level
    :data:`DEFAULT_PATH` AT CALL TIME, so monkeypatching ``persist.DEFAULT_PATH``
    (e.g. in tests, to a temp file) redirects persistence here. A binding of the
    default at def time would ignore such a monkeypatch.
    """
    path = Path(path if path is not None else DEFAULT_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Even the directory could not be ensured; try the plain write (which
        # will likely also fail) so we exercise the single warning-and-return
        # path rather than raising here.
        logger.warning("event log dir could not be created at %s: %s", path.parent, exc)

    serialized = [event.model_dump(mode="json") for event in events]
    payload = json.dumps(serialized)

    # --- Strategy 1: atomic temp-file write + os.replace with retries --------
    if _atomic_replace_with_retries(path, payload):
        return

    # --- Strategy 2: plain in-place write ------------------------------------
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        logger.warning(
            "event log at %s written non-atomically after os.replace retries "
            "were exhausted",
            path,
        )
        return
    except OSError as exc:
        # --- Strategy 3: give up on disk, keep the event in memory -----------
        logger.warning(
            "event log at %s could not be persisted (%s); keeping events in "
            "memory only. The on-disk log will lag until the next successful "
            "write.",
            path,
            exc,
        )
        return


def _atomic_replace_with_retries(path: Path, payload: str) -> bool:
    """Temp-file write then ``os.replace`` into ``path``, retrying the swap.

    Returns ``True`` when the atomic swap eventually succeeds, ``False`` when
    every attempt fails (so the caller can fall back). The temp file is always
    cleaned up on failure so no ``*.tmp`` litter is left behind.
    """
    last_exc: OSError | None = None
    for attempt in range(REPLACE_RETRIES):
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
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, path)
            return True
        except OSError as exc:
            last_exc = exc
            # Clean up the temp file before retrying so we do not leak it.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            if attempt < REPLACE_RETRIES - 1:
                time.sleep(REPLACE_WAIT_S)
        except BaseException:
            # Non-OSError (e.g. serialization already done): clean up and let it
            # propagate; this is not the transient case we retry.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise

    if last_exc is not None:
        logger.warning(
            "os.replace into %s failed after %d attempts: %s",
            path,
            REPLACE_RETRIES,
            last_exc,
        )
    return False


def load(path: Path | str | None = None) -> list[Event]:
    """Load and validate the Event_Log from ``path``.

    Returns ``[]`` when the file does not exist. Otherwise the file is parsed as
    JSON whose top level must be a list, and every item is validated with
    ``Event.model_validate``. Any corruption (bad JSON, a non-list top level, or
    an item that fails validation) raises ``ValueError`` wrapping the cause.

    ``path`` defaults to ``None`` and is resolved to the module-level
    :data:`DEFAULT_PATH` AT CALL TIME, so a monkeypatched ``DEFAULT_PATH`` (tests
    redirecting to a temp file) is honored here too.
    """
    path = Path(path if path is not None else DEFAULT_PATH)
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
