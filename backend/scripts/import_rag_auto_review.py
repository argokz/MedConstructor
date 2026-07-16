"""Merge expert decisions on auto-generated RAG cases into a verified seed (part B).

Reads the reviewed CSV from ``export_rag_auto_review.py`` and writes a clean seed:
- curated cases are carried over unchanged;
- auto cases marked ``keep``/``fix`` become ``requires_expert_review=false``
  (source ``expert_verified``) with the reviewer's verified expectations;
- auto cases marked ``drop`` are excluded;
- auto cases with an empty decision are kept as-is (still flagged for review).

    cd backend
    python scripts/import_rag_auto_review.py --reviewed benchmarks/rag_auto_cases_review.filled.csv
    # -> benchmarks/rag_queries.research.verified.seed.json
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
OUT = BACKEND_ROOT / "benchmarks" / "rag_queries.research.verified.seed.json"
SEP = "|"


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(SEP) if part.strip()]


def _split_ints(value: str | None) -> list[int]:
    out: list[int] = []
    for part in _split(value):
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge expert RAG review decisions into a verified seed.")
    parser.add_argument("--seed", default=str(SEED))
    parser.add_argument("--reviewed", required=True, help="Filled review CSV.")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    by_id = {str(q.get("id")): q for q in seed}

    with Path(args.reviewed).open("r", encoding="utf-8-sig", newline="") as file:
        reviewed = {str(row["id"]): row for row in csv.DictReader(file)}

    out_cases: list[dict[str, Any]] = []
    stats = {"curated": 0, "verified_keep": 0, "verified_fix": 0, "dropped": 0, "still_unreviewed": 0}

    for case in seed:
        cid = str(case.get("id"))
        meta = case.get("metadata") or {}
        if not meta.get("requires_expert_review"):
            out_cases.append(case)
            stats["curated"] += 1
            continue

        row = reviewed.get(cid)
        decision = (row or {}).get("decision", "").strip().lower()
        if not row or decision not in {"keep", "fix", "drop"}:
            out_cases.append(case)  # leave flagged
            stats["still_unreviewed"] += 1
            continue
        if decision == "drop":
            stats["dropped"] += 1
            continue

        verified = dict(case)
        verified["expected_protocol_ids"] = _split_ints(row.get("verified_expected_protocol_ids")) or case.get("expected_protocol_ids", [])
        verified["expected_sections"] = _split(row.get("verified_expected_sections")) or case.get("expected_sections", [])
        verified["expected_key_phrases"] = _split(row.get("verified_expected_key_phrases")) or case.get("expected_key_phrases", [])
        verified["metadata"] = {
            **meta,
            "requires_expert_review": False,
            "source": "expert_verified",
            "reviewer_notes": (row.get("reviewer_notes") or "").strip() or None,
        }
        out_cases.append(verified)
        stats["verified_keep" if decision == "keep" else "verified_fix"] += 1

    Path(args.out).write_text(json.dumps(out_cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verified_total = stats["curated"] + stats["verified_keep"] + stats["verified_fix"]
    print(
        json.dumps(
            {
                "out": str(args.out),
                "total_cases": len(out_cases),
                "expert_verified_or_curated": verified_total,
                **stats,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
