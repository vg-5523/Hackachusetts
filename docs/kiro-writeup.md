# Building Ambulance Scribe + Safety Check with Kiro

A short account of how this project was built, what worked, and what is still open. Where a
capability is not built yet, it is marked TODO rather than described as done.

## Tools used

- **Spec workflow** — per-account specs under `.kiro/specs/` (requirements, design, tasks).
- **Steering docs** — `.kiro/steering/product.md`, `tech.md`, `structure.md` as always-on project rules.
- **File + shell tools** — reading the shared contract, writing owned folders, running `pytest` and
  the offline cache pre-warm.
- **Direct API probing** — a one-off RxNorm call to test whether the RxNav interaction API still
  works (it does not; see below).

Early on, a request stalled for roughly **11 minutes** because the agent leaned on web search while
exploring. The fix was a standing instruction: **"do not use web search."** Investigation now stays
in the repo and in the one first-party API the code itself calls (RxNorm, for drug-name
normalization), which kept later turns fast and predictable.

## Spec-driven development vs vibe coding

The project is **contract-first**. Before feature work, the shared contract was fixed:
`shared/schema.py` (Pydantic v2 models), `shared/api.md` (the HTTP contract), and mock data. Every
account then wrote a small spec (requirements → design → tasks) against that frozen contract rather
than improvising.

Why the **folder ownership** worked: `structure.md` assigns exactly one owner per top-level folder
(`backend/extraction` = Account A, `backend/safety` = Account B, `frontend` = Account C,
`backend/store` + `backend/outputs` + `scenarios` + `eval` = Account D, `shared` + `.kiro` = Contract).
Each turn edited only its owned folder and treated `shared/` as read-only. That single rule let the
safety engine, the scenarios, and the docs be built in separate branches with no merge conflicts and
no accidental cross-edits. Vibe coding would have blurred those lines and produced churn in files
other contributors depend on.

### What is actually built today

- **`backend/safety/`** — the deterministic safety engine (`evaluate`), with unit tests passing.
- **`scenarios/`** — five scripted transcripts plus gold files.
- **`shared/`** — the frozen contract (schema, `api.md`, mock data) and Phase 1 stubs.

TODO: the following are Phase 1 stubs, not finished features — extraction
(`backend/extraction`), the store (`backend/store`), the SBAR / pre-alert / checklist outputs
(`backend/outputs`), the live FastAPI pipeline wiring (`backend/main.py`), and the React frontend
(`frontend/`). Update this section as each is implemented.

## Agent hooks

Hooks can automate checks on events (file save, task completion, pre/post tool use). Candidate hooks
for this repo: run `pytest backend/safety` on save under `backend/safety/`, and validate
`scenarios/*.json` on save under `scenarios/`.

TODO: no agent hooks have been created or run yet. Record here which hooks were added, their triggers,
and whether they fired cleanly.

## Steering docs

Three always-on steering files encode the non-negotiables so every turn inherits them:

- **product.md** — provenance on every field; the AI never talks to the crew directly; the
  `say_to_crew` relay always goes through a human; synthetic data only; the disclaimer
  "decision support, not clinical advice."
- **tech.md** — Python 3.11, FastAPI, Pydantic v2, pytest + Hypothesis, React/Vite/Tailwind, SSE,
  the single `call_llm` wrapper.
- **structure.md** — folder owners and the edit rules described above.

These steering docs are why safety, scenarios, and docs stayed consistent without re-explaining the
rules each turn.

## Property-based testing

The stack includes **Hypothesis** (pinned in `backend/requirements.txt`) for property-based tests,
and the contract spec defines named properties (schema round-trip, whole-input rejection, flag state
machine, append all-or-nothing, replay equals live, quotes-are-substrings). The safety engine's ids
are a pure function of type + rule_key + sorted evidence, which is a natural property target
(idempotent ids; evidence order irrelevant).

TODO: no property-based tests have been written or run yet. The safety engine currently ships
example-based unit tests only. Fill in which properties were implemented, example counts, and any
counterexamples Hypothesis found.

## MCP

No MCP servers are configured for this project. The one piece of external data the code needs
(RxNorm drug-name normalization) is reached directly and cached on disk rather than through an MCP
tool.

TODO: if an MCP server is added later (for example a medical-reference server), document the server,
its tools, and how the safety engine uses it.

## Powers

No Kiro Powers are installed.

TODO: if a Power is added later (packaged docs, steering, or MCP tools), record which Power, what it
provided, and where it was used.

---

### Case study: the RxNav interaction API and the offline cache

While building `backend/safety`, the plan assumed a live drug-interaction lookup. Testing the RxNav
interaction endpoint directly returned **HTTP 404 — the interaction API is retired.** The RxNorm
*name-normalization* endpoint still works (aspirin → rxcui 1191).

So the safety engine uses **RxNorm for drug names and a curated `backend/safety/rules.json` for
interactions.** Two consequences shaped the design:

1. **`backend/safety/rules.json` is the interaction source of truth.** Interactions, drug classes
   (penicillin ↔ amoxicillin), and citations (name + URL) are curated in that file instead of fetched
   at runtime.
2. **A pre-warmed, on-disk cache makes the engine work with no network.** Every RxNorm response is
   cached under `backend/safety/cache/`, pre-warmed and committed for the eleven demo drugs. With the
   cache present, `evaluate(record)` runs fully offline; normalization only touches the network on a
   true cache miss, and even then degrades gracefully to the lowercased name.

This is the payoff of spec-driven, contract-first work: a surprise in one owned folder
(`backend/safety`) was absorbed without touching the shared contract or any other account's folder.
