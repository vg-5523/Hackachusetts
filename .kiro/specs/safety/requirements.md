# Requirements: Safety engine (`backend/safety/`)

## Introduction

`backend/safety/` (Account B) evaluates a `PatientRecord` and raises deterministic,
cited safety `Flag`s. Rules are the authority; the LLM may only phrase the
`say_to_crew` line. The module must work with no network access. Scope is limited to
`backend/safety/` and its tests; `shared/` is read-only contract.

Drug scope (demo): aspirin, nitroglycerin, morphine, fentanyl, heparin, metoprolol,
sildenafil, ondansetron, naloxone, plus penicillin and amoxicillin for allergy
cross-reactivity.

## Requirements

### R1 Deterministic, rule-based evaluation
- 1.1 `evaluate(record: PatientRecord) -> list[Flag]` returns flags computed only from
  deterministic rules over the record (Phase 1 signature preserved).
- 1.2 The LLM only phrases `say_to_crew`. If `call_llm` is unavailable or fails for any
  reason (including `LLM_API_KEY` unset), a per-type template sentence is used.
- 1.3 Type, severity, and evidence are never influenced by the LLM.

### R2 Interaction source of truth
- 2.1 The RxNav drug-interaction API is treated as retired; it is not relied upon at
  runtime.
- 2.2 Interaction rules come from a curated `backend/safety/rules.json`.
- 2.3 Every rule carries a citation `name` and `url` used as a flag's `source_ref`.

### R3 Checks (each hit → one `Flag`)
- 3.1 `duplicate_dose`: same normalized drug given two or more times within a
  configurable time window (default 60 minutes).
- 3.2 `allergy_conflict`: a given drug matches a listed allergy, including class
  cross-reactivity (penicillin ↔ amoxicillin).
- 3.3 `interaction`: a given pair of drugs matches a curated rule in `rules.json`.
- 3.4 `contradiction`: any Sourced field with status `conflicted` → one `critical` flag.
- 3.5 `missing_info`: a required field still `unknown` (e.g. allergies). Evidence may be
  empty for this type only.

### R4 Flag content
- 4.1 Every flag has `source_ref` (`name`, `url`), `evidence` quotes taken verbatim from
  the record's sources, and a `say_to_crew` of at most 280 non-blank characters.
- 4.2 Flags validate against `shared.schema.Flag` before being returned.

### R5 Idempotent ids
- 5.1 `id = f"{type}:{sha1(type + rule_key + sorted(evidence) joined)[:12]}"`.
- 5.2 Calling `evaluate` twice on the same record returns identical ids and ordering.

### R6 Normalization and offline cache
- 6.1 Drug names normalize via the RxNorm API (`rxcui` lookup, approximate fallback).
- 6.2 Every API response is cached on disk under `backend/safety/cache/`.
- 6.3 The cache is pre-warmed for all demo drugs and committed; with no network the
  module still evaluates correctly from the cache.

### R7 Hero case
- 7.1 Record with allergies first "none" then "penicillin" (status `conflicted`) and
  aspirin given twice yields an `allergy_conflict` or `contradiction` flag plus a
  `duplicate_dose` flag.
