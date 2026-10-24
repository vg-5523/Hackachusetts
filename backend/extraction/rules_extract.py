"""Deterministic, LLM-free fallback extractor.

``rules_extract(utterance)`` returns a list of :class:`Proposal` using regex and
keyword matching only. Every proposal carries an exact quote that is a substring
of ``utterance.text`` and is marked ``hedged=True`` so that, once applied, every
fact it produces has status ``unverified`` (these are best-effort guesses, not
model- or human-confirmed facts).

Drug names come from ``backend/safety/rules.json`` when that file exists (it is
owned by another contributor and may be absent); otherwise an embedded default
list is used. The returned proposals are fed through the same ``verify`` /
``apply_proposals`` path as the LLM proposals.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from shared.schema import Utterance

from .parse import Proposal

# backend/safety/rules.json, if present. Owned by another contributor.
_SAFETY_RULES = (
    Path(__file__).resolve().parent.parent / "safety" / "rules.json"
)

# Embedded fallback drug list, used when backend/safety/rules.json is absent.
_DEFAULT_DRUGS = (
    "aspirin",
    "nitroglycerin",
    "nitro",
    "glyceryl trinitrate",
    "gtn",
    "morphine",
    "fentanyl",
    "heparin",
    "ticagrelor",
    "clopidogrel",
    "adrenaline",
    "epinephrine",
    "amiodarone",
    "atropine",
    "naloxone",
    "ondansetron",
    "paracetamol",
    "oxygen",
    "metoprolol",
    "furosemide",
    "salbutamol",
)

# Chief-complaint keyword -> canonical value.
_COMPLAINTS = (
    ("chest pain", "chest pain"),
    ("chest tightness", "chest pain"),
    ("stroke", "stroke symptoms"),
    ("facial droop", "stroke symptoms"),
    ("slurred speech", "stroke symptoms"),
    ("weakness on one side", "stroke symptoms"),
    ("overdose", "overdose"),
    ("od", "overdose"),
)

_ROUTES = {
    "po": "PO",
    "oral": "PO",
    "by mouth": "PO",
    "iv": "IV",
    "intravenous": "IV",
    "im": "IM",
    "intramuscular": "IM",
    "sl": "SL",
    "sublingual": "SL",
    "subcut": "SC",
    "sc": "SC",
    "neb": "NEB",
    "nebulised": "NEB",
    "nebulized": "NEB",
}


def _drug_list() -> tuple[str, ...]:
    """Return the drug names, preferring backend/safety/rules.json if present."""
    try:
        raw = _SAFETY_RULES.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return _DEFAULT_DRUGS
    names: list[str] = []
    # Accept a few plausible shapes: {"drugs": [...]}, {"medications": [...]},
    # a bare list, or {"interactions": {...}} keyed by drug name.
    if isinstance(data, dict):
        for key in ("drugs", "medications", "meds"):
            value = data.get(key)
            if isinstance(value, list):
                names.extend(str(x) for x in value if isinstance(x, str))
        for key in ("interactions", "allergies", "rules"):
            value = data.get(key)
            if isinstance(value, dict):
                names.extend(str(k) for k in value)
    elif isinstance(data, list):
        names.extend(str(x) for x in data if isinstance(x, str))
    names = [n.strip().lower() for n in names if n and n.strip()]
    return tuple(dict.fromkeys(names)) if names else _DEFAULT_DRUGS


def _mk(path: str, value, quote: str, confidence: float = 0.4) -> Proposal:
    """Build an unverified fallback proposal (hedged=True -> unverified)."""
    return Proposal(path=path, value=value, quote=quote, confidence=confidence, hedged=True)


def _find(pattern: str, text: str) -> re.Match | None:
    return re.search(pattern, text, flags=re.IGNORECASE)


def rules_extract(utterance: Utterance) -> list[Proposal]:
    """Extract proposals from ``utterance`` using regex/keyword rules only."""
    text = utterance.text
    out: list[Proposal] = []

    _extract_age(text, out)
    _extract_sex(text, out)
    _extract_complaint(text, out)
    _extract_allergies(text, out)
    _extract_meds(text, out)
    _extract_vitals(text, out)
    _extract_eta(text, out)

    # Keep only proposals whose quote is actually a substring of the text.
    return [p for p in out if p.quote and p.quote in text]


def _extract_age(text: str, out: list[Proposal]) -> None:
    m = _find(r"\b(\d{1,3})[- ]?(?:years?[- ]old|y/?o|yo)\b", text)
    if m:
        out.append(_mk("age", m.group(1), m.group(0)))


def _extract_sex(text: str, out: list[Proposal]) -> None:
    m = _find(r"\b(male|female|man|woman|boy|girl)\b", text)
    if m:
        word = m.group(1).lower()
        value = "male" if word in ("male", "man", "boy") else "female"
        out.append(_mk("sex", value, m.group(0)))


def _extract_complaint(text: str, out: list[Proposal]) -> None:
    lowered = text.lower()
    for needle, value in _COMPLAINTS:
        idx = lowered.find(needle)
        if idx != -1:
            out.append(_mk("chief_complaint", value, text[idx : idx + len(needle)]))
            return


def _extract_allergies(text: str, out: list[Proposal]) -> None:
    m = _find(r"\bno known (?:drug )?allergies\b|\bno allergies\b|\bnka\b", text)
    if m:
        out.append(_mk("allergies", "none", m.group(0)))
    # "<drug> allergy" / "allergic to <drug>" / "<drug> allergy bracelet"
    for m in re.finditer(
        r"\ballergic to (\w+)\b|\b(\w+) allergy(?: bracelet)?\b", text, flags=re.IGNORECASE
    ):
        drug = (m.group(1) or m.group(2) or "").strip()
        if drug and drug.lower() not in ("no", "known", "drug"):
            out.append(_mk("allergies", drug.lower(), m.group(0)))


def _extract_meds(text: str, out: list[Proposal]) -> None:
    lowered = text.lower()
    drugs = _drug_list()
    # Where every drug mention starts, so one drug's dose/route window does not
    # bleed into the next drug mention.
    drug_starts = sorted(
        {m.start() for d in drugs for m in re.finditer(re.escape(d), lowered)}
    )
    seen: set[int] = set()
    for drug in drugs:
        for m in re.finditer(re.escape(drug), lowered):
            idx = m.start()
            if idx in seen:
                continue  # a longer drug name already claimed this position
            seen.add(idx)
            drug_end = idx + len(drug)
            next_drug = next((s for s in drug_starts if s > idx), len(text))
            window_end = min(len(text), idx + len(drug) + 30, next_drug)
            window = text[idx:window_end]
            # Stop at a conjunction so "GTN ... and morphine 5mg" keeps 5mg off GTN.
            conj = re.search(r"\b(?:and|then|plus)\b|[,;]", window, re.IGNORECASE)
            if conj:
                window = window[: conj.start()]
            dose_m = re.search(
                r"\b(\d+(?:\.\d+)?\s?(?:mg|mcg|g|units?|ml))\b", window, re.IGNORECASE
            )
            route = None
            for token, canonical in _ROUTES.items():
                if re.search(rf"\b{re.escape(token)}\b", window, re.IGNORECASE):
                    route = canonical
                    break
            med: dict[str, str] = {"drug": drug}
            if dose_m:
                med["dose"] = dose_m.group(1)
            if route:
                med["route"] = route
            end = drug_end
            if dose_m:
                end = max(end, idx + dose_m.end())
            quote = text[idx:end]
            out.append(_mk("meds_given", med, quote))


def _extract_vitals(text: str, out: list[Proposal]) -> None:
    vitals: dict[str, object] = {}
    quotes: list[str] = []

    m = _find(r"\b(?:hr|heart rate|pulse)\s*(?:is|of|=|:)?\s*(\d{1,3})\b", text)
    if m:
        vitals["hr"] = int(m.group(1))
        quotes.append(m.group(0))
    m = _find(r"\b(?:bp|blood pressure)\s*(?:is|of|=|:)?\s*(\d{2,3}/\d{2,3})\b", text)
    if m:
        vitals["bp"] = m.group(1)
        quotes.append(m.group(0))
    m = _find(r"\b(?:spo2|sats?|o2 sats?|oxygen saturation)\s*(?:is|of|=|:|at)?\s*(\d{1,3})\s*%?", text)
    if m:
        vitals["spo2"] = int(m.group(1))
        quotes.append(m.group(0))
    m = _find(r"\b(?:rr|resp rate|respiratory rate)\s*(?:is|of|=|:)?\s*(\d{1,3})\b", text)
    if m:
        vitals["rr"] = int(m.group(1))
        quotes.append(m.group(0))

    if vitals:
        # Quote the first vitals fragment (all are substrings of the text).
        out.append(_mk("vitals_timeline", vitals, quotes[0]))


def _extract_eta(text: str, out: list[Proposal]) -> None:
    m = _find(r"\beta\s*(?:is|of|=|:)?\s*(\d{1,3}\s*(?:min(?:ute)?s?|mins?))\b", text)
    if m:
        out.append(_mk("eta", m.group(1), m.group(0)))
        return
    m = _find(r"\b(\d{1,3}\s*(?:min(?:ute)?s?|mins?))\s*(?:out|away|to (?:the )?(?:ed|hospital))\b", text)
    if m:
        out.append(_mk("eta", m.group(1), m.group(0)))
