"""Build the fillable expert-rating CSV fallback from the DB (source of truth).

Mirrors exactly the active variants experts see in-system, so the CSV and the
in-system path are interchangeable (same ``review_item_id``). Researcher-only
fields (expected_pattern, model metrics) go into a separate key + eval benchmark,
not the fillable template.

    cd backend
    python scripts/build_expert_csv_from_db.py --cohort cardiology_pilot --experts 5
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ValidationVariant

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = BACKEND_ROOT / "benchmarks" / "cardiology_expert_ratings_REAL.template.csv"
KEY = BACKEND_ROOT / "benchmarks" / "cardiology_expert_review_key.json"
EVAL_BENCHMARK = BACKEND_ROOT / "benchmarks" / "cardiology_graph_benchmark_for_expert_eval.json"


async def _active_variants(cohort: str) -> list[ValidationVariant]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ValidationVariant)
            .where(ValidationVariant.cohort == cohort, ValidationVariant.is_active == 1)
            .order_by(ValidationVariant.display_order.asc().nulls_last(), ValidationVariant.id.asc())
        )
        return list(rows.scalars().all())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build expert CSV fallback from active DB variants.")
    parser.add_argument("--cohort", default="cardiology_pilot")
    parser.add_argument("--experts", type=int, default=5)
    args = parser.parse_args()

    variants = asyncio.run(_active_variants(args.cohort))
    if not variants:
        raise SystemExit(f"No active variants in cohort {args.cohort}. Run load_validation_variants.py first.")

    experts = [f"expert_{i:02d}" for i in range(1, args.experts + 1)]

    template_rows: list[dict[str, Any]] = []
    key_items: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for variant in variants:
        key_items.append(
            {
                "review_item_id": variant.review_item_id,
                "case_id": variant.case_id,
                "variant_id": variant.variant_id,
                "expected_pattern": variant.expected_pattern,
                "metrics": variant.model_metrics or {},
            }
        )
        results.append(
            {
                "case_id": variant.case_id,
                "variant_id": variant.variant_id,
                "expected_pattern": variant.expected_pattern,
                "metrics": variant.model_metrics or {},
            }
        )
        for expert_id in experts:
            template_rows.append(
                {
                    "review_item_id": variant.review_item_id,
                    "clinical_case_title": variant.case_title,
                    "graph_under_review": variant.graph_under_review,
                    "expert_id": expert_id,
                    "expert_score_0_100": "",
                    "expert_accept": "",
                    "expert_comment": "",
                }
            )

    fieldnames = [
        "review_item_id", "clinical_case_title", "graph_under_review",
        "expert_id", "expert_score_0_100", "expert_accept", "expert_comment",
    ]
    with TEMPLATE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(template_rows)

    KEY.write_text(
        json.dumps(
            {
                "source": "db",
                "cohort": args.cohort,
                "note": "Researcher-only key. Do NOT share with raters.",
                "items": key_items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    EVAL_BENCHMARK.write_text(
        json.dumps({"graph": {"results": results}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "template": str(TEMPLATE),
                "key": str(KEY),
                "eval_benchmark": str(EVAL_BENCHMARK),
                "variants": len(variants),
                "experts": experts,
                "rows_to_fill": len(template_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
