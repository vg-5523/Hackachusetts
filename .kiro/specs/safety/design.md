# Design: Safety engine (`backend/safety/`)

## Overview

Pure, deterministic rule functions produce **hits**, `evaluate` turns each hit into a
validated `Flag`. Only `say_to_crew` touches the LLM, with a template fallback. Drug
names are normalized through an on-disk RxNorm cache so the module runs offline.

```
evaluate(record)
  ├─ normalize(drug) ────► cache (backend/safety/cache/) ─► RxNorm API (miss only)
  ├─ rules_meds:   duplicate_dose, allergy_conflict, interaction(rules.json)
  ├─ rules_record: contradiction, missing_info
  └─ for each hit: flag_id + phrasing(say_to_crew) → Flag (schema-validated)
```

## Module layout (all under `backend/safety/`)

| File | Responsibility |
|---|---|
| `__init__.py` | Public `evaluate(record) -> list[Flag]`; orchestrates rules, ids, phrasing, validation, stable ordering. |
| `ids.py` | `flag_id(type, rule_key, evidence)` per R5. |
| `normalize.py` | `normalize(name) -> str` RxNorm rxcui via `cache`; approximate fallback; offline-safe. |
| `cache.py` | `cached(kind, key, fetch)` read-through JSON cache under `cache/`; no `fetch` on hit. |
| `rules.json` | Curated interaction rules + drug classes + citations (primary source). |
| `rules_meds.py` | `duplicate_dose`, `allergy_conflict`, `interaction` hit builders. |
| `rules_record.py` | `contradiction`, `missing_info` hit builders. |
| `phrasing.py` | `say_to_crew(hit) -> str`; LLM via `backend.llm.call_llm`, else template. |
| `config.py` | Tunables: `DUPLICATE_WINDOW_MINUTES = 60`, required fields for missing_info. |
| `cache/` | Committed pre-warmed RxNorm responses (one JSON per drug). |

## Hit shape (internal)

A `Hit` dataclass: `type: FlagType`, `severity: FlagSeverity`, `rule_key: str`,
`message: str`, `evidence: list[str]`, `citation: Citation`. `evaluate` maps it to a
`Flag` with `id=flag_id(...)`, `say_to_crew=phrasing(hit)`, `status=open`.

## rules.json shape

```jsonc
{
  "classes": { "penicillin": ["penicillin", "amoxicillin"] },
  "citations": { "<key>": { "name": "...", "url": "https://..." } },
  "interactions": [
    { "rule_key": "nitroglycerin+sildenafil", "drugs": ["nitroglycerin","sildenafil"],
      "severity": "critical", "message": "...", "citation": "nitro_sildenafil" }
  ]
}
```
Interactions are matched on **normalized** rxcui where possible, falling back to the
lowercased drug name, so order of the pair does not matter.

## Normalization & cache

- `normalize(name)` → `cached("rxnorm", name.lower(), fetch_rxcui)`. On hit returns the
  stored rxcui without any network call. `fetch_rxcui` calls
  `rxcui.json?name=&search=1`, then `approximateTerm.json` on an empty result.
- Cache entries are JSON files keyed by a safe slug of `kind` + `key` under `cache/`.
  Pre-warmed and committed for all 11 demo drugs. Confirmed at design time: the RxNav
  interaction endpoint returns 404 (retired); the RxNorm rxcui endpoint works
  (aspirin → 1191).

## Rules

- **duplicate_dose**: group `meds_given` by normalized drug; if two doses fall within
  `DUPLICATE_WINDOW_MINUTES` (parsed from each med's `time`/source ts), emit one hit per
  group, evidence = the two source quotes. `warn`.
- **allergy_conflict**: for each given drug, if its normalized name or its class matches
  any listed allergy, emit a hit. `critical`. Evidence = allergy source + med source.
- **interaction**: for each unordered pair of given drugs, look up `rules.json`
  interactions; emit a hit with the rule's severity/citation.
- **contradiction**: one hit per Sourced field whose `status == conflicted`; all that
  field's source quotes as evidence. `critical`.
- **missing_info**: one hit per required field still `unknown`; evidence may be `[]`.
  `info`.

## say_to_crew phrasing

`phrasing(hit)` builds a prompt from `hit.message` + evidence and calls
`backend.llm.call_llm`. Accept the reply only if it is 1–280 non-blank chars; otherwise
fall back to a deterministic per-type template. Any exception → template. The result is
truncated defensively to 280 chars. Type/severity/evidence are untouched.

## Ordering & idempotency

`evaluate` sorts flags by `(type value, id)` for a stable deterministic order. Ids are a
pure function of type + rule_key + sorted evidence, so repeated calls are identical.

## Testing (`backend/safety/tests/`)

- `test_ids.py`: determinism, evidence-order independence, length ≤ 64.
- `test_cache.py`: hit never calls `fetch`; miss writes; offline read works.
- `test_evaluate.py`: hero case → `duplicate_dose` + (`allergy_conflict` or
  `contradiction`); repeated calls identical ids; `LLM_API_KEY` unset → template;
  all flags schema-valid. No network in tests.
