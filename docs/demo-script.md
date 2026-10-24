# Demo script — STEMI hero scenario (2:45)

Scenario file: `scenarios/stemi_hero.json`. A 58-year-old male with chest pain. The story: the
record builds from the transcript, the allergy contradiction surfaces when a penicillin bracelet is
found, the duplicate aspirin is caught, a human relays the SAY-TO-CREW line, and an SBAR hand-off is
produced. Target run time 2:45. No third-party logos or trademarks on screen.

> **Build status.** The parts that are real today: the five scenario transcripts in `scenarios/`
> and the deterministic safety engine in `backend/safety/` (`evaluate`), which produces the
> contradiction and duplicate-dose flags described below from a record of this run. The live
> transcript UI, the on-screen flags panel, the Relay button, and the rendered SBAR panel are **not
> built yet** — they are Phase 1 stubs. Every on-screen UI beat below is therefore marked **TODO
> (not built yet)**. Until the UI exists, the demo can be run as a narrated walkthrough of
> `scenarios/stemi_hero.json` plus the safety engine's output for that run.

---

**0:00 – 0:12 — The problem (one sentence)**
- Say: "During a hot ambulance run, a paramedic is talking, treating, and driving all at once, and
  the small things — a contradicted allergy, a double dose — are exactly what gets missed."
- On screen — TODO (not built yet): title card, then an empty record panel with the footer
  disclaimer "decision support, not clinical advice." Until the frontend exists, show the empty
  record shape from `shared/schema.py`.

**0:12 – 0:40 — Live transcript starts building the record**
- Say: "The medic just speaks. Dispatch, 58-year-old male, crushing central chest pain radiating to
  the left arm, started about forty minutes ago."
- Real today: these are the first utterances in `scenarios/stemi_hero.json`.
- On screen — TODO (not built yet): utterances streaming into a transcript and fields filling in
  (age 58, sex male, chief complaint chest pain) each with a source quote and status badge. The
  extraction that produces these fields is still a stub.
- Say: "Every field carries its provenance — the exact words that produced it."

**0:40 – 1:05 — Vitals, allergies, and the STEMI call**
- Say: "First vitals land, the medic reports no known allergies, and the twelve-lead shows ST
  elevation — a STEMI, level one."
- Real today: these utterances are in the scenario (HR 96, BP 150/92, SpO2 94, RR 22; "no known
  allergies"; STEMI; level one).
- On screen — TODO (not built yet): vitals timeline, allergies reading "none", suspected condition
  STEMI, acuity ESI 1.

**1:05 – 1:20 — First aspirin**
- Say: "Aspirin 324, chewed, given."
- Real today: the utterance "Giving 324 aspirin chewed now." is in the scenario.
- On screen — TODO (not built yet): a `meds_given.0` aspirin entry with its quote and timestamp.

**1:20 – 1:45 — The contradiction flag (penicillin bracelet)**
- Say: "Now the correction every handoff dreads — the medic finds a penicillin allergy bracelet,
  after saying no allergies earlier."
- Real today: the safety engine raises a **CONTRADICTION** flag (severity critical) for an allergies
  field whose status is `conflicted`, keeping BOTH source quotes as evidence with a cited source.
  This is what `evaluate` produces for this run; it is the gold flag in
  `scenarios/stemi_hero.gold.json`.
- On screen — TODO (not built yet): the allergies field turning `conflicted` with both quotes shown
  and the flag card rendered.

**1:45 – 2:05 — The duplicate aspirin flag**
- Say: "A few minutes later a second aspirin goes in, phrased completely differently — 'gave him
  another aspirin.' The system still recognizes it as the same drug."
- Real today: the safety engine raises a **DUPLICATE_DOSE** flag (warn) for the two aspirin doses,
  matching them after RxNorm name normalization; also a gold flag in the scenario.
- On screen — TODO (not built yet): two aspirin entries and the duplicate-dose flag card.

**2:05 – 2:25 — SAY TO CREW relay (human in the loop)**
- Say: "The machine never talks to the crew. It hands a short line to a human operator, who decides
  whether to relay it."
- Real today: every flag carries a `say_to_crew` line (the safety engine phrases it via the LLM, or
  falls back to a per-type template). The contract defines the human-only relay path
  (open → relayed → acknowledged) with no crew-facing delivery.
- On screen — TODO (not built yet): the SAY-TO-CREW line with a Relay button and the open → relayed
  transition. The relay/ack endpoints are currently Phase 1 stubs over mock state.

**2:25 – 2:40 — SBAR hand-off**
- Say: "On arrival, the SBAR hand-off is produced from the record — Situation, Background,
  Assessment, Recommendation — with the allergy conflict and the duplicate dose called out."
- On screen — TODO (not built yet): a rendered SBAR panel. SBAR generation (`backend/outputs`) is a
  Phase 1 stub, so there is no real SBAR text yet.

**2:40 – 2:45 — Who benefits and how it scales**
- Say: "Paramedics get a second set of eyes and a hand-off that writes itself; receiving clinicians
  get a traceable record instead of a verbal scramble. The safety engine is rule-based and runs
  offline, so it scales to any run with no change to how the crew already works."
- On screen — TODO (not built yet): the full record + flags + SBAR with the disclaimer in the footer.

---

### Delivery notes
- Until the frontend and outputs are built, run this as a narrated walkthrough: read
  `scenarios/stemi_hero.json` and show the safety engine's flags for a matching record.
- The two beats to land hard: the contradiction keeping BOTH quotes, and the SAY-TO-CREW relay being
  a human decision.
- Keep the disclaimer visible whenever a UI is shown.
- Data is synthetic. No real patient, person, or institution appears.
