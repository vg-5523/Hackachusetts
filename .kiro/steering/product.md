# Product

Ambulance Scribe + Safety Check. This steering file describes what the product
is and the non-negotiable product rules every contributor and AI agent must
follow.

## Purpose

Ambulance Scribe + Safety Check listens to a paramedic speaking or typing during
an ambulance run and builds a structured patient record in real time. A safety
engine watches that record for duplicate doses, allergy conflicts, drug
interactions, contradictions, and missing information, and it produces an SBAR
handoff, an ED pre-alert, and a bed/resus checklist. The goal is to reduce the
clinician's cognitive load during a high-pressure run, not to make clinical
decisions for the crew.

## Provenance on Every Field

Every value in the patient record carries its provenance. Each field is a
`Sourced` value (defined in `shared/schema.py`) that wraps the value with:

- the source quote taken verbatim from an utterance,
- the timestamp of that utterance, and
- a status: `confirmed`, `unverified`, `conflicted`, or `unknown`.

No field is ever shown without its source. A receiving clinician must always be
able to trace a value back to the exact words that produced it. Code that sets a
field value without attaching at least one source is a contract violation.

## The AI Never Talks to Paramedics Directly

This is the core safety principle. The AI does not instruct, direct, or speak to
the paramedic crew. It only surfaces decision support to a human operator. No
part of the system sends text, audio, or push notifications to a paramedic or to
any crew-facing device or channel. Alerts reach the crew only through a human who
chooses to relay them.

## The `say_to_crew` Relay Mechanism

Each safety flag includes a short `say_to_crew` line (1 to 280 characters). This
line is a suggestion, not a command. The Frontend presents each `say_to_crew`
line to a human operator, who decides whether and how to relay the line to the
crew. The operator is always in the loop:

- A flag starts as `open`.
- When the operator chooses to pass the line along, the flag moves to `relayed`.
- When the crew confirms they heard it, the operator marks the flag `acknowledged`.

The machine never short-circuits this path. The LLM may phrase the line, but it
never decides that the line reaches the crew.

## Synthetic Data Only

This project uses synthetic data only and contains no real patient data. Every
record in every tracked file is fabricated for this project and is not copied
from, derived from, or re-identifiable to any real individual. No real patient,
person, or institution names, identifiers, contact details, or dates of birth
belong anywhere in the repository. If any data cannot be confirmed as fictional,
it must be removed before the next merge.

## Disclaimer

The Frontend displays the disclaimer "decision support, not clinical advice." on
every screen, visible without scrolling or interaction. This product supports the
crew's judgment; it never replaces it. The final clinical decision always rests
with the human clinician.
