"""Validate ``shared/mock_record.json`` against the shared schema.

This is the Phase 1 contract check for the mock fixture. It loads the mock
file, validates its ``record`` through :class:`shared.schema.PatientRecord` and
each entry of ``flags`` through :class:`shared.schema.Flag`, and reports the
outcome through the process exit code:

* On success it prints ``OK`` and exits ``0``.
* On any validation (or load) error it prints every error in a readable form
  and exits with a non-zero code.

Run it from the repo root either as a script::

    python eval/validate_mock.py

or as a module::

    python -m eval.validate_mock

The repo root is placed on ``sys.path`` (pytest.ini also adds it) so the
``from shared.schema import ...`` import resolves under direct execution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the repo root from this file's location and put it on sys.path so the
# ``shared`` package imports whether the script is run as ``python
# eval/validate_mock.py`` or ``python -m eval.validate_mock`` from the repo
# root. eval/validate_mock.py -> eval/ -> repo root (two parents up).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError  # noqa: E402  (after sys.path setup)

from shared.schema import Flag, PatientRecord  # noqa: E402

MOCK_PATH = REPO_ROOT / "shared" / "mock_record.json"


def _format_validation_error(label: str, exc: ValidationError) -> list[str]:
    """Render a Pydantic ``ValidationError`` as readable, per-error lines."""
    lines: list[str] = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", ())) or "(root)"
        message = err.get("msg", "invalid value")
        lines.append(f"{label}: {location}: {message}")
    return lines


def validate_mock(mock_path: Path = MOCK_PATH) -> list[str]:
    """Validate the mock file and return a list of readable error strings.

    An empty list means the mock is valid. Load/parse problems and schema
    validation failures are all returned as human-readable strings.
    """
    errors: list[str] = []

    try:
        raw = mock_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read {mock_path}: {exc}"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"{mock_path} is not valid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{mock_path}: top level must be an object with 'record' and 'flags'"]

    if "record" not in data:
        errors.append(f"{mock_path}: missing 'record' key")
    else:
        try:
            PatientRecord.model_validate(data["record"])
        except ValidationError as exc:
            errors.extend(_format_validation_error("record", exc))

    if "flags" not in data:
        errors.append(f"{mock_path}: missing 'flags' key")
    elif not isinstance(data["flags"], list):
        errors.append(f"{mock_path}: 'flags' must be a list")
    else:
        for index, flag in enumerate(data["flags"]):
            try:
                Flag.model_validate(flag)
            except ValidationError as exc:
                errors.extend(_format_validation_error(f"flags[{index}]", exc))

    return errors


def main() -> int:
    """Entry point: print the result and return the process exit code."""
    errors = validate_mock()
    if errors:
        for line in errors:
            print(line)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
