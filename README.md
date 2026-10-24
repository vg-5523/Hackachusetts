# Relay — Ambulance Scribe + Safety Check

Relay is a Hackachusetts hackathon prototype that turns spoken or typed ambulance updates into a structured patient record, highlights potential safety concerns, and prepares information for the receiving emergency department (ED).

**Decision support, not clinical advice. Use synthetic data only.** This is a demonstration project, not a clinically validated system.

## What specific problem does it cover?

The project focuses on the **ambulance-to-emergency-department handoff**: the period when a crew is assessing and treating a patient while communicating information under pressure.

Important details can be scattered across radio updates, repeated, corrected, or missed. Relay explores how AI-assisted documentation and human-reviewed safety checks can help an operator keep track of those details before hospital arrival.

Within the hackathon, our scope is prehospital documentation, information consistency, and handoff preparation. The prototype does not diagnose patients, choose treatment, or automatically send instructions to the ambulance crew.

## What we are trying to achieve

- Reduce the effort needed to turn ambulance updates into an organized record.
- Preserve source quotes and timestamps so an operator can review where information came from.
- Make uncertainty and conflicting information visible instead of silently presenting it as fact.
- Surface possible duplicate doses, allergy conflicts, selected drug interactions, contradictions, and missing information.
- Prepare a consistent handoff while keeping a human responsible for reviewing and relaying concerns.

These are design goals. The prototype has not demonstrated improved clinical outcomes or reduced workload in a real ambulance setting.

## Team and roles

The table combines the original account-based responsibilities with the team's implementation contributions. Vrishin also carried out broad implementation and integration across the project, beyond the Account D responsibilities.

| Team member | Role | Responsibilities |
|---|---|---|
| **Vrishin Gera — Account D** | Primary Programmer | Implement and integrate functionality across the application; maintain event logging and replay; generate handoff outputs; build synthetic scenarios and evaluations; troubleshoot and test the end-to-end workflow. Main assigned areas: backend/store/, backend/outputs/, scenarios/, and eval/. |
| **Sai Srinath — Account A** | Extraction and AI integration | Convert utterances into structured patient facts; verify supporting quotes; work on extraction prompts, cached responses, and the rules-based fallback. Main area: backend/extraction/. |
| **Jenil Vyas — Account B** | Safety engine | Build deterministic safety checks, medication-name normalization, curated rules, flag evidence, and suggested relay phrasing. Main area: backend/safety/. |
| **Ruhan Vikram — Account C** | Frontend and operator experience | Build the React dashboard, typed and microphone input, live record updates, evidence views, flag interactions, and output panels. Main area: frontend/. |

Shared Python/TypeScript models, the API contract, backend entrypoint, and LLM wrapper connect the workstreams. Kiro specifications and steering documents live in .kiro/.

## How it works

1. **Capture an update.** Type an utterance, use supported browser speech recognition, or play a synthetic scenario.
2. **Extract information.** Use cached extraction responses, Gemini when configured, or a limited rules-based fallback to populate patient fields, medications, and vital signs.
3. **Keep a traceable record.** Store updates in an event log. Fields can be unknown, unverified, confirmed, or conflicted.
4. **Run safety checks.** Deterministic rules evaluate the record. An LLM can phrase an alert's suggested relay line, but does not decide which safety rule fires.
5. **Review and hand off.** Display the record, flags, and source evidence alongside an SBAR handoff (Situation, Background, Assessment, Recommendation), ED pre-alert, and receiving-team checklist.

The operator decides whether to relay an alert. The app tracks **open → relayed → acknowledged**; it does not deliver alerts directly to the ambulance crew.

## Current capabilities

- Local React dashboard connected to a Python/FastAPI backend with streaming updates.
- Typed input and browser-dependent microphone transcription.
- Patient record extraction, source evidence, confirmation controls, and safety flags.
- Deterministic SBAR, pre-alert, and checklist generation from the current record.
- Persisted event history and scenario replay.
- Five synthetic scenarios: stemi_hero, clean_stemi, stroke, garbled_uncertain, and opioid_overdose.
- Backend unit, integration, and property-based tests. Passing tests cover defined cases; they do not establish clinical accuracy.

## Current limitations

- **Limited safety coverage.** Medication rules are a small curated demonstration set. Several citation links are explicitly synthetic placeholders, not verified clinical references.
- **Extraction can be wrong.** The fallback recognizes limited wording and can miss or misinterpret details. Gemini output and speech transcription can also be wrong. Supporting quotes allow review but do not guarantee correct interpretation.
- **Demo timers need work.** Scenarios use historical timestamps, so elapsed-time displays can show extremely large or negative values rather than useful demo timers.
- **Test history persists.** Restarting the backend retains the prior record. Repeated submissions can accumulate medication entries and conflicting values. Playing a scenario replaces the current demo record; existing false entries are not automatically repaired by code fixes.
- **Single shared record.** The local backend is not a production system for separate patients, crews, or concurrent clinical sessions.
- **Browser and network dependencies.** Microphone support varies by browser and permissions. Uncached Gemini calls require a valid key and network access; medication normalization can also use the network on a cache miss.
- **Production readiness remains open.** Authentication, clinical-system integration, secure deployment, privacy review, and clinical validation remain outside the demonstrated local workflow. Do not enter real patient information.

## Run locally in Kiro on Windows

Prerequisites: Python 3.11, Node.js/npm, and the project open in Kiro. Start in the repository root and use two PowerShell terminals.

**Terminal 1 — backend**

~~~powershell
# Create the environment only if .venv311 does not exist:
# py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:SCRIBE_MODE = "live"
.\.venv311\Scripts\python.exe -m uvicorn backend.main:app --port 8000
~~~

Set SCRIBE_MODE before starting the backend. It defaults to stub mode, which serves mock behavior. Using the environment's Python directly avoids activation and interpreter-selection problems.

**Terminal 2 — frontend**

~~~powershell
cd frontend
npm.cmd install
npm.cmd run dev
~~~

Leave both terminals running and open [http://localhost:5173](http://localhost:5173). Select **Play scenario → stemi_hero** for a fresh synthetic demo. If it is already selected, select another scenario and then select it again. Press **Ctrl+C** in each terminal to stop the servers.

Gemini is optional: copy .env.example to a root .env and set LLM_API_KEY to enable it. Never commit the key. Cached or rules-based extraction can work without Gemini; a successful scenario replay alone does not prove a live Gemini call occurred.

## Tests

From the repository root, with the backend stopped, temporarily set aside any root .env and clear LLM_API_KEY in the test terminal so local credentials cannot enable Gemini calls. Restore your .env after testing.

~~~powershell
$env:LLM_API_KEY = ""
.\.venv311\Scripts\python.exe -m pytest backend eval -q
~~~

Frontend tests are available separately:

~~~powershell
cd frontend
npm.cmd test
~~~
