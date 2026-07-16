"""Recompute model metrics for blinded validation variants.

This preserves expert ratings and graph payloads, but refreshes
``ValidationVariant.model_metrics`` with the current GraphEvaluator version.

Usage:
    cd backend
    python scripts/rescore_validation_variants.py --cohort cardiology_pilot
    python scripts/rescore_validation_variants.py --cohort cardiology_pilot --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ValidationVariant
from app.schemas import GraphSchema
from app.services.graph_evaluator import EVALUATION_ALGORITHM_VERSION, GraphEvaluator


METRIC_KEYS = (
    "precision",
    "recall",
    "f1_score",
    "edge_f1",
    "weighted_precision",
    "weighted_recall",
    "weighted_edge_f1",
    "node_coverage",
    "chain_completeness",
    "directed_path_completeness",
    "category_accuracy",
    "structural_correctness",
    "safety_penalty",
    "edge_count_penalty",
    "student_edge_count",
    "reference_edge_count",
    "unsafe_extra_action",
    "missing_critical_action",
    "diagnostic_evidence_gap",
    "diagnostic_evidence_findings",
    "clinical_connectivity_gap",
    "clinical_connectivity_findings",
    "score_caps",
    "safety_findings",
    "missing_edges",
    "incorrect_edges",
    "missing_nodes",
    "composite_score",
    "algorithm_version",
)


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in METRIC_KEYS if key in payload}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score blinded validation variants with the current evaluator.")
    parser.add_argument("--cohort", default="cardiology_pilot")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    updated = skipped = 0
    failures: list[dict[str, str]] = []
    patterns: Counter[str] = Counter()
    scores: list[float] = []

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ValidationVariant)
            .where(ValidationVariant.cohort == args.cohort)
            .where(ValidationVariant.is_active == 1)
            .order_by(ValidationVariant.case_id, ValidationVariant.variant_id)
        )
        variants = rows.scalars().all()

        for variant in variants:
            student_graph = variant.student_graph
            reference_graph = variant.reference_graph
            if not isinstance(student_graph, dict) or not isinstance(reference_graph, dict):
                skipped += 1
                continue
            try:
                result = GraphEvaluator.evaluate(
                    GraphSchema.model_validate(student_graph),
                    GraphSchema.model_validate(reference_graph),
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    {
                        "case_id": str(variant.case_id),
                        "variant_id": str(variant.variant_id),
                        "error": repr(exc),
                    }
                )
                continue

            metrics = _score_payload(result)
            patterns[str(variant.expected_pattern)] += 1
            if metrics.get("composite_score") is not None:
                scores.append(float(metrics["composite_score"]))
            if not args.dry_run:
                variant.model_metrics = metrics
            updated += 1

        if not args.dry_run:
            await session.commit()

    print(
        json.dumps(
            {
                "ok": not failures,
                "mode": "dry_run" if args.dry_run else "applied",
                "cohort": args.cohort,
                "algorithm_version": EVALUATION_ALGORITHM_VERSION,
                "updated": updated,
                "skipped": skipped,
                "failed": len(failures),
                "mean_composite": round(sum(scores) / len(scores), 4) if scores else None,
                "pattern_counts": dict(patterns),
                "failures": failures[:20],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
