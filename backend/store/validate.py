"""Event payload validation for the append-only Event_Log.

``validate_event`` is the single gate the Store runs before an :class:`Event`
is persisted or appended. It enforces two things from the written contract in
``shared/api.md`` ("Event kinds"):

1. ``kind`` is one of the permitted values (:data:`ALLOWED_KINDS`).
2. ``payload`` matches the shape required for that ``kind``.

On any problem it raises :class:`ValueError` whose message names the offending
field and the reason, for example ``"kind: unknown kind 'foo'"`` or
``"payload.confidence: must be between 0 and 1"``. Nested Pydantic
``ValidationError``s (from validating an embedded ``Utterance``, ``SourceRef``,
or ``Flag``) are converted into a flat ``ValueError`` that names the nested
field so the Store never leaks a raw Pydantic error to the caller.

This module only imports read-only model definitions from ``shared.schema`` and
never edits shared state. Targets Python 3.11 and Pydantic v2.
"""

from __future__ import annotations

import numbers
from typing import Any

from pydantic import ValidationError

from shared.schema import Event, Flag, SourceRef, Utterance

__all__ = ["ALLOWED_KINDS", "validate_event"]


# The permitted ``Event.kind`` values. ``log.py`` reuses this constant so the
# allowed set has one definition. Keep it a plain ``set`` as the task requires.
ALLOWED_KINDS: set[str] = {
    "utterance",
    "fact",
    "flag_raised",
    "flag_relayed",
    "flag_acked",
    "field_confirmed",
}


def _format_nested(field: str, exc: ValidationError) -> str:
    """Flatten a Pydantic ``ValidationError`` into a ``field: reason`` message.

    The nested model's own field location (e.g. ``quote``) is appended to the
    payload field prefix (e.g. ``payload.source``) so the final message names
    the offending nested field, like
    ``payload.source.quote: String should have at least 1 character``.
    """
    errors = exc.errors()
    if not errors:
        return f"{field}: invalid value"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ()))
    reason = first.get("msg", "invalid value")
    where = f"{field}.{loc}" if loc else field
    return f"{where}: {reason}"


def _require_mapping(payload: Any) -> dict:
    """Return ``payload`` as a dict or raise naming ``payload``."""
    if not isinstance(payload, dict):
        raise ValueError(
            f"payload: must be an object for this kind, got "
            f"{type(payload).__name__}"
        )
    return payload


def _check_exact_keys(payload: dict, allowed: set[str], required: set[str]) -> None:
    """Reject unknown keys and missing required keys, naming the field."""
    unknown = set(payload) - allowed
    if unknown:
        name = sorted(unknown)[0]
        raise ValueError(f"payload.{name}: unexpected field for this kind")
    missing = required - set(payload)
    if missing:
        name = sorted(missing)[0]
        raise ValueError(f"payload.{name}: missing required field")


def _require_non_empty_str(payload: dict, key: str) -> None:
    """Require ``payload[key]`` to be a non-empty string, naming the field."""
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(
            f"payload.{key}: must be a string, got {type(value).__name__}"
        )
    if not value:
        raise ValueError(f"payload.{key}: must not be empty")


def _validate_utterance(payload: dict) -> None:
    """utterance: ``{"utterance": <Utterance-shaped dict>}``."""
    _check_exact_keys(payload, allowed={"utterance"}, required={"utterance"})
    raw = payload["utterance"]
    if not isinstance(raw, dict):
        raise ValueError(
            f"payload.utterance: must be an object, got {type(raw).__name__}"
        )
    try:
        Utterance.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(_format_nested("payload.utterance", exc)) from exc


def _validate_fact(payload: dict) -> None:
    """fact: ``{"path": str, "value": any, "source": SourceRef, "confidence": 0..1}``.

    ``value`` may be any JSON value including ``null``; the contract only
    requires the key to be present.
    """
    _check_exact_keys(
        payload,
        allowed={"path", "value", "source", "confidence"},
        required={"path", "value", "source", "confidence"},
    )

    _require_non_empty_str(payload, "path")

    source = payload["source"]
    if not isinstance(source, dict):
        raise ValueError(
            f"payload.source: must be an object, got {type(source).__name__}"
        )
    try:
        SourceRef.model_validate(source)
    except ValidationError as exc:
        raise ValueError(_format_nested("payload.source", exc)) from exc

    confidence = payload["confidence"]
    # ``bool`` is a subclass of ``int``; reject it so a flag isn't read as 0/1.
    if isinstance(confidence, bool) or not isinstance(confidence, numbers.Real):
        raise ValueError(
            f"payload.confidence: must be a number, got "
            f"{type(confidence).__name__}"
        )
    numeric = float(confidence)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise ValueError("payload.confidence: must be a finite number")
    if not 0.0 <= numeric <= 1.0:
        raise ValueError("payload.confidence: must be between 0 and 1")


def _validate_flag_raised(payload: dict) -> None:
    """flag_raised: ``{"flag": <Flag-shaped dict>}``."""
    _check_exact_keys(payload, allowed={"flag"}, required={"flag"})
    raw = payload["flag"]
    if not isinstance(raw, dict):
        raise ValueError(
            f"payload.flag: must be an object, got {type(raw).__name__}"
        )
    try:
        Flag.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(_format_nested("payload.flag", exc)) from exc


def _validate_flag_id_payload(payload: dict) -> None:
    """flag_relayed / flag_acked: ``{"flag_id": non-empty str}``."""
    _check_exact_keys(payload, allowed={"flag_id"}, required={"flag_id"})
    _require_non_empty_str(payload, "flag_id")


def _validate_field_confirmed(payload: dict) -> None:
    """field_confirmed: ``{"path": non-empty str}``."""
    _check_exact_keys(payload, allowed={"path"}, required={"path"})
    _require_non_empty_str(payload, "path")


# Dispatch table from kind -> payload validator. Keyed only on members of
# ``ALLOWED_KINDS`` so an unknown kind is caught before dispatch.
_PAYLOAD_VALIDATORS = {
    "utterance": _validate_utterance,
    "fact": _validate_fact,
    "flag_raised": _validate_flag_raised,
    "flag_relayed": _validate_flag_id_payload,
    "flag_acked": _validate_flag_id_payload,
    "field_confirmed": _validate_field_confirmed,
}


def validate_event(event: Event) -> None:
    """Validate an :class:`Event`'s ``kind`` and ``payload`` shape.

    Returns ``None`` when the event is valid. Raises :class:`ValueError` whose
    message names the offending field and the reason when the ``kind`` is not
    in :data:`ALLOWED_KINDS` or the ``payload`` does not match that kind's
    required shape.
    """
    if event.kind not in ALLOWED_KINDS:
        raise ValueError(f"kind: unknown kind {event.kind!r}")

    payload = _require_mapping(event.payload)
    _PAYLOAD_VALIDATORS[event.kind](payload)
