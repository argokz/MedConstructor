"""Export protocol provenance for the controlled cardiology benchmark cases."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_seed.json"
DEFAULT_SYNTHETIC_RESULT = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_latest.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "benchmarks" / "cardiology_protocol_grounding.csv"
DEFAULT_TASK_OUTPUT = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_tasks_latest.csv"


def _source_id(source: dict[str, Any]) -> str | None:
    explicit = source.get("protocol_external_id") or source.get("external_protocol_id")
    if explicit not in (None, ""):
        return str(explicit)
    match = re.search(r"/(\d+)(?:\?.*)?$", str(source.get("protocol_url") or ""))
    return match.group(1) if match else None


def build_rows(seed_path: Path = DEFAULT_SEED) -> list[dict[str, Any]]:
    cases = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    for case in cases:
        source = case.get("source_protocol") or {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "case_title": case.get("title"),
                "database_protocol_id": source.get("protocol_id"),
                "source_protocol_id": _source_id(source),
                "protocol_title": source.get("protocol_title"),
                "protocol_year": source.get("protocol_year"),
                "protocol_category": "; ".join(source.get("protocol_sections") or []),
                "protocol_version": source.get("protocol_version"),
                "protocol_url": source.get("protocol_url"),
                "source_fit": source.get("source_fit"),
                "source_note": source.get("source_note"),
            }
        )
    return rows


def build_task_rows(seed_path: Path = DEFAULT_SEED) -> list[dict[str, Any]]:
    cases = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    source_by_case = {
        str(case.get("case_id")): case.get("source_protocol") or {} for case in cases
    }
    result = json.loads(DEFAULT_SYNTHETIC_RESULT.read_text(encoding="utf-8-sig"))
    result_tasks = {
        str(task.get("case_id")): task for task in result.get("tasks") or []
    }
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        task = result_tasks.get(case_id) or case.get("task") or {}
        graph = case.get("reference_graph") or {}
        source = source_by_case.get(case_id) or {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "protocol_area": case.get("protocol_area"),
                "database_protocol_id": source.get("protocol_id"),
                "source_protocol_id": _source_id(source),
                "source_protocol_title": source.get("protocol_title"),
                "source_protocol_year": source.get("protocol_year"),
                "source_protocol_sections": "; ".join(source.get("protocol_sections") or []),
                "source_protocol_chunk_count": source.get("protocol_chunk_count"),
                "source_protocol_url": source.get("protocol_url"),
                "source_fit": source.get("source_fit"),
                "source_note": source.get("source_note"),
                "protocol_focus": task.get("protocol_focus"),
                "difficulty": task.get("difficulty"),
                "target_competency": task.get("target_competency"),
                "task_quality_score": task.get("task_quality_score"),
                "task_quality_accepted": task.get("task_quality_accepted"),
                "expected_sections": "; ".join(task.get("expected_sections") or []),
                "red_flags": "; ".join(task.get("red_flags") or []),
                "checklist_count": task.get("checklist_count", len(task.get("checklist") or [])),
                "description_chars": task.get(
                    "description_chars", len(str(task.get("description") or ""))
                ),
                "reference_node_count": task.get("reference_node_count", len(graph.get("nodes") or [])),
                "reference_edge_count": task.get("reference_edge_count", len(graph.get("edges") or [])),
                "variant_count": task.get("variant_count", len(case.get("variants") or [])),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_rows()
    if not rows:
        raise RuntimeError("The cardiology seed contains no cases")
    if any(not row["source_protocol_id"] for row in rows):
        raise RuntimeError("Every cardiology case must have a source protocol ID")

    task_rows = build_task_rows()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(DEFAULT_OUTPUT, rows)
    _write_csv(DEFAULT_TASK_OUTPUT, task_rows)
    print(f"Wrote {len(rows)} rows to {DEFAULT_OUTPUT}")
    print(f"Wrote {len(task_rows)} rows to {DEFAULT_TASK_OUTPUT}")


if __name__ == "__main__":
    main()
