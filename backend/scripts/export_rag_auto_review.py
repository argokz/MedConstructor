"""Export the 36 auto-generated RAG cases for expert verification (part B).

Builds a spreadsheet-friendly CSV where a domain expert confirms or corrects the
expected protocol / sections / key phrases of each auto-generated case. The current
expectations are pre-filled into the ``verified_*`` columns, and the system's actual
top results are shown as a suggestion so the reviewer can judge quickly.

    cd backend
    python scripts/export_rag_auto_review.py
    # -> benchmarks/rag_auto_cases_review.template.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED = BACKEND_ROOT / "benchmarks" / "rag_queries.research.seed.json"
RESULTS = BACKEND_ROOT / "benchmarks" / "rag_research_latest.json"
OUT = BACKEND_ROOT / "benchmarks" / "rag_auto_cases_review.template.csv"

SEP = " | "


def _join(values: Any) -> str:
    if not values:
        return ""
    return SEP.join(str(v) for v in values)


def _full_results_by_id(results_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def find_full(node: Any) -> list[dict[str, Any]] | None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, list) and value and isinstance(value[0], dict) and "hit_rank" in value[0]:
                    if any(r.get("mode") == "full" for r in value):
                        return [r for r in value if r.get("mode") == "full"]
                found = find_full(value)
                if found:
                    return found
        return None

    rows = find_full(results_payload) or []
    return {str(r.get("id")): r for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export auto-generated RAG cases for expert review.")
    parser.add_argument("--seed", default=str(SEED))
    parser.add_argument("--results", default=str(RESULTS))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    auto = [q for q in seed if (q.get("metadata") or {}).get("requires_expert_review")]
    results_by_id = {}
    if Path(args.results).exists():
        results_by_id = _full_results_by_id(json.loads(Path(args.results).read_text(encoding="utf-8")))

    fieldnames = [
        "id", "query",
        "current_expected_protocol_ids", "current_expected_sections", "current_expected_key_phrases",
        "system_top_protocols", "system_top_sections", "hit_rank",
        "decision",  # keep / fix / drop
        "verified_expected_protocol_ids", "verified_expected_sections", "verified_expected_key_phrases",
        "reviewer_notes",
    ]
    with Path(args.out).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for case in auto:
            res = results_by_id.get(str(case.get("id")), {})
            sources = res.get("sources") or []
            top_protocols = _join([f"{s.get('protocol_id')}:{s.get('protocol_title')}" for s in sources[:5]])
            top_sections = _join([s.get("section") for s in sources[:5] if s.get("section")])
            writer.writerow(
                {
                    "id": case.get("id"),
                    "query": case.get("query"),
                    "current_expected_protocol_ids": _join(case.get("expected_protocol_ids")),
                    "current_expected_sections": _join(case.get("expected_sections")),
                    "current_expected_key_phrases": _join(case.get("expected_key_phrases")),
                    "system_top_protocols": top_protocols,
                    "system_top_sections": top_sections,
                    "hit_rank": res.get("hit_rank"),
                    "decision": "",  # reviewer fills: keep / fix / drop
                    # Pre-fill verified_* with current values; reviewer edits only what is wrong.
                    "verified_expected_protocol_ids": _join(case.get("expected_protocol_ids")),
                    "verified_expected_sections": _join(case.get("expected_sections")),
                    "verified_expected_key_phrases": _join(case.get("expected_key_phrases")),
                    "reviewer_notes": "",
                }
            )

    print(
        json.dumps(
            {"out": str(args.out), "auto_cases": len(auto), "separator": SEP.strip()},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
