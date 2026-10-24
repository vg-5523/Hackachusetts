"""Deterministic medication rules: duplicate_dose, allergy_conflict, interaction.

Each function is pure: given a :class:`~shared.schema.PatientRecord` it returns a
list of :class:`~backend.safety.hit.Hit`. Drug names are compared after RxNorm
normalization so spellings of the same drug collapse together; interactions and
allergy classes come from the curated ``rules.json``.
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations
from pathlib import Path

from shared.schema import FlagSeverity, FlagType, PatientRecord, Sourced

from . import rules_data
from .config import DUPLICATE_WINDOW_MINUTES
from .hit import Hit
from .normalize import normalize


def _med_quotes(med: Sourced) -> list[str]:
    """Verbatim source quotes backing one administered medication."""
    return [s.quote for s in med.sources]


def _med_ts(med: Sourced) -> datetime | None:
    """Best-effort administration timestamp for a medication.

    Prefers the ``Medication.time`` field when it parses as an ISO 8601 string,
    otherwise falls back to the timestamp of the medication's first source.
    """
    value = med.value
    if value is not None and value.time:
        try:
            return datetime.fromisoformat(value.time)
        except ValueError:
            pass
    if med.sources:
        return med.sources[0].ts
    return None


def duplicate_dose(
    record: PatientRecord, cache_dir: Path | None = None
) -> list[Hit]:
    """One hit per drug administered two or more times within the window."""
    by_drug: dict[str, list[Sourced]] = {}
    for med in record.meds_given:
        if med.value is None or not med.value.drug:
            continue
        key = normalize(med.value.drug, cache_dir)
        by_drug.setdefault(key, []).append(med)

    hits: list[Hit] = []
    window = DUPLICATE_WINDOW_MINUTES * 60
    for key, meds in by_drug.items():
        if len(meds) < 2:
            continue
        # Find at least one pair within the configurable window. Missing
        # timestamps are treated as within-window (a duplicate we cannot rule
        # out), which is the safety-conservative choice.
        duplicate = False
        for a, b in combinations(meds, 2):
            ta, tb = _med_ts(a), _med_ts(b)
            if ta is None or tb is None:
                duplicate = True
                break
            if abs((ta - tb).total_seconds()) <= window:
                duplicate = True
                break
        if not duplicate:
            continue

        drug_name = meds[0].value.drug
        evidence: list[str] = []
        for med in meds:
            evidence.extend(_med_quotes(med))
        hits.append(
            Hit(
                type=FlagType.duplicate_dose,
                severity=FlagSeverity.warn,
                rule_key=f"duplicate:{key}",
                message=(
                    f"{drug_name} appears to have been administered "
                    f"{len(meds)} times within {DUPLICATE_WINDOW_MINUTES} "
                    "minutes."
                ),
                citation=rules_data.citation("duplicate_dose"),
                evidence=evidence,
            )
        )
    return hits


def _allergy_terms(record: PatientRecord, cache_dir: Path | None) -> set[str]:
    """Normalized set of every listed allergy plus its class members."""
    classes = rules_data.classes()
    terms: set[str] = set()
    for allergy in record.allergies.value or []:
        if not allergy:
            continue
        name = allergy.strip().lower()
        terms.add(normalize(name, cache_dir))
        terms.add(name)
        # Class cross-reactivity: if the allergy names a class, every member of
        # that class is also an allergy conflict.
        for members in classes.values():
            if name in (m.lower() for m in members):
                for member in members:
                    terms.add(member.lower())
                    terms.add(normalize(member, cache_dir))
    return {t for t in terms if t}


def allergy_conflict(
    record: PatientRecord, cache_dir: Path | None = None
) -> list[Hit]:
    """One hit per given drug that matches a listed allergy (incl. class)."""
    allergy_terms = _allergy_terms(record, cache_dir)
    if not allergy_terms:
        return []
    allergy_quotes = [s.quote for s in record.allergies.sources]

    hits: list[Hit] = []
    seen: set[str] = set()
    for med in record.meds_given:
        if med.value is None or not med.value.drug:
            continue
        drug_name = med.value.drug.strip().lower()
        drug_key = normalize(med.value.drug, cache_dir)
        if drug_name not in allergy_terms and drug_key not in allergy_terms:
            continue
        if drug_key in seen:
            continue
        seen.add(drug_key)
        evidence = allergy_quotes + _med_quotes(med)
        hits.append(
            Hit(
                type=FlagType.allergy_conflict,
                severity=FlagSeverity.critical,
                rule_key=f"allergy:{drug_key}",
                message=(
                    f"{med.value.drug} was given but conflicts with a listed "
                    "allergy (including drug-class cross-reactivity)."
                ),
                citation=rules_data.citation("allergy_cross_reactivity"),
                evidence=evidence,
            )
        )
    return hits


def interaction(
    record: PatientRecord, cache_dir: Path | None = None
) -> list[Hit]:
    """One hit per unordered pair of given drugs matching a curated rule."""
    given: dict[str, Sourced] = {}
    for med in record.meds_given:
        if med.value is None or not med.value.drug:
            continue
        key = normalize(med.value.drug, cache_dir)
        given.setdefault(key, med)
        # Also index by lowercased name so name-based rules still match.
        given.setdefault(med.value.drug.strip().lower(), med)

    rules = rules_data.interactions()
    hits: list[Hit] = []
    for rule in rules:
        # The rule matches only if every drug it names is present, either by its
        # normalized rxcui or by its lowercased name.
        matched_meds: list[Sourced] = []
        present = True
        for drug in rule["drugs"]:
            dk = normalize(drug, cache_dir)
            nk = drug.strip().lower()
            med = given.get(dk) or given.get(nk)
            if med is None:
                present = False
                break
            matched_meds.append(med)
        if not present:
            continue
        evidence: list[str] = []
        for med in matched_meds:
            evidence.extend(_med_quotes(med))
        hits.append(
            Hit(
                type=FlagType.interaction,
                severity=FlagSeverity(rule["severity"]),
                rule_key=rule["rule_key"],
                message=rule["message"],
                citation=rules_data.citation(rule["citation"]),
                evidence=evidence,
            )
        )
    return hits
