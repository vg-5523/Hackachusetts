"""Optional property-based tests for the pure extraction logic.

Feature: extraction. These cover Properties 1-9 from the design (parse, verify,
and apply). The cache round-trip (Property 10) is exercised by the example
suite; these tests stay pure and make no LLM call.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.extraction.apply import apply_proposals
from backend.extraction.parse import Proposal, parse_response
from backend.extraction.verify import verify
from backend.extraction.prompt import EXTRACTABLE_PATHS
from shared.schema import FieldStatus, PatientRecord, Utterance

_TS = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)
_SCALARS = ["age", "sex", "chief_complaint", "suspected_condition", "eta"]


def _utt(text: str) -> Utterance:
    return Utterance(id="u1", text=text or "x", ts=_TS)


# -- Property 4: non-conforming output yields no facts ----------------------
@settings(max_examples=100)
@given(st.text())
def test_property_4_garbage_parses_to_empty(text):
    """Feature: extraction, Property 4: Non-conforming output yields no facts."""
    result = parse_response(text)
    # Either it happened to contain a valid {"facts": [...]} object, or [].
    assert isinstance(result, list)
    if "{" not in text:
        assert result == []


@settings(max_examples=100)
@given(st.text())
def test_property_4_non_object_is_empty(payload):
    """A JSON value that is not an object with a facts list yields []."""
    assert parse_response(json.dumps(payload)) == []


# -- Property 5: only verified substring quotes survive ---------------------
@settings(max_examples=100)
@given(
    text=st.text(min_size=1, max_size=40),
    quote=st.text(max_size=20),
    path=st.sampled_from(list(EXTRACTABLE_PATHS) + ["bogus_path"]),
)
def test_property_5_verify_substring_and_path(text, quote, path):
    """Feature: extraction, Property 5: Only verified substring quotes survive."""
    prop = Proposal(path=path, value="v", quote=quote, confidence=0.5)
    kept = verify([prop], _utt(text))
    should_keep = bool(quote) and quote in text and path in EXTRACTABLE_PATHS
    assert (len(kept) == 1) == should_keep


# -- Property 6: input record is never mutated ------------------------------
@settings(max_examples=100)
@given(
    path=st.sampled_from(_SCALARS),
    frag=st.text(min_size=1, max_size=10),
)
def test_property_6_input_not_mutated(path, frag):
    """Feature: extraction, Property 6: Input record is never mutated."""
    text = f"prefix {frag} suffix"
    rec = PatientRecord()
    before = rec.model_dump_json()
    prop = Proposal(path=path, value=frag, quote=frag, confidence=0.5)
    out = apply_proposals(rec, [prop], _utt(text))
    assert rec.model_dump_json() == before
    assert out is not rec


# -- Property 1: provenance on every applied field --------------------------
@settings(max_examples=100)
@given(path=st.sampled_from(_SCALARS), frag=st.text(min_size=1, max_size=10))
def test_property_1_provenance(path, frag):
    """Feature: extraction, Property 1: Provenance on every applied field."""
    text = f"xx {frag} yy"
    prop = Proposal(path=path, value=frag, quote=frag, confidence=0.7)
    out = apply_proposals(PatientRecord(), [prop], _utt(text))
    field = getattr(out, path)
    assert len(field.sources) == 1
    src = field.sources[0]
    assert src.quote in text
    assert src.utterance_id == "u1"
    assert src.ts == _TS


# -- Property 3: acuity_esi stays within 1..5 -------------------------------
@settings(max_examples=100)
@given(value=st.integers(min_value=-20, max_value=20))
def test_property_3_acuity_range(value):
    """Feature: extraction, Property 3: acuity_esi stays within 1..5."""
    text = "ESI set here"
    prop = Proposal(path="acuity_esi", value=value, quote="ESI set", confidence=0.5)
    out = apply_proposals(PatientRecord(), [prop], _utt(text))
    if 1 <= value <= 5:
        assert out.acuity_esi.value == value
    else:
        assert out.acuity_esi.value is None


# -- Property 8 + 9: never conflicted; hedged -> unverified, no more confident
@settings(max_examples=100)
@given(
    path=st.sampled_from(_SCALARS),
    frag=st.text(min_size=1, max_size=10),
    conf=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_8_9_status_and_confidence(path, frag, conf):
    """Feature: extraction, Property 8: Status never conflicted;
    Property 9: Hedged facts unverified and no more confident."""
    text = f"aa {frag} bb"
    hedged = Proposal(path=path, value=frag, quote=frag, confidence=conf, hedged=True)
    plain = Proposal(path=path, value=frag, quote=frag, confidence=conf, hedged=False)

    out_h = apply_proposals(PatientRecord(), [hedged], _utt(text))
    out_p = apply_proposals(PatientRecord(), [plain], _utt(text))

    fh = getattr(out_h, path)
    fp = getattr(out_p, path)
    assert fh.status == FieldStatus.unverified
    assert fp.status == FieldStatus.confirmed
    assert fh.status != FieldStatus.conflicted and fp.status != FieldStatus.conflicted
    assert fh.confidence <= fp.confidence


# -- Property 7: differing values append, prior sources remain --------------
@settings(max_examples=100)
@given(a=st.text(min_size=1, max_size=8), b=st.text(min_size=1, max_size=8))
def test_property_7_prior_sources_remain(a, b):
    """Feature: extraction, Property 7: Differing values append, prior sources
    remain."""
    rec = PatientRecord()
    out1 = apply_proposals(
        rec,
        [Proposal(path="age", value=a, quote=a, confidence=0.6)],
        Utterance(id="u1", text=f"q {a} r", ts=_TS),
    )
    out2 = apply_proposals(
        out1,
        [Proposal(path="age", value=b, quote=b, confidence=0.6)],
        Utterance(id="u2", text=f"q {b} r", ts=_TS),
    )
    # The first utterance's source is still present after the second apply.
    assert any(s.utterance_id == "u1" for s in out2.age.sources)
