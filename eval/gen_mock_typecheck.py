"""Generate eval/mock_typecheck.ts from shared/mock_record.json.

This is a contract check: it proves that shared/mock_record.json is
assignable to the hand-written TypeScript types in shared/types.ts
(PatientRecord and Flag[]). If the mock drifts from the TS contract
(wrong field name, bad enum value, wrong nullability), the generated
file fails to type-check.

Why embed the JSON inline instead of importing it?
  A plain `import mock from "./mock_record.json"` widens every string
  to the general `string` type, so the enum / string-literal-union
  fields (e.g. FieldStatus "confirmed" | "unverified" | ...) would
  type-check even when the mock holds an invalid value. Emitting the
  data as inline object literals assigned to an explicitly typed
  `const` forces TypeScript to check each literal against the exact
  union, which is the whole point of this check.

Usage:
    python eval/gen_mock_typecheck.py

    Writes eval/mock_typecheck.ts.

The generated file is type-checked (never emitted) with the TypeScript
compiler that ships in frontend/ (frontend owns the TS toolchain):

    frontend/node_modules/.bin/tsc --noEmit -p eval/tsconfig.mock.json

(on Windows: frontend\\node_modules\\.bin\\tsc.cmd --noEmit -p eval\\tsconfig.mock.json)

Run `npm install` in frontend/ first so the compiler is present.
"""

from __future__ import annotations

import json
from pathlib import Path

# eval/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_PATH = REPO_ROOT / "shared" / "mock_record.json"
OUT_PATH = REPO_ROOT / "eval" / "mock_typecheck.ts"


def _ts_literal(value: object, indent: int = 0) -> str:
    """Render a JSON-decoded Python value as a TypeScript literal.

    json.dumps already produces valid TypeScript for objects, arrays,
    strings, numbers, booleans, and null, so we lean on it and only
    control the indentation so the output reads cleanly.
    """
    pad = "  " * indent
    text = json.dumps(value, indent=2, ensure_ascii=False)
    # Re-indent every line after the first to sit under `pad`.
    lines = text.splitlines()
    if len(lines) == 1:
        return lines[0]
    reindented = [lines[0]] + [pad + line for line in lines[1:]]
    return "\n".join(reindented)


def generate(mock: dict) -> str:
    if "record" not in mock or "flags" not in mock:
        raise ValueError(
            'mock_record.json must have the shape {"record": ..., "flags": [...]}'
        )

    record_literal = _ts_literal(mock["record"], indent=0)
    flags_literal = _ts_literal(mock["flags"], indent=0)

    return f"""// GENERATED FILE - DO NOT EDIT BY HAND.
// Regenerate with: python eval/gen_mock_typecheck.py
//
// This file exists solely to type-check shared/mock_record.json against
// the hand-written contract in shared/types.ts. The JSON is embedded
// inline (not imported) so string-literal-union / enum fields are checked
// against their exact types instead of being widened to `string`.
//
// Type-check (never emits) with the compiler in frontend/:
//   frontend/node_modules/.bin/tsc --noEmit -p eval/tsconfig.mock.json
import type {{ PatientRecord, Flag }} from "../shared/types";

const record: PatientRecord = {record_literal};

const flags: Flag[] = {flags_literal};

// Reference the bindings so `noUnusedLocals` does not reject them.
void record;
void flags;
"""


def main() -> None:
    mock = json.loads(MOCK_PATH.read_text(encoding="utf-8"))
    OUT_PATH.write_text(generate(mock), encoding="utf-8")
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
