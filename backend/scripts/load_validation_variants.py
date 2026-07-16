"""Load the blinded cardiology graph variants into ``validation_variants``.

Experts then rate them in-system via the expert workspace. The ``review_item_id``
matches ``build_cardiology_expert_template.py`` so the in-system and CSV paths are
interchangeable. Idempotent: re-running updates existing rows (matched by
``review_item_id``) and never touches collected ratings.

    cd backend
    python scripts/load_validation_variants.py
    # custom source / cohort:
    python scripts/load_validation_variants.py --benchmark benchmarks/cardiology_synthetic_latest.json --cohort cardiology_pilot
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ValidationVariant

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_latest.json"
SHUFFLE_SEED = 20260629

CORRECT_VARIANT = "correct_reference_solution"
# Rare pattern (N=1 in the corpus); force-include it in its own case when subsetting.
RARE_VARIANT = "contraindication_reversed_to_indication"


def _review_item_id(case_id: str, variant_id: str, cohort: str = "cardiology_pilot") -> str:
    # Keep historical IDs for the original pilot cohort. New cohorts must not
    # overwrite already rated validation rows, because ratings reference these
    # blinded review items.
    key = f"{case_id}::{variant_id}"
    if cohort != "cardiology_pilot":
        key = f"{cohort}::{key}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"cre_{digest}"


def _cardiology_block(benchmark: dict[str, Any]) -> dict[str, Any]:
    return benchmark.get("cardiology", benchmark)


def _select_variant_ids(case: dict[str, Any], per_case: int | None) -> list[str]:
    """Pick which variant ids of a case to keep. Always keeps the correct solution.

    Callers pass a shared ``deque`` via case["_rr"] so error patterns are balanced
    round-robin across all cases. Without ``per_case`` all variants are kept.
    """
    all_ids = [v.get("variant_id") for v in case.get("variants", [])]
    if per_case is None or per_case >= len(all_ids):
        return all_ids

    keep: list[str] = [CORRECT_VARIANT] if CORRECT_VARIANT in all_ids else []
    errors = [vid for vid in all_ids if vid != CORRECT_VARIANT]
    slots = max(0, per_case - len(keep))

    # Force-include the rare pattern in the case that owns it.
    if RARE_VARIANT in errors and slots > 0:
        keep.append(RARE_VARIANT)
        errors.remove(RARE_VARIANT)
        slots -= 1

    rr: deque[str] = case["_rr"]
    picked: list[str] = []
    guard = 0
    while slots > 0 and errors and guard < 1000:
        guard += 1
        candidate = rr[0]
        rr.rotate(-1)
        if candidate in errors and candidate not in picked:
            picked.append(candidate)
            slots -= 1
    # Fallback if round-robin under-fills (e.g. case lacks a pattern).
    for vid in errors:
        if slots <= 0:
            break
        if vid not in picked:
            picked.append(vid)
            slots -= 1
    return keep + picked


def _build_rows(benchmark_path: Path, per_case: int | None, cohort: str) -> list[dict[str, Any]]:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    block = _cardiology_block(benchmark)
    results = {(r.get("case_id"), r.get("variant_id")): r for r in block.get("graph", {}).get("results", [])}

    # Shared round-robin of the common error patterns for balanced coverage.
    common_errors = deque(
        [
            "unsafe_extra_action",
            "missing_critical_action",
            "broken_reasoning_chain",
            "missing_key_diagnostic_step",
            "wrong_node_category",
        ]
    )

    rows: list[dict[str, Any]] = []
    pattern_counts: Counter[str] = Counter()
    for case in block.get("cases", []):
        case["_rr"] = common_errors  # shared deque across cases
        case_id = case.get("case_id")
        case_title = case.get("title") or case_id
        task = case.get("task") or {}
        case_prompt = task.get("description") if isinstance(task, dict) else None
        reference_graph = case.get("reference_graph")
        variant_by_id = {v.get("variant_id"): v for v in case.get("variants", [])}
        keep_ids = _select_variant_ids(case, per_case)
        for variant_id in keep_ids:
            variant = variant_by_id.get(variant_id)
            if not variant:
                continue
            result = results.get((case_id, variant_id), {})
            pattern = variant.get("expected_pattern") or result.get("expected_pattern")
            pattern_counts[pattern] += 1
            # Correct variants store the sentinel "__same_as_reference__"; resolve it
            # to the actual reference graph so the rater sees the complete solution.
            student_graph = variant.get("student_graph")
            if not isinstance(student_graph, dict):
                student_graph = reference_graph
            rows.append(
                {
                    "review_item_id": _review_item_id(case_id, variant_id, cohort),
                    "case_id": case_id,
                    "case_title": case_title,
                    "case_prompt": case_prompt,
                    "variant_id": variant_id,
                    "expected_pattern": pattern,
                    "graph_under_review": variant.get("description"),
                    "student_graph": student_graph,
                    "reference_graph": reference_graph,
                    "model_metrics": result.get("metrics"),
                }
            )

    # Deterministic blinded order so raters do not see variants grouped by case.
    rng = random.Random(SHUFFLE_SEED)
    rng.shuffle(rows)
    for index, row in enumerate(rows, start=1):
        row["display_order"] = index
    _build_rows.last_pattern_counts = dict(pattern_counts)  # type: ignore[attr-defined]
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load blinded validation variants into the DB.")
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    parser.add_argument("--cohort", default="cardiology_pilot")
    parser.add_argument(
        "--per-case",
        type=int,
        default=3,
        help="Variants kept per case (correct + balanced errors). Use 0 to keep all.",
    )
    args = parser.parse_args()

    per_case = None if args.per_case <= 0 else args.per_case
    rows = _build_rows(Path(args.benchmark), per_case, args.cohort)
    selected_ids = {row["review_item_id"] for row in rows}
    created = updated = deactivated = 0

    async with AsyncSessionLocal() as session:
        for row in rows:
            existing = await session.execute(
                select(ValidationVariant).where(ValidationVariant.review_item_id == row["review_item_id"])
            )
            variant = existing.scalars().first()
            if variant is None:
                variant = ValidationVariant(review_item_id=row["review_item_id"], cohort=args.cohort)
                session.add(variant)
                created += 1
            else:
                updated += 1
            variant.cohort = args.cohort
            variant.case_id = row["case_id"]
            variant.case_title = row["case_title"]
            variant.case_prompt = row["case_prompt"]
            variant.variant_id = row["variant_id"]
            variant.expected_pattern = row["expected_pattern"]
            variant.graph_under_review = row["graph_under_review"]
            variant.student_graph = row["student_graph"]
            variant.reference_graph = row["reference_graph"]
            variant.model_metrics = row["model_metrics"]
            variant.display_order = row["display_order"]
            variant.is_active = 1

        # Deactivate (don't delete) cohort variants no longer in the selection, so
        # any previously collected ratings stay intact.
        cohort_rows = await session.execute(
            select(ValidationVariant).where(ValidationVariant.cohort == args.cohort)
        )
        for variant in cohort_rows.scalars().all():
            if variant.review_item_id not in selected_ids and variant.is_active != 0:
                variant.is_active = 0
                deactivated += 1
        await session.commit()

    print(
        json.dumps(
            {
                "cohort": args.cohort,
                "per_case": args.per_case,
                "created": created,
                "updated": updated,
                "deactivated": deactivated,
                "total_active": len(rows),
                "pattern_coverage": getattr(_build_rows, "last_pattern_counts", {}),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
