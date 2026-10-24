# Project Structure & Ownership

This project is built by several contributors in parallel. To avoid merge conflicts,
each top-level area has exactly one Owner. Work inside your owned folder and treat the
shared contract as read-only unless everyone agrees to a change.

## Folders and Owners

| Folder | Owner | Purpose |
|---|---|---|
| `shared` | Contract | Holds the shared contract: the Pydantic schema, the mirrored TypeScript types, the API definition, and mock data. It is the single source of truth every other folder depends on. |
| `backend/extraction` | Account A | Python package that turns paramedic utterances into structured PatientRecord fields with provenance. Its public functions are exposed in `backend/extraction/__init__.py`. |
| `backend/safety` | Account B | Python package that evaluates a PatientRecord and raises safety Flags (duplicate dose, allergy conflict, interaction, contradiction). Its public functions are exposed in `backend/safety/__init__.py`. |
| `backend/store` | Account D | Python package holding the in-memory event-sourced store from which the PatientRecord is derived and replayed. Its public functions are exposed in `backend/store/__init__.py`. |
| `backend/outputs` | Account D | Python package that generates the SBAR handoff, ED pre-alert, and bed/resus checklist from a PatientRecord. Its public functions are exposed in `backend/outputs/__init__.py`. |
| `frontend` | Account C | React + Vite + TypeScript + Tailwind application that paramedics and receiving clinicians use. It consumes the API and shared types. |
| `scenarios` | Account D | Holds synthetic scenario scripts used to drive demos and replays. Contains a placeholder `README.md` until scenarios are added. |
| `eval` | Account D | Holds evaluation harnesses and fixtures for measuring extraction and safety quality. Contains a placeholder `README.md` until evaluations are added. |
| `.kiro` | Contract | Holds the spec, steering files, and Kiro configuration that define how the project is built. |

## Ownership Rule (Owner_Folder)

Each contributor edits only files inside the contributor's owned folder listed above.
Do not modify files in a folder you do not own. If you need a change in someone else's
folder, coordinate with that Owner instead of editing it directly. This keeps parallel
work free of merge conflicts.

## Shared Contract Rule

A change to the shared contract — anything inside the `shared/` folder (the Pydantic
schema `shared/schema.py`, plus the mirrored TypeScript types, the API definition, and
the mock data that are added alongside it) — requires agreement from all contributors
before the change is made. The contract is what lets everyone build in parallel, so it
does not change unilaterally.

## Coordinated Backend-Root Files

Some files sit at the `backend` root, outside any per-owner folder, and are shared
across backend owners. Treat them like the shared contract: edit them only by
agreement among the affected contributors.

- `backend/llm.py` — the single `call_llm` wrapper through which all LLM calls pass.
- The FastAPI entrypoint `main.py` (the API stub serving every endpoint) is added at
  this same backend root and is likewise a coordinated file edited by agreement.
