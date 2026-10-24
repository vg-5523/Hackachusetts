# CONTRACT_NOTE: how a NEW fact is represented in the returned record

`process_utterance(utterance, record)` returns a NEW `PatientRecord` (input is
never mutated). Every fact it adds for this utterance carries a `SourceRef`
whose `utterance_id == utterance.id`. That is the one rule the store relies on.

## Detection rule (for `store.facts_from(utt, old, new)`)

> A field was changed by this utterance **iff** the returned record has, on that
> field, at least one `SourceRef` with `utterance_id == utt.id`.

The quote on that `SourceRef` is always a substring of `utt.text` (verified
before the fact is applied), so `facts_from` can emit it directly.

## Per-field detail

- **Scalars** (`age`, `sex`, `chief_complaint`, `suspected_condition`, `eta`,
  `acuity_esi`): a `Sourced[...]`. A new fact sets `.value` and appends
  `SourceRef(utt.id, quote, utt.ts)` to `.sources`. New fact ⇔ some source has
  `utterance_id == utt.id`. A differing value is assigned while prior sources
  are kept, so a value change is also visible by comparing `old`/`new` `.value`.

- **`allergies`** (`Sourced[list[str]]`): each new allergy string is appended to
  `.value` (deduped) and a `SourceRef` for this utterance is appended. "no known
  allergies" yields `value == []` (empty list, not null) WITH a source, so that
  empty-list-with-source state is itself a fact. New fact ⇔ a source has
  `utterance_id == utt.id`.

- **`meds_given`** (`list[Sourced[Medication]]`): each administration appends a
  NEW element whose `.sources == [SourceRef(utt.id, ...)]`. Two doses from two
  utterances are two elements with distinct quotes. New fact ⇔ some element has
  a source with `utterance_id == utt.id`; one element per dose.

## Notes

Sources dedupe on `(utterance_id, quote)`, so a repeated identical quote adds
one source but still leaves one with `utterance_id == utt.id`. The rules
fallback marks facts `unverified` but uses the same `apply_proposals` path, so
this rule is identical for it.
