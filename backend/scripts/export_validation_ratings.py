"""Export in-system expert ratings to the real cardiology validation artifact.

Reads ``validation_ratings`` collected through the expert workspace, reconstructs
the benchmark from the stored model metrics, runs the shared correlation analyzer,
enriches it with bootstrap CIs + baseline comparison, and writes
``benchmarks/cardiology_real_expert_validation_latest.json`` plus a long-format
ratings CSV for supplementary materials.

    cd backend
    python scripts/export_validation_ratings.py --cohort cardiology_pilot
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User, ValidationRating, ValidationVariant
from app.services.expert_evaluation import analyze_expert_ratings
from app.services.graph_evaluator import EVALUATION_ALGORITHM_VERSION
from scripts.enrich_cardiology_real_validation import enrich_payload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_validation_latest.json"
OUT_CSV = BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_ratings_latest.csv"


async def _load(cohort: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with AsyncSessionLocal() as session:
        variant_rows = await session.execute(
            select(ValidationVariant).where(
                ValidationVariant.cohort == cohort, ValidationVariant.is_active == 1
            )
        )
        variants = {v.id: v for v in variant_rows.scalars().all()}

        rating_rows = await session.execute(
            select(ValidationRating, User)
            .join(User, User.id == ValidationRating.expert_id)
            .where(ValidationRating.variant_id.in_(list(variants.keys())))
        )
        ratings = rating_rows.all()

    # Public research artifacts use stable cohort-local codes rather than login
    # addresses or database identifiers. The mapping is intentionally not exported.
    expert_codes = {
        expert_id: f"expert_{index:02d}"
        for index, expert_id in enumerate(
            sorted({expert.id for _, expert in ratings}),
            start=1,
        )
    }

    results = [
        {
            "case_id": v.case_id,
            "variant_id": v.variant_id,
            "expected_pattern": v.expected_pattern,
            "metrics": v.model_metrics or {},
        }
        for v in variants.values()
    ]

    rating_records: list[dict[str, Any]] = []
    for rating, expert in ratings:
        if rating.score is None:
            continue
        variant = variants[rating.variant_id]
        rating_records.append(
            {
                "expert_id": expert_codes[expert.id],
                "case_id": variant.case_id,
                "variant_id": variant.variant_id,
                "expected_pattern": variant.expected_pattern,
                "model_score": float((variant.model_metrics or {}).get("composite_score") or 0.0),
                "expert_score_0_100": rating.score,
                "expert_accept": rating.accept,
                "expert_comment": rating.comment,
            }
        )
    return results, rating_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Export in-system expert ratings to the validation artifact.")
    parser.add_argument("--cohort", default="cardiology_pilot")
    parser.add_argument("--out", default=str(OUT_JSON))
    args = parser.parse_args()

    results, rating_records = asyncio.run(_load(args.cohort))
    if not rating_records:
        raise SystemExit("No ratings found. Experts have not submitted any scores yet.")

    benchmark = {"graph": {"results": results}}
    report = analyze_expert_ratings(benchmark, rating_records)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": args.cohort,
        "algorithm_version": EVALUATION_ALGORITHM_VERSION,
        "summary": {
            "case_count": len({r["case_id"] for r in results}),
            "variant_count": report["item_count"],
            "expert_count": report["expert_count"],
            "rating_count": report["rating_count"],
            "expert_panel_mode": "real_cardiologist_panel",
            "human_subject_data": True,
            "pattern_pass_rate": None,
        },
        "expert_panel": {
            "panel_mode": "real_cardiologist_panel",
            "is_human_subject_data": True,
            "expert_count": report["expert_count"],
            "evaluation_scale": "0-100 raw score, normalized to 0-1 for analysis",
            "blind_evaluation_design": True,
        },
        "results": results,
        "expert_items": report["items"],
        "by_expert": report["by_expert"],
        "by_expected_pattern": report["by_expected_pattern"],
        "inter_rater": report["inter_rater"],
        "correlation_with_mean_expert": report["correlation_with_mean_expert"],
        "skipped_row_count": report["skipped_row_count"],
    }

    # Add bootstrap CIs + baseline comparison via the shared enrich step.
    payload = enrich_payload(payload)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = [
            "expert_id", "case_id", "variant_id", "expected_pattern",
            "model_score", "expert_score_0_100", "expert_accept", "expert_comment",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rating_records)

    summary = payload.get("summary", {})
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(out_path),
                "csv": str(OUT_CSV),
                "experts": summary.get("expert_count"),
                "variants": summary.get("variant_count"),
                "ratings": summary.get("rating_count"),
                "spearman": summary.get("expert_spearman"),
                "spearman_ci": [summary.get("expert_spearman_ci_low"), summary.get("expert_spearman_ci_high")],
                "mae": summary.get("expert_mae"),
                "bias": summary.get("expert_bias"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
