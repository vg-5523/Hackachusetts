"""Test isolation for the eval suite.

Several eval tests drive the live FastAPI app, which persists the Event_Log and
reads ``SCRIBE_MODE`` once at import time. Without isolation a live test can (a)
write the real ``backend/store/event_log.json`` and (b) leave ``backend.main``
imported in live mode, polluting later stub tests (e.g. an int ``age`` produced
by extraction then flunking ``PatientRecord`` validation on a stub read).

The autouse fixture below makes every eval test hermetic:

* ``persist.DEFAULT_PATH`` is pointed at a per-test ``tmp_path`` file. Because
  ``persist.save``/``load`` resolve ``DEFAULT_PATH`` at call time, this
  redirects ALL persistence (including ``store.log.append`` and
  ``store.clear``) to the temp file, so no test writes the real event log.
* ``SCRIBE_MODE`` defaults to ``stub`` for each test unless the test overrides
  it before importing ``backend.main`` (the live tests set it and re-import).
* The in-memory store log is reset before the test, and ``backend.main`` is
  dropped from ``sys.modules`` AFTER each test so the next test re-imports it
  fresh and never inherits a stale module-level ``SCRIBE_MODE``.

A test that needs live mode still sets ``SCRIBE_MODE=live`` and re-imports
``backend.main`` itself; this fixture only guarantees a clean baseline and that
the real event log is never touched.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_store_and_mode(tmp_path, monkeypatch):
    """Redirect persistence to a temp file, default stub mode, reset the log."""
    from backend.store import log as store_log
    from backend.store import persist

    # Call-time DEFAULT_PATH resolution means this redirects every save/load.
    monkeypatch.setattr(persist, "DEFAULT_PATH", tmp_path / "event_log.json")

    # Default to stub for each test; live tests override before importing main.
    monkeypatch.setenv("SCRIBE_MODE", "stub")

    # Start from an empty in-memory log so nothing bleeds in from a prior test.
    store_log.reset()

    yield

    # Drop backend.main so the next test re-imports it fresh (module-level
    # SCRIBE_MODE is read at import time) and never inherits live mode.
    sys.modules.pop("backend.main", None)
    store_log.reset()
