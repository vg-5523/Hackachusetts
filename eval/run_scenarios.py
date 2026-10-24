"""Play every scenario through the real pipeline and score it against gold.

Task 5.1 (store-outputs). This is a *report*, not a gate: it runs the scenario
corpus in ``scenarios/`` through the real Store + extraction + safety pipeline
IN-PROCESS (no uvicorn, no disk writes), scores extraction field-accuracy and
flag precision/recall against each scenario's gold file, prints a table to
stdout, and writes the same table to ``eval/report.md``.

Design notes
------------
- **No disk writes.** We never call ``backend.store.append`` / ``persist.save``.
  Instead we fold events ourselves with a local list and call
  ``backend.store.derive(all_events)`` at the end, mirroring the live pipeline
  in ``backend/main.py`` (utterance event -> fact events -> flag_raised events)
  but keeping everything in memory, so ``backend/store/event_log.json`` is never
  created or touched.
- **Tolerant of a missing corpus.** ``scenarios/`` and individual files may be
  absent (branch b-scenarios has not landed yet). Missing dir -> "no scenarios"
  message + exit 0. Missing/garbled transcript or gold -> a note on that row and
  the run continues.
- **Phase 1 reality.** Extraction and safety are stubs, so field accuracy will
  be ~0 and there are no flags. That is expected; the runner's job is to run and
  report without crashing, and to be correct once real extraction/safety land.

Transcript shapes accepted
---------------------------
- a bare JSON list of ``{"text": ..., "ts": ...}`` objects, or
- an object ``{"id": ..., "utterances": [ {"text": ..., "ts": ...}, ... ]}``.

Each utterance is validated as :class:`UtteranceRequest` (text + aware ts).

Gold shape (tolerant)
---------------------
``{"fields": {dotted_path: expected_value, ...}, "flags": [ "type" | {"type": ...} ]}``
Both keys optional. A missing gold file means the scenario is still played but
scored as "no gold".

Targets Python 3.11.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

# --- Make the repo root importable when run as ``python eval/run_scenarios.py``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.schema import (  # noqa: E402  (after sys.path shim)
    Event,
    PatientRecord,
    Sourced,
    Utterance,
    UtteranceRequest,
)

import backend.extraction as extraction  # noqa: E402
import backend.safety as safety  # noqa: E402
import backend.store as store  # noqa: E402

SCENARIOS_DIR = _REPO_ROOT / "scenarios"
REPORT_PATH = _REPO_ROOT / "eval" / "report.md"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def discover_scenario_ids(scenarios_dir: Path) -> list[str]:
    """Return sorted scenario ids = stems of ``*.json`` minus ``*.gold.json``.

    When ``scenarios_dir`` is missing (or is not a directory) returns ``[]`` so
    the caller can print the "no scenarios" message and exit cleanly.
    """
    if not scenarios_dir.is_dir():
        return []
    ids: list[str] = []
    for path in sorted(scenarios_dir.glob("*.json")):
        name = path.name
        if name.endswith(".gold.json"):
            continue
        ids.append(path.stem)
    return ids


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_transcript(path: Path) -> list[UtteranceRequest]:
    """Load + validate a transcript file into a list of ``UtteranceRequest``.

    Accepts a bare list of utterance objects or an object with an
    ``"utterances"`` list. Raises ``ValueError`` (wrapping the underlying cause)
    on any malformed input so the caller can record a parse-error row.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        items = raw.get("utterances")
        if items is None:
            raise ValueError("object transcript has no 'utterances' list")
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(f"transcript must be a list or object, got {type(raw).__name__}")

    if not isinstance(items, list):
        raise ValueError("'utterances' must be a list")

    requests: list[UtteranceRequest] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"utterance #{i} is not an object")
        try:
            requests.append(UtteranceRequest.model_validate(item))
        except Exception as exc:  # noqa: BLE001 - re-raise as a clean ValueError
            raise ValueError(f"utterance #{i} invalid: {exc}") from exc
    return requests


def load_gold(path: Path) -> dict[str, Any] | None:
    """Load a gold file if present; return ``None`` when absent.

    Raises ``ValueError`` on a malformed gold file so the caller can note it.
    """
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gold file must be a JSON object")
    return raw


# ---------------------------------------------------------------------------
# Playing (pure, in-memory; mirrors backend/main.py but writes no disk)
# ---------------------------------------------------------------------------
def play_scenario(
    scenario_id: str, utterances: list[UtteranceRequest]
) -> tuple[PatientRecord, list]:
    """Fold a transcript through the real pipeline and derive ``(record, flags)``.

    Pure and in-memory: builds the same event batch the live endpoint would
    (utterance event, then fact events, then one ``flag_raised`` per new flag),
    accumulates them in a local list, and calls :func:`store.derive` once at the
    end. Never calls ``store.append`` / ``persist.save``, so no disk file is
    created or modified.
    """
    all_events: list[Event] = []

    for i, req in enumerate(utterances):
        utt = Utterance(id=f"{scenario_id}-{i}", text=req.text, ts=req.ts)

        # Current derived state from the events accumulated so far.
        old_record, old_flags = store.derive(all_events)

        # Extraction (Phase 1 stub returns the record unchanged).
        new_record = extraction.process_utterance(utt, old_record)

        # Diff old vs new into deterministic fact events.
        fact_events = store.facts_from(utt, old_record, new_record)

        # Safety (Phase 1 stub returns no flags).
        flags = safety.evaluate(new_record)

        # Assemble the batch: utterance, facts, then new flag_raised events.
        existing_flag_ids = {flag.id for flag in old_flags}
        all_events.append(
            Event(
                id=utt.id,
                ts=utt.ts,
                kind="utterance",
                payload={"utterance": utt.model_dump(mode="json")},
            )
        )
        all_events.extend(fact_events)
        new_flag_index = 0
        for flag in flags:
            if flag.id in existing_flag_ids:
                continue
            all_events.append(
                Event(
                    id=f"{utt.id}:flag:{new_flag_index}",
                    ts=utt.ts,
                    kind="flag_raised",
                    payload={"flag": flag.model_dump(mode="json")},
                )
            )
            new_flag_index += 1

    return store.derive(all_events)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
_MISSING = object()


def resolve_path(record: PatientRecord, dotted: str) -> Any:
    """Resolve a dotted path over ``record``, unwrapping ``Sourced`` to ``.value``.

    Supports single-segment scalar/allergies fields and ``list.N`` indices (e.g.
    ``meds_given.0``). Returns the sentinel :data:`_MISSING` when the path cannot
    be resolved (bad attribute or out-of-range index). A resolved ``Sourced`` is
    compared on its ``.value``.
    """
    current: Any = record
    for segment in dotted.split("."):
        if current is None:
            return _MISSING
        if segment.isdigit():
            index = int(segment)
            if not isinstance(current, (list, tuple)) or not (0 <= index < len(current)):
                return _MISSING
            current = current[index]
        else:
            if not hasattr(current, segment):
                return _MISSING
            current = getattr(current, segment)
    # Unwrap provenance wrappers down to the underlying value.
    while isinstance(current, Sourced):
        current = current.value
    return current


def _values_match(actual: Any, expected: Any) -> bool:
    """Compare a derived value to an expected gold value, tolerantly.

    Exact equality by default; when both sides are lists they are compared as
    sets (order-independent, handling the allergies case).
    """
    if actual is _MISSING:
        return False
    if isinstance(actual, list) and isinstance(expected, list):
        try:
            return set(actual) == set(expected)
        except TypeError:
            # Unhashable members: fall back to order-independent element compare.
            return len(actual) == len(expected) and all(e in actual for e in expected)
    return actual == expected


def score_fields(record: PatientRecord, gold: dict[str, Any]) -> tuple[int, int]:
    """Return ``(correct, total)`` over ``gold['fields']`` (empty -> ``(0, 0)``)."""
    fields = gold.get("fields") or {}
    if not isinstance(fields, dict):
        return (0, 0)
    correct = 0
    total = 0
    for dotted, expected in fields.items():
        total += 1
        if _values_match(resolve_path(record, dotted), expected):
            correct += 1
    return (correct, total)


def _gold_flag_types(gold: dict[str, Any]) -> set[str]:
    """Extract the set of expected flag types from a tolerant gold ``flags`` list."""
    raw = gold.get("flags") or []
    if not isinstance(raw, list):
        return set()
    types: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            types.add(item)
        elif isinstance(item, dict) and "type" in item:
            types.add(str(item["type"]))
    return types


def _flag_type_str(flag: Any) -> str:
    """Best-effort string of a derived flag's type (handles Enum ``.value``)."""
    ftype = getattr(flag, "type", None)
    return getattr(ftype, "value", str(ftype))


def score_flags(flags: list, gold: dict[str, Any]) -> tuple[float, float]:
    """Return ``(precision, recall)`` of derived flag types vs gold flag types.

    Compared as sets of type strings. Divide-by-zero is guarded: with no
    predictions and no gold both metrics are ``1.0`` (vacuously correct);
    otherwise an empty denominator yields ``0.0``.
    """
    pred = {_flag_type_str(f) for f in flags}
    want = _gold_flag_types(gold)
    inter = pred & want

    if not pred and not want:
        return (1.0, 1.0)

    precision = len(inter) / len(pred) if pred else (1.0 if not want else 0.0)
    recall = len(inter) / len(want) if want else (1.0 if not pred else 0.0)
    return (precision, recall)


# ---------------------------------------------------------------------------
# Row model + rendering
# ---------------------------------------------------------------------------
class Row:
    """One scored (or skipped) scenario row for the report table."""

    def __init__(
        self,
        scenario: str,
        utterances: int = 0,
        correct: int | None = None,
        total: int | None = None,
        precision: float | None = None,
        recall: float | None = None,
        note: str = "",
    ) -> None:
        self.scenario = scenario
        self.utterances = utterances
        self.correct = correct
        self.total = total
        self.precision = precision
        self.recall = recall
        self.note = note

    @property
    def has_gold_fields(self) -> bool:
        return self.total is not None and self.total > 0

    def field_accuracy_cell(self) -> str:
        if self.correct is None or self.total is None:
            return "-"
        if self.total == 0:
            return "0/0"
        pct = round(100 * self.correct / self.total)
        return f"{self.correct}/{self.total} = {pct}%"

    def precision_cell(self) -> str:
        return "-" if self.precision is None else f"{self.precision:.2f}"

    def recall_cell(self) -> str:
        return "-" if self.recall is None else f"{self.recall:.2f}"


_HEADERS = ("scenario", "utterances", "field_accuracy", "flag_precision", "flag_recall", "notes")


def _row_cells(row: Row) -> tuple[str, ...]:
    return (
        row.scenario,
        str(row.utterances),
        row.field_accuracy_cell(),
        row.precision_cell(),
        row.recall_cell(),
        row.note or "",
    )


def render_plain_table(rows: list[Row]) -> str:
    """Render rows as a plain-text table with aligned columns."""
    all_cells = [_HEADERS] + [_row_cells(r) for r in rows]
    widths = [max(len(c[i]) for c in all_cells) for i in range(len(_HEADERS))]

    def fmt(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    lines = [fmt(_HEADERS), "  ".join("-" * w for w in widths)]
    lines.extend(fmt(_row_cells(r)) for r in rows)
    return "\n".join(lines)


def render_markdown_table(rows: list[Row]) -> str:
    """Render rows as a GitHub-flavored Markdown table."""
    lines = ["| " + " | ".join(_HEADERS) + " |", "| " + " | ".join("---" for _ in _HEADERS) + " |"]
    for r in rows:
        cells = _row_cells(r)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def macro_field_accuracy(rows: list[Row]) -> float | None:
    """Macro-average of per-scenario field accuracy over rows that had gold."""
    scored = [r for r in rows if r.has_gold_fields]
    if not scored:
        return None
    return sum((r.correct or 0) / (r.total or 1) for r in scored) / len(scored)


def write_report(rows: list[Row]) -> None:
    """Write ``eval/report.md``: title, generated-at line, table, one-line summary."""
    generated = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    macro = macro_field_accuracy(rows)
    if macro is None:
        summary = "No scenarios with gold fields were scored."
    else:
        summary = (
            f"Macro-averaged field accuracy over {sum(1 for r in rows if r.has_gold_fields)} "
            f"scenario(s) with gold: {macro * 100:.0f}%."
        )

    parts = [
        "# Scenario Eval Report",
        "",
        f"_Generated at {generated}._",
        "",
    ]
    if rows:
        parts.append(render_markdown_table(rows))
    else:
        parts.append("No scenarios found (`scenarios/` absent or empty).")
    parts.extend(["", summary, ""])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_scenario(scenario_id: str) -> Row:
    """Play + score one scenario id, returning its report :class:`Row`.

    Never raises for expected per-scenario problems (missing/garbled transcript
    or gold): those become a note on the row so the run continues.
    """
    transcript_path = SCENARIOS_DIR / f"{scenario_id}.json"
    gold_path = SCENARIOS_DIR / f"{scenario_id}.gold.json"

    if not transcript_path.is_file():
        return Row(scenario_id, note="file missing")

    try:
        utterances = load_transcript(transcript_path)
    except Exception as exc:  # noqa: BLE001 - malformed transcript: note + continue
        return Row(scenario_id, note=f"parse error: {exc}")

    try:
        gold = load_gold(gold_path)
    except Exception as exc:  # noqa: BLE001 - malformed gold: play but don't score
        gold = None
        gold_note = f"gold parse error: {exc}"
    else:
        gold_note = ""

    record, flags = play_scenario(scenario_id, utterances)

    if gold is None:
        note = gold_note or "no gold"
        return Row(scenario_id, utterances=len(utterances), note=note)

    correct, total = score_fields(record, gold)
    precision, recall = score_flags(flags, gold)
    return Row(
        scenario_id,
        utterances=len(utterances),
        correct=correct,
        total=total,
        precision=precision,
        recall=recall,
        note=gold_note,
    )


def main() -> int:
    """Discover, play, score, print, and write the report. Returns an exit code.

    Returns 0 even when there are no scenarios (this is a report, not a gate);
    non-zero only on an unexpected internal error, never for low scores.
    """
    try:
        ids = discover_scenario_ids(SCENARIOS_DIR)

        if not ids:
            if SCENARIOS_DIR.is_dir():
                print("no scenarios found (scenarios/ present but has no scenario files)")
            else:
                print("no scenarios found (scenarios/ absent)")
            write_report([])
            print(f"wrote {REPORT_PATH}")
            return 0

        rows = [run_scenario(scenario_id) for scenario_id in ids]

        print(render_plain_table(rows))
        macro = macro_field_accuracy(rows)
        if macro is not None:
            print()
            print(f"macro field accuracy (gold scenarios): {macro * 100:.0f}%")

        write_report(rows)
        print(f"wrote {REPORT_PATH}")
        return 0
    except Exception as exc:  # noqa: BLE001 - unexpected internal error only
        print(f"run_scenarios: unexpected internal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
