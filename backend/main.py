"""FastAPI stub server for the Ambulance Scribe + Safety Check system.

Phase 1 stub: serves the synthetic mock record and flags from an in-memory
copy so the frontend and backend contributors can integrate before the real
pipeline exists. No LLM calls happen anywhere in this module; the app imports
and starts with ``LLM_API_KEY`` unset (Req 9.14).

Run from the repository root with::

    uvicorn backend.main:app --port 8000

Task 4.1 builds only the app shell: the FastAPI app, CORS locked to the two
frontend dev origins, the in-memory mutable server state (a deep copy of
``shared/mock_record.json``), and the error/response-validation helpers. The
actual endpoints are appended by tasks 4.2 - 4.5 in the clearly marked sections
below.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import store
from backend.outputs import make_checklist, make_pre_alert, make_sbar
from shared.schema import (
    ErrorBody,
    Event,
    Flag,
    PatientRecord,
    SourceRef,
    Sourced,
    Utterance,
    UtteranceRequest,
)

# ---------------------------------------------------------------------------
# SCRIBE_MODE: stub (default) vs live (Task 3.1 — Req 3.1, 3.2)
# ---------------------------------------------------------------------------

# ``SCRIBE_MODE`` selects the pipeline behavior and defaults to ``stub`` so an
# unset environment keeps the exact Phase 1 mock behavior and the existing stub
# tests pass untouched (Req 3.1, 3.2). It is read once, at import time, and
# normalized (trim + lowercase) so values like ``"Live"`` or ``" live "`` are
# accepted. Anything other than ``"live"`` is treated as stub.
#
# This task (3.1) wires only the mode flag and the live-mode startup replay.
# The utterance pipeline (3.2) and scenario play (3.3) branch on ``_is_live()``
# at the clearly marked endpoint sections below; stub behavior stays as-is.
SCRIBE_MODE = os.environ.get("SCRIBE_MODE", "stub").strip().lower()


def _is_live() -> bool:
    """Return ``True`` only in live mode; stub is the default for any other value."""
    return SCRIBE_MODE == "live"


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

# Exactly the two frontend development server origins are allowed, including on
# preflight. No other origin is permitted (Req 9.11). ``CORSMiddleware`` with an
# explicit ``allow_origins`` list (not ``"*"`` and no regex) enforces this: any
# other Origin receives a response without the ``Access-Control-Allow-Origin``
# header, so the browser blocks it.
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(
    # The current mode is surfaced harmlessly in the title (no new routes).
    title=f"Ambulance Scribe + Safety Check ({SCRIBE_MODE})",
    version="0.1.0",
    description=(
        "Phase 1 stub serving synthetic mock data. Decision support, not "
        "clinical advice."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Mock loading + in-memory server state
# ---------------------------------------------------------------------------

# Resolve the mock path from the repository root robustly: this file lives at
# ``<repo>/backend/main.py``, so the repo root is its parent's parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_RECORD_PATH = REPO_ROOT / "shared" / "mock_record.json"


def _load_mock() -> dict[str, Any]:
    """Read and parse ``shared/mock_record.json`` into a plain dict.

    This is the pristine, never-mutated source. The mutable server state is
    always a deep copy of what this returns, so relay/ack/confirm (added in
    later tasks) mutate only the in-memory copy, never the file.
    """
    with MOCK_RECORD_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


class ServerState:
    """The in-memory, mutable server state for the stub.

    Holds the current :class:`PatientRecord` and the list of :class:`Flag`s,
    both validated through the schema on load. ``reset`` re-copies from the
    pristine mock so later endpoints (and tests) can restore a clean baseline
    without touching ``shared/mock_record.json`` on disk.
    """

    def __init__(self) -> None:
        self._pristine: dict[str, Any] = _load_mock()
        self.record: PatientRecord
        self.flags: list[Flag]
        self.reset()

    def reset(self) -> None:
        """Re-copy the current record and flags from the pristine mock.

        A deep copy of the pristine dict is validated through the schema, so
        mutations to ``self.record`` / ``self.flags`` can never leak back to the
        pristine source or to the file on disk.
        """
        snapshot = copy.deepcopy(self._pristine)
        self.record = PatientRecord.model_validate(snapshot["record"])
        self.flags = [Flag.model_validate(flag) for flag in snapshot["flags"]]


# Module-level singleton. Created at import time so the app has state ready as
# soon as ``uvicorn backend.main:app`` imports this module; a startup hook also
# re-copies it to guarantee a clean baseline per process (Req 9.14: no network).
state = ServerState()


@app.on_event("startup")
def _load_state_on_startup() -> None:
    """Prepare in-memory state when the app starts.

    Stub mode (the default) re-copies the pristine mock into ``state`` exactly
    as in Phase 1, so stub behavior is unchanged. Live mode additionally
    replays the persisted Event_Log from disk into the Store's in-memory log
    (Req 1.5, 3.1); the ``backend.store`` import above does no I/O, so this is
    the first and only point disk is touched, and only under live mode.
    """
    state.reset()
    if _is_live():
        store.load_from_disk()


# ---------------------------------------------------------------------------
# Error + response-validation helpers
# ---------------------------------------------------------------------------


def error_response(
    status_code: int,
    category: str,
    detail: str,
    field: str | None = None,
) -> JSONResponse:
    """Build a JSON response whose body matches the :class:`ErrorBody` model.

    Every error path in the stub returns through here so error bodies are
    uniform ``{category, field?, detail}`` (see ``shared/api.md``). ``field`` is
    omitted from the body when ``None``.
    """
    body = ErrorBody(category=category, field=field, detail=detail)
    # ``exclude_none`` keeps the optional ``field`` out of the body when unset.
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
    )


M = TypeVar("M", bound=BaseModel)


def validate_response(data: Any, model: type[M]) -> JSONResponse:
    """Validate an outgoing body against ``model`` before sending it.

    Accepts either a model instance or raw data; on success returns a 200
    ``JSONResponse`` carrying the validated, schema-serialized body. On failure
    returns HTTP 500 with an :class:`ErrorBody` whose ``category`` is
    ``response_validation`` and does not send the invalid body (Req 9.12,
    9.13).
    """
    try:
        validated = model.model_validate(data)
    except ValidationError as exc:
        field = _first_error_field(exc)
        return error_response(
            status_code=500,
            category="response_validation",
            detail="response body failed schema validation",
            field=field,
        )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(validated.model_dump(mode="json")),
    )


def validate_response_list(data: list[Any], model: type[M]) -> JSONResponse:
    """Validate a list whose every item must satisfy ``model`` before sending.

    Several endpoints (``/api/flags``, ``/api/events``) return a JSON array of
    schema models. On any item's failure, respond 500 ``response_validation``
    and send nothing (Req 9.12, 9.13).
    """
    validated_items: list[dict[str, Any]] = []
    try:
        for item in data:
            validated = model.model_validate(item)
            validated_items.append(validated.model_dump(mode="json"))
    except ValidationError as exc:
        field = _first_error_field(exc)
        return error_response(
            status_code=500,
            category="response_validation",
            detail="response body failed schema validation",
            field=field,
        )
    return JSONResponse(status_code=200, content=jsonable_encoder(validated_items))


def _first_error_field(exc: ValidationError) -> str | None:
    """Return a dotted path to the first offending field, if any."""
    errors = exc.errors()
    if not errors:
        return None
    location = errors[0].get("loc", ())
    if not location:
        return None
    return ".".join(str(part) for part in location)


# ---------------------------------------------------------------------------
# Exception handlers: every error serializes as an ErrorBody
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Serialize FastAPI/Pydantic request-validation errors (422) as ErrorBody.

    The offending field is named from the first error's location, dropping the
    leading ``body``/``query``/``path`` segment so ``field`` reads like
    ``text`` rather than ``body.text`` (Req 9.5).
    """
    errors = exc.errors()
    field: str | None = None
    detail = "request body failed validation"
    if errors:
        location = [str(part) for part in errors[0].get("loc", ())]
        if location and location[0] in {"body", "query", "path", "header"}:
            location = location[1:]
        field = ".".join(location) if location else None
        detail = errors[0].get("msg", detail)
    return error_response(
        status_code=422,
        category="validation",
        detail=detail,
        field=field,
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Serialize raised HTTP errors as an ErrorBody.

    Endpoints raise ``HTTPException`` with a ``detail`` that is either an
    ErrorBody-shaped dict (``{category, field?, detail}``) or a plain string.
    Either way the response body is normalized to the ErrorBody model so the
    contract in ``shared/api.md`` holds.
    """
    category_by_status = {
        404: "not_found",
        409: "conflict",
        422: "validation",
        500: "processing",
    }
    default_category = category_by_status.get(exc.status_code, "processing")

    detail = exc.detail
    if isinstance(detail, dict):
        return error_response(
            status_code=exc.status_code,
            category=str(detail.get("category", default_category)),
            detail=str(detail.get("detail", "")),
            field=detail.get("field"),
        )
    return error_response(
        status_code=exc.status_code,
        category=default_category,
        detail=str(detail),
    )


# ===========================================================================
# Endpoints
#
# The route handlers below are appended by later tasks. Each must build its
# body and return it through ``validate_response`` / ``validate_response_list``
# so every response is schema-validated before sending, and must return errors
# through ``error_response`` (or raise ``HTTPException`` with an ErrorBody-shaped
# detail). All of them read/mutate the module-level ``state`` only.
# ===========================================================================

# --- Task 4.2: GET endpoints -------------------------------------------------
#   GET /api/record, /api/flags, /api/sbar, /api/preAlert, /api/checklist,
#   /api/events


@app.get("/api/record")
def get_record() -> JSONResponse:
    """Return the current :class:`PatientRecord` (Req 7.3, 9.1).

    The body is validated against ``PatientRecord`` before being sent, so a
    schema regression surfaces as a 500 ``response_validation`` rather than a
    malformed body reaching the client.

    Live mode (Task 3.2) derives the current record from the Store's Event_Log
    (the single source of truth) instead of reading the in-memory mock; stub
    mode is unchanged.
    """
    if _is_live():
        record, _ = store.derive(store.events())
        return validate_response(record, PatientRecord)
    return validate_response(state.record, PatientRecord)


@app.get("/api/flags")
def get_flags() -> JSONResponse:
    """Return the current list of safety :class:`Flag`s (Req 7.3, 9.1).

    Each item is validated against ``Flag`` before sending (Req 9.12, 9.13).

    Live mode (Task 3.2) derives the current flags from the Store's Event_Log;
    stub mode is unchanged.
    """
    if _is_live():
        _, flags = store.derive(store.events())
        return validate_response_list(flags, Flag)
    return validate_response_list(state.flags, Flag)


@app.get("/api/sbar")
def get_sbar() -> JSONResponse:
    """Return the SBAR handoff text as a JSON string (Req 7.10).

    The body is a plain ``str`` (not a schema model), so it is returned
    directly with a 200 status. ``make_sbar`` reads the in-memory record and
    flags; the Phase 1 stub performs no LLM calls.

    Live mode (Task 3.2) feeds ``make_sbar`` the record and flags derived from
    the Store's Event_Log; stub mode is unchanged.
    """
    if _is_live():
        record, flags = store.derive(store.events())
        sbar = make_sbar(record, flags)
        return JSONResponse(status_code=200, content=sbar)
    sbar = make_sbar(state.record, state.flags)
    return JSONResponse(status_code=200, content=sbar)


@app.get("/api/preAlert")
def get_pre_alert() -> JSONResponse:
    """Return the ED pre-alert text as a JSON string (Req 7.10).

    The body is a plain ``str``; it is returned directly with a 200 status.

    Live mode (Task 3.2) feeds ``make_pre_alert`` the record and flags derived
    from the Store's Event_Log; stub mode is unchanged.
    """
    if _is_live():
        record, flags = store.derive(store.events())
        pre_alert = make_pre_alert(record, flags)
        return JSONResponse(status_code=200, content=pre_alert)
    pre_alert = make_pre_alert(state.record, state.flags)
    return JSONResponse(status_code=200, content=pre_alert)


@app.get("/api/checklist")
def get_checklist() -> JSONResponse:
    """Return the receiving-team checklist as a JSON array of strings (Req 7.10).

    The body is a plain ``list[str]``; it is returned directly with a 200
    status.

    Live mode (Task 3.2) feeds ``make_checklist`` the record derived from the
    Store's Event_Log; stub mode is unchanged.
    """
    if _is_live():
        record, _ = store.derive(store.events())
        checklist = make_checklist(record)
        return JSONResponse(status_code=200, content=checklist)
    checklist = make_checklist(state.record)
    return JSONResponse(status_code=200, content=checklist)


# The Sourced fields on a PatientRecord whose provenance may carry SourceRefs.
# The ``meds_given`` entries are each a ``Sourced[Medication]`` and are handled
# separately because they live in a list.
_SOURCED_SCALAR_FIELDS = (
    "age",
    "sex",
    "chief_complaint",
    "suspected_condition",
    "eta",
    "acuity_esi",
    "allergies",
)


def _collect_source_refs(record: PatientRecord) -> list[SourceRef]:
    """Gather every :class:`SourceRef` across the record's Sourced fields.

    Walks the scalar ``Sourced`` fields and each ``meds_given`` entry (also a
    ``Sourced``) and returns their ``sources`` in field order, which gives a
    stable, deterministic baseline order before the timestamp sort.
    """
    refs: list[SourceRef] = []
    for name in _SOURCED_SCALAR_FIELDS:
        field = getattr(record, name)
        if isinstance(field, Sourced):
            refs.extend(field.sources)
    for med in record.meds_given:
        if isinstance(med, Sourced):
            refs.extend(med.sources)
    return refs


def _synthesize_events(record: PatientRecord, flags: list[Flag]) -> list[Event]:
    """Build a synthetic Event_Log from the mock record and flags.

    One ``utterance`` Event is emitted per distinct source ``utterance_id``
    found across the record's Sourced fields, with a best-effort
    :class:`Utterance` payload reconstructed from the first SourceRef seen for
    that id (``id=utterance_id``, ``text=quote``, ``ts=ts``). One
    ``flag_raised`` Event follows per flag.

    Events are ordered oldest to newest by timestamp (Req 7.5). Utterance
    events sort by their reconstructed ``ts``; flag events have no intrinsic
    timestamp, so they are placed after the utterances they are derived from
    while preserving the flag list order. ``id`` is a deterministic index-based
    string so the log is stable across calls.
    """
    # Deduplicate utterance ids, keeping the first SourceRef seen for each so
    # the reconstructed Utterance is deterministic. ``dict`` preserves insertion
    # order, giving a stable tiebreak when two utterances share a timestamp.
    first_ref_by_id: dict[str, SourceRef] = {}
    for ref in _collect_source_refs(record):
        first_ref_by_id.setdefault(ref.utterance_id, ref)

    # Sort utterances oldest -> newest by their timestamp; insertion order
    # (stable) breaks ties deterministically.
    ordered_refs = sorted(first_ref_by_id.values(), key=lambda ref: ref.ts)

    events: list[Event] = []
    index = 0
    latest_ts = None
    for ref in ordered_refs:
        utterance = Utterance(id=ref.utterance_id, text=ref.quote, ts=ref.ts)
        events.append(
            Event(
                id=f"evt-{index:04d}",
                ts=ref.ts,
                kind="utterance",
                payload={"utterance": utterance.model_dump(mode="json")},
            )
        )
        latest_ts = ref.ts
        index += 1

    # Flags have no timestamp of their own; place them after the utterances
    # (newest utterance ts, or the newest flag just before it) so the overall
    # log stays oldest -> newest, and keep the flag list order among themselves.
    flag_base_ts = latest_ts if latest_ts is not None else None
    for flag in flags:
        flag_ts = flag_base_ts if flag_base_ts is not None else _epoch_utc()
        events.append(
            Event(
                id=f"evt-{index:04d}",
                ts=flag_ts,
                kind="flag_raised",
                payload={"flag": flag.model_dump(mode="json")},
            )
        )
        index += 1

    return events


def _epoch_utc() -> datetime:
    """A deterministic UTC timestamp used only when no utterance ts exists."""
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


@app.get("/api/events")
def get_events() -> JSONResponse:
    """Return the synthesized Event_Log, oldest to newest (Req 7.5, 9.1).

    The stub has no real Event_Log yet, so events are synthesized from the mock
    record and flags. Every item is validated against ``Event`` before sending
    (Req 9.12, 9.13).

    Live mode (Task 3.2) returns the real Event_Log from the Store (oldest
    first) rather than a synthesized one; stub mode is unchanged.
    """
    if _is_live():
        return validate_response_list(store.events(), Event)
    events = _synthesize_events(state.record, state.flags)
    return validate_response_list(events, Event)

# --- Task 4.3: POST /api/utterance + scenario endpoints ----------------------
#   POST /api/utterance, GET /api/scenarios, POST /api/scenario/{id}/play

# The known STUB scenario ids. Stub mode ships a single canned scenario; this
# fixed set backs both ``GET /api/scenarios`` (which lists it) and the stub play
# endpoint's known-id check, so the stub list and the stub 404 boundary never
# drift and the existing stub smoke test ("stemi_hero" in the list; play
# stemi_hero -> 200; play unknown -> 404) keeps passing unchanged.
SCENARIO_IDS: list[str] = ["stemi_hero"]

# ---------------------------------------------------------------------------
# Live scenario corpus (Task 3.3 — Req 3.5, 3.6)
# ---------------------------------------------------------------------------

# Scenario transcripts are authored by another branch (b-scenarios) under
# ``scenarios/<id>.json`` at the repository root. They may not have landed yet,
# so every lookup below tolerates a missing directory or file. ``.gold.json``
# companions (expected fields/flags per Req 5.4) are NOT playable scenarios and
# are excluded from listings.
SCENARIOS_DIR = REPO_ROOT / "scenarios"

# Per-utterance streaming delay (seconds) between scenario utterances so SSE
# subscribers observe incremental updates. Overridable via
# ``SCENARIO_PLAY_DELAY_S`` (tests set it to ``0`` to run without waiting). It
# is read per-call (not cached at import) so a test can set the env var before
# driving the endpoint.
_DEFAULT_SCENARIO_PLAY_DELAY_S = 0.3


def _scenario_play_delay_s() -> float:
    """Return the inter-utterance streaming delay in seconds (Req 3.5).

    Reads ``SCENARIO_PLAY_DELAY_S`` each call and falls back to
    ``_DEFAULT_SCENARIO_PLAY_DELAY_S`` (0.3s) when unset or unparseable. A
    negative value is clamped to ``0`` so the delay is never used as a
    (nonsensical) negative sleep.
    """
    raw = os.environ.get("SCENARIO_PLAY_DELAY_S")
    if raw is None:
        return _DEFAULT_SCENARIO_PLAY_DELAY_S
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_SCENARIO_PLAY_DELAY_S
    return value if value > 0 else 0.0


def _available_scenario_ids() -> list[str]:
    """List playable scenario ids from ``scenarios/*.json`` (Req 3.5).

    An id is the stem of a ``scenarios/*.json`` file that is NOT a
    ``*.gold.json`` companion. Returns ``[]`` when the directory is missing
    (b-scenarios has not landed) rather than raising, so the endpoint never
    crashes on a fresh checkout. Ids are sorted for a stable, deterministic
    listing.
    """
    if not SCENARIOS_DIR.is_dir():
        return []
    ids: list[str] = []
    for path in SCENARIOS_DIR.glob("*.json"):
        # ``foo.gold.json`` has suffixes [".gold", ".json"]; skip those.
        if path.name.endswith(".gold.json"):
            continue
        ids.append(path.stem)
    return sorted(ids)


def _scenario_path(scenario_id: str) -> Path:
    """Resolve the on-disk transcript path for ``scenario_id``."""
    return SCENARIOS_DIR / f"{scenario_id}.json"


def _load_scenario_utterances(scenario_id: str) -> list[UtteranceRequest]:
    """Load ``scenarios/{id}.json`` and normalize it to a list of utterances.

    Tolerates BOTH shapes b-scenarios may write (Req 5.1 and the agreed loader
    contract):

    - a bare JSON list of utterances: ``[{"text": ..., "ts": ...}, ...]``;
    - an object ``{"id": ..., "utterances": [{"text": ..., "ts": ...}, ...]}``.

    Detection: if the parsed JSON is a list, use it directly; if it is a dict
    with an ``"utterances"`` key, use that list. Each item is validated as an
    :class:`UtteranceRequest` so a malformed utterance (missing/empty text,
    missing/mistyped ts) raises here. Raises ``FileNotFoundError`` when the file
    is absent (the caller maps that to 404) and ``ValueError`` for any other
    malformed shape (mapped to 500 ``processing`` by the caller).
    """
    path = _scenario_path(scenario_id)
    if not path.exists():
        raise FileNotFoundError(f"no such scenario file: {path}")

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        raw_utterances = data
    elif isinstance(data, dict) and "utterances" in data:
        raw_utterances = data["utterances"]
    else:
        raise ValueError(
            "scenario file must be a list of utterances or an object with an "
            "'utterances' list"
        )

    if not isinstance(raw_utterances, list):
        raise ValueError("scenario 'utterances' must be a JSON list")

    return [UtteranceRequest.model_validate(item) for item in raw_utterances]


@app.post("/api/utterance")
def post_utterance(body: UtteranceRequest) -> JSONResponse:
    """Accept one submitted utterance and return the current record (Req 7.1, 9.4).

    Declaring ``body`` as :class:`UtteranceRequest` makes FastAPI validate the
    request body; a missing/empty/oversized ``text`` or a missing/mistyped
    ``ts`` is rejected as 422 by the ``RequestValidationError`` handler, which
    names the offending field (Req 9.5, 9.16).

    The Phase 1 stub runs no extraction/safety pipeline and mutates no state: on
    valid input it returns the current mock :class:`PatientRecord` unchanged,
    validated before sending (Req 9.17).
    """
    # TASK 3.2 (Req 3.3, 3.4): live mode runs the real pipeline below; stub mode
    # keeps the no-op, no-side-effect behavior.
    if _is_live():
        return _post_utterance_live(body)
    return validate_response(state.record, PatientRecord)


def _run_live_utterance(text: str, ts: Any) -> None:
    """Run the live pipeline for ONE utterance, appending its events in order.

    This is the reusable core shared by ``POST /api/utterance`` (Task 3.2) and
    scenario play (Task 3.3). Steps (Req 3.3, 3.4):

    1. Build an :class:`Utterance` with a deterministic id derived from the
       current event count (``f"utt-{len(store.events())}"``).
    2. Derive the current record from the Store's Event_Log.
    3. Run the extraction stub ``process_utterance(utt, old_record) -> new``.
    4. Compute the ``fact`` events from the record diff (``store.facts_from``).
    5. Run the safety stub ``evaluate(new_record) -> flags`` and keep only the
       flags whose id is NOT already present in the currently-derived flags.
    6. Assemble the events to append IN ORDER: the ``utterance`` event, then the
       fact events, then one ``flag_raised`` event per new flag.

    Everything that can raise (steps 1-6) happens BEFORE any ``store.append``,
    so a failure there leaves the Event_Log untouched. Only once the full
    ordered batch is assembled do we append; ``store.append`` persists and
    broadcasts each event.

    ``text`` / ``ts`` are validated here by constructing an :class:`Utterance`,
    so an invalid utterance raises before anything is appended. Callers that
    need the all-or-nothing boundary (both of them) wrap this in try/except and
    map a raise to 500 ``processing``.
    """
    # Lazy import keeps module import stub-safe and avoids import-time coupling
    # to the extraction/safety packages (Req 9.14: no network at import).
    from backend import extraction, safety

    # (a)/(b) Build the Utterance with a deterministic, event-count-derived id.
    # Constructing the model validates text/ts against the schema.
    utt = Utterance(
        id=f"utt-{len(store.events())}",
        text=text,
        ts=ts,
    )

    # (c) Current record + flags from the Store (single source of truth).
    old_record, old_flags = store.derive(store.events())

    # (d) Extraction stub: returns the record (unchanged in Phase 1).
    new_record = extraction.process_utterance(utt, old_record)

    # (e) Diff old vs new into deterministic ``fact`` events.
    fact_events = store.facts_from(utt, old_record, new_record)

    # (f) Safety stub: cited flags for the new record (empty in Phase 1).
    flags = safety.evaluate(new_record)

    # (g) Assemble the ordered append batch: utterance first, then facts,
    # then one flag_raised per NEW flag id (not already present).
    existing_flag_ids = {flag.id for flag in old_flags}
    pending: list[Event] = [
        Event(
            id=utt.id,
            ts=utt.ts,
            kind="utterance",
            payload={"utterance": utt.model_dump(mode="json")},
        )
    ]
    pending.extend(fact_events)
    new_flag_index = 0
    for flag in flags:
        if flag.id in existing_flag_ids:
            continue
        pending.append(
            Event(
                id=f"{utt.id}:flag:{new_flag_index}",
                ts=utt.ts,
                kind="flag_raised",
                payload={"flag": flag.model_dump(mode="json")},
            )
        )
        new_flag_index += 1

    # (h) Append-last: persist + broadcast the batch in order. ``store.append``
    # is all-or-nothing per event; the batch was fully built above so the first
    # append (the utterance event) always runs.
    for event in pending:
        store.append(event)


def _post_utterance_live(body: UtteranceRequest) -> JSONResponse:
    """Run the live utterance pipeline with append-last, all-or-nothing semantics.

    Delegates the per-utterance work to :func:`_run_live_utterance`. Everything
    that can raise happens before the first append inside that helper, so a
    failure leaves the Event_Log untouched and surfaces here as 500
    ``processing`` (Req 3.4). On success the response is the record derived from
    the Store after the appends.
    """
    try:
        _run_live_utterance(body.text, body.ts)
    except Exception as exc:  # noqa: BLE001 - any pre-append failure is 500
        # Nothing has been appended yet, so the Event_Log is untouched.
        return error_response(
            status_code=500,
            category="processing",
            detail=f"failed to process utterance: {exc}",
        )

    rec, _ = store.derive(store.events())
    return validate_response(rec, PatientRecord)


@app.get("/api/scenarios")
def get_scenarios() -> JSONResponse:
    """Return the list of known scenario ids as a JSON ``string[]`` (Req 7.13, 3.5).

    Stub mode (the default) returns the fixed :data:`SCENARIO_IDS`, so the
    existing stub smoke test ("stemi_hero" in the list) keeps passing regardless
    of whether the ``scenarios/`` corpus has landed. Live mode lists the real
    playable transcripts discovered under ``scenarios/`` (``*.json`` minus
    ``*.gold.json`` companions), returning ``[]`` when the directory is missing.

    The body is a plain ``list[str]`` (not a schema model), returned directly
    with a 200 status. Leaves the record, flags, and Event_Log unchanged.
    """
    if _is_live():
        return JSONResponse(status_code=200, content=_available_scenario_ids())
    return JSONResponse(status_code=200, content=list(SCENARIO_IDS))


@app.post("/api/scenario/{id}/play")
async def post_scenario_play(id: str) -> JSONResponse:
    """Play a named scenario, returning the derived current record (Req 7.14, 9.18, 3.5, 3.6).

    Stub mode (the default) is unchanged: a known id (one in
    :data:`SCENARIO_IDS`) returns the current mock :class:`PatientRecord` with
    no side effects, and an unknown id is rejected with 404 ``not_found`` via
    the shared ``HTTPException`` handler.

    Live mode streams the scenario transcript through the live pipeline
    (Req 3.5):

    - A missing ``scenarios/{id}.json`` -> 404 ``not_found`` (Req 3.6).
    - Otherwise each utterance is loaded, normalized, and run through the SAME
      per-utterance pipeline as ``POST /api/utterance`` (:func:`_run_live_utterance`),
      in order, appending + broadcasting its events. Between utterances the
      handler ``await``s ``asyncio.sleep(delay)`` so SSE subscribers observe
      incremental updates; the delay defaults to 0.3s and is overridable via
      ``SCENARIO_PLAY_DELAY_S`` (tests set it to 0).
    - If an utterance fails validation or the pipeline raises, the handler
      returns 500 ``processing``. Because play is streamed, events for earlier
      utterances may already be appended; that partial progress is accepted and
      intentional for a streamed play.

    After all utterances, the response is the record derived from the Store,
    validated against :class:`PatientRecord` before sending.
    """
    if _is_live():
        # 404 boundary: the id is known iff its transcript file exists (Req 3.6).
        try:
            utterances = _load_scenario_utterances(id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={
                    "category": "not_found",
                    "detail": f"unknown scenario id: {id}",
                    "field": "id",
                },
            )
        except Exception as exc:  # noqa: BLE001 - malformed file -> 500
            return error_response(
                status_code=500,
                category="processing",
                detail=f"failed to load scenario {id}: {exc}",
            )

        delay = _scenario_play_delay_s()
        for index, utterance in enumerate(utterances):
            try:
                _run_live_utterance(utterance.text, utterance.ts)
            except Exception as exc:  # noqa: BLE001 - pipeline failure -> 500
                # Streamed play: events for earlier utterances may already be
                # appended. That partial progress is accepted (documented above).
                return error_response(
                    status_code=500,
                    category="processing",
                    detail=(
                        f"failed to process scenario {id} at utterance "
                        f"{index}: {exc}"
                    ),
                )
            # Space out appends so SSE subscribers see incremental updates;
            # skip the sleep after the final utterance.
            if delay > 0 and index < len(utterances) - 1:
                await asyncio.sleep(delay)

        rec, _ = store.derive(store.events())
        return validate_response(rec, PatientRecord)

    # Stub mode: unchanged no-side-effect behavior against the fixed id set.
    if id not in SCENARIO_IDS:
        raise HTTPException(
            status_code=404,
            detail={
                "category": "not_found",
                "detail": f"unknown scenario id: {id}",
                "field": "id",
            },
        )
    return validate_response(state.record, PatientRecord)


# --- Task 4.4: relay, ack, confirm -------------------------------------------
#   POST /api/flags/{id}/relay, POST /api/flags/{id}/ack,
#   POST /api/fields/{path}/confirm

from shared.schema import FlagStatus, FieldStatus


def _find_flag(flag_id: str) -> Flag | None:
    """Return the in-memory :class:`Flag` with this ``id``, or ``None``.

    Searches ``state.flags`` only, so a miss leaves every flag untouched and the
    caller can turn it into a 404 (Req 9.8, 11.7).
    """
    for flag in state.flags:
        if flag.id == flag_id:
            return flag
    return None


@app.post("/api/flags/{id}/relay")
def post_flag_relay(id: str) -> JSONResponse:
    """Move a flag to ``relayed`` (Req 7.4, 7.12, 9.6, 9.15, 11.3, 11.7).

    The forward-only state machine (``open -> relayed -> acknowledged``) allows
    relay from ``open`` (-> ``relayed``) and, idempotently, from ``relayed`` (no
    change, no new event). Relay on an ``acknowledged`` flag is an invalid
    transition -> 409 ``conflict``; an unknown id -> 404 ``not_found``. Every
    failure leaves the flag unchanged.
    """
    flag = _find_flag(id)
    if flag is None:
        raise HTTPException(
            status_code=404,
            detail={
                "category": "not_found",
                "detail": f"unknown flag id: {id}",
                "field": "id",
            },
        )
    if flag.status is FlagStatus.acknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "category": "conflict",
                "detail": "cannot relay a flag that is already acknowledged",
                "field": "status",
            },
        )
    # open -> relayed; relayed -> relayed (idempotent no-op).
    flag.status = FlagStatus.relayed
    return validate_response(flag, Flag)


@app.post("/api/flags/{id}/ack")
def post_flag_ack(id: str) -> JSONResponse:
    """Move a flag to ``acknowledged`` (Req 7.4, 7.12, 9.7, 9.15, 11.3, 11.7).

    Ack is allowed from ``relayed`` (-> ``acknowledged``) and, idempotently,
    from ``acknowledged`` (no change, no new event). Ack on an ``open`` flag is
    ack-before-relay -> 409 ``conflict``; an unknown id -> 404 ``not_found``.
    Every failure leaves the flag unchanged.
    """
    flag = _find_flag(id)
    if flag is None:
        raise HTTPException(
            status_code=404,
            detail={
                "category": "not_found",
                "detail": f"unknown flag id: {id}",
                "field": "id",
            },
        )
    if flag.status is FlagStatus.open:
        raise HTTPException(
            status_code=409,
            detail={
                "category": "conflict",
                "detail": "cannot acknowledge a flag that has not been relayed",
                "field": "status",
            },
        )
    # relayed -> acknowledged; acknowledged -> acknowledged (idempotent no-op).
    flag.status = FlagStatus.acknowledged
    return validate_response(flag, Flag)


def _resolve_sourced(record: PatientRecord, path: str) -> Sourced | None:
    """Resolve a dotted ``{path}`` against ``record`` to a :class:`Sourced`.

    The path is ``.``-separated segments; each segment is either a field name
    (resolved with ``getattr`` on a model) or a zero-based integer index into a
    list (for example ``meds_given.0`` -> the first ``Sourced[Medication]``).
    Walking stops and returns the current object as soon as it is a ``Sourced``
    instance, so a path may legitimately end at the ``Sourced`` wrapper rather
    than its ``value``.

    Returns ``None`` (treated as 404 by the caller) when a segment names a
    missing field, indexes a non-list or an out-of-range position, or the fully
    resolved object is not a ``Sourced``. The record is never mutated here.
    """
    segments = path.split(".")
    current: Any = record
    for segment in segments:
        # Stop early: once we reach a Sourced, the remaining segments (if any)
        # would descend into its value, which is not what confirm targets.
        if isinstance(current, Sourced):
            return current
        if segment.isdigit():
            index = int(segment)
            if not isinstance(current, (list, tuple)):
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            if isinstance(current, BaseModel) and hasattr(current, segment):
                current = getattr(current, segment)
            else:
                return None
    return current if isinstance(current, Sourced) else None


@app.post("/api/fields/{path}/confirm")
def post_field_confirm(path: str) -> JSONResponse:
    """Confirm a Sourced field by ``{path}`` (Req 7.4, 7.9, 7.12, 9.9, 9.10, 11.7).

    Resolves the dotted ``{path}`` (for example ``age`` or ``meds_given.0``) to
    a ``Sourced`` field on the in-memory record and sets its ``status`` to
    ``confirmed``, returning that ``Sourced``. Already ``confirmed`` is an
    idempotent 200 with no change. A path that does not resolve to a ``Sourced``
    (bad name, out-of-range index, or a non-Sourced target) -> 404
    ``not_found`` with the record left unchanged.
    """
    sourced = _resolve_sourced(state.record, path)
    if sourced is None:
        raise HTTPException(
            status_code=404,
            detail={
                "category": "not_found",
                "detail": f"path does not resolve to a Sourced field: {path}",
                "field": "path",
            },
        )
    # confirmed -> confirmed is an idempotent no-op; any other status advances.
    sourced.status = FieldStatus.confirmed
    return validate_response(sourced, Sourced)


# --- Task 4.5: GET /api/stream (SSE) -----------------------------------------
#   GET /api/stream

import asyncio
from datetime import timedelta

from fastapi.responses import StreamingResponse

from shared.schema import Clocks, ClockEntry

# The door-to-ECG goal: a 12-lead ECG should be completed within 10 minutes of
# patient contact. This is the widely used STEMI door-to-ECG benchmark; the
# stub derives ``door_to_ecg_target_ts`` as ``contact_ts + DOOR_TO_ECG_GOAL``.
DOOR_TO_ECG_GOAL = timedelta(minutes=10)


def _sse(event_type: str, data: Any) -> str:
    """Serialize one Server-Sent Event frame: ``event: <type>\\ndata: <json>\\n\\n``.

    ``data`` may be a Pydantic model instance, a list of them, or already-plain
    JSON-able data. It is run through ``jsonable_encoder`` so datetimes and
    enums serialize the same way the REST endpoints serialize them, then dumped
    to a single-line JSON string for the SSE ``data:`` field.
    """
    payload = jsonable_encoder(data)
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _parse_aware_datetime(value: Any) -> datetime | None:
    """Parse ``value`` into a timezone-aware :class:`datetime`, or ``None``.

    Accepts an existing ``datetime`` (returned as-is when already aware, or
    assumed UTC when naive) or an ISO 8601 string. Anything that does not parse
    cleanly, or lacks enough information to be a real timestamp, yields ``None``
    so callers can leave the corresponding clock field unset.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # ``fromisoformat`` handles the "+00:00" offsets the contract uses; a
        # trailing "Z" is normalized first since older Pythons reject it.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _earliest_contact_ts(record: PatientRecord) -> datetime | None:
    """Return the earliest SourceRef timestamp across the record, or ``None``.

    This is the patient-contact time: the first moment any utterance about this
    run was recorded. Reuses :func:`_collect_source_refs`, so it walks the same
    Sourced fields (scalars plus each ``meds_given`` entry) the Event_Log
    synthesis does. ``None`` when the record carries no sources at all.
    """
    refs = _collect_source_refs(record)
    timestamps = [ref.ts for ref in refs if ref.ts is not None]
    if not timestamps:
        return None
    return min(timestamps)


def _med_last_dose_ts(med: Sourced, contact_ts: datetime | None) -> datetime | None:
    """Most recent dose timestamp for one ``meds_given`` entry.

    Prefers the medication's own ``time`` field when it parses as a timestamp;
    otherwise falls back to the latest SourceRef ``ts`` on the Sourced entry;
    otherwise to ``contact_ts``. Returns ``None`` only when none of those is
    available, in which case the caller skips the entry (``ClockEntry`` requires
    a ``last_dose_ts``).
    """
    value = med.value if isinstance(med, Sourced) else None
    med_time = getattr(value, "time", None) if value is not None else None
    parsed = _parse_aware_datetime(med_time)
    if parsed is not None:
        return parsed
    source_ts = [ref.ts for ref in med.sources if ref.ts is not None]
    if source_ts:
        return max(source_ts)
    return contact_ts


def _build_clocks(record: PatientRecord, now: datetime) -> Clocks:
    """Build the :class:`Clocks` snapshot from the current record (Req 7.8).

    ``contact_ts`` is the earliest source timestamp; ``eta`` comes from
    ``record.eta.value`` when it parses as a timestamp (else ``None``);
    ``door_to_ecg_target_ts`` is ``contact_ts + DOOR_TO_ECG_GOAL`` when contact
    is known. One :class:`ClockEntry` is emitted per ``meds_given.N`` entry with
    ``med_id = "meds_given.{i}"``, its most recent dose timestamp, and the whole
    non-negative seconds elapsed since that dose relative to ``now`` (UTC).
    """
    contact_ts = _earliest_contact_ts(record)
    eta = _parse_aware_datetime(record.eta.value)
    door_to_ecg_target_ts = (
        contact_ts + DOOR_TO_ECG_GOAL if contact_ts is not None else None
    )

    meds: list[ClockEntry] = []
    for index, med in enumerate(record.meds_given):
        last_dose_ts = _med_last_dose_ts(med, contact_ts)
        if last_dose_ts is None:
            # Without any timestamp a ClockEntry cannot be built; skip it rather
            # than invent a time.
            continue
        elapsed_s = max(0, int((now - last_dose_ts).total_seconds()))
        meds.append(
            ClockEntry(
                med_id=f"meds_given.{index}",
                last_dose_ts=last_dose_ts,
                elapsed_s=elapsed_s,
            )
        )

    return Clocks(
        contact_ts=contact_ts,
        eta=eta,
        door_to_ecg_target_ts=door_to_ecg_target_ts,
        meds=meds,
    )


@app.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events stream of ``record``, ``flags``, then ``clocks`` (Req 7.2, 7.7, 7.8, 9.3).

    On connect the async generator emits, in order and within one second, a
    ``record`` event (the current :class:`PatientRecord`), a ``flags`` event
    (the current ``Flag[]``), and a ``clocks`` event (the current
    :class:`Clocks` snapshot). After that initial burst it emits a ``clocks``
    event once per second until the client disconnects.

    Every payload is validated against its schema model before serialization
    (record -> ``PatientRecord``, each flag -> ``Flag``, clocks -> ``Clocks``),
    so the stream stays consistent with the REST contract. The loop checks
    ``request.is_disconnected()`` each iteration and breaks on disconnect so the
    generator exits cleanly and never hangs.
    """

    async def event_generator() -> Any:
        # Initial burst: record, then flags, then clocks, all validated against
        # their schema models before serialization.
        record = PatientRecord.model_validate(state.record)
        yield _sse("record", record.model_dump(mode="json"))

        flags = [Flag.model_validate(flag) for flag in state.flags]
        yield _sse("flags", [flag.model_dump(mode="json") for flag in flags])

        now = datetime.now(timezone.utc)
        clocks = Clocks.model_validate(_build_clocks(state.record, now))
        yield _sse("clocks", clocks.model_dump(mode="json"))

        # Steady state: one ``clocks`` event per second until the client
        # disconnects. Checking ``is_disconnected`` each loop lets the generator
        # exit cleanly (and keeps tests from hanging).
        while True:
            await asyncio.sleep(1)
            if await request.is_disconnected():
                break
            now = datetime.now(timezone.utc)
            clocks = Clocks.model_validate(_build_clocks(state.record, now))
            yield _sse("clocks", clocks.model_dump(mode="json"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
