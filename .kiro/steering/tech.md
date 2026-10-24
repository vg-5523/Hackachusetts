# Tech Stack

This project is split into a Python backend and a TypeScript frontend that talk
to each other over a small HTTP + streaming contract. Everything in this file
describes the technology each side uses and where the key integration points
live.

## Backend

- **Language:** Python 3.11. All backend code targets this version.
- **Web framework:** FastAPI. The app is defined in `backend/main.py` and runs
  with `uvicorn backend.main:app --port 8000` from the repository root.
- **Data models:** Pydantic (v2). The shared models live in `shared/schema.py`
  and are the single source of truth for every request and response shape.
- **Testing:** pytest with Hypothesis for property-based tests.
- **Dependencies:** pinned with `==` in `backend/requirements.txt`.

### In-memory event-sourced store

State is held by an in-memory event-sourced store under `backend/store/`. An
append-only event log is the single source of truth, and the patient record is
derived as a pure fold over that log. The log is replayed on startup so the
derived record and the live record always match.

## Frontend

- **Framework:** React, built and served with Vite.
- **Language:** TypeScript, with types hand-mirrored from `shared/schema.py`
  into `shared/types.ts`.
- **Styling:** Tailwind CSS.
- The project lives in `frontend/` (see `frontend/package.json`), with source
  under `frontend/src/`. The Vite dev server runs on port 5173.

### Audio input

Voice capture uses the browser Web Speech API when it is available. A typed
textarea is always present as a fallback, so the app works even when the Web
Speech API is missing or denied. Both paths post the same `{text, ts}` body to
`POST /api/utterance`.

## Backend <-> Frontend communication

- **Request/response:** JSON over HTTP. CORS allows only
  `http://localhost:5173` and `http://127.0.0.1:5173`.
- **Live updates:** Server-Sent Events (SSE). The frontend subscribes to
  `GET /api/stream`, which emits `record`, `flags`, and `clocks` events. SSE is
  one-directional (server to browser); the browser sends data back through the
  normal HTTP endpoints.

## LLM access

- All model calls go through a single wrapper, `call_llm`, defined in
  `backend/llm.py`. No other module calls an LLM provider directly.
- The wrapper reads the `LLM_API_KEY` environment variable at call time. When
  `LLM_API_KEY` is unset or empty, `call_llm` raises before any network request,
  and the FastAPI stub still starts and serves every endpoint from mock data.
- Copy `.env.example` to `.env` to set `LLM_API_KEY` locally. Never commit real
  keys.

## Conventions

- Backend models are defined once in `shared/schema.py`; TypeScript types in
  `shared/types.ts` mirror them by hand.
- Timestamps are offset-aware ISO 8601.
- Responses are validated against the Pydantic schema before they are sent.
