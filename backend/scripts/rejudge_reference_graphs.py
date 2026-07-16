"""Re-run the current reference-graph judge against stored graphs.

Dry-run is the default. Use ``--apply`` to persist quality metadata and
``--demote-invalid`` to return critically invalid published assignments to
teacher review.

Examples:
    python scripts/rejudge_reference_graphs.py --reference-id 111
    python scripts/rejudge_reference_graphs.py --reference-id 111 --apply --demote-invalid
    python scripts/rejudge_reference_graphs.py --all --apply --demote-invalid
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

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Assignment, ReferenceGraph
from app.schemas import GraphSchema
from app.services.graph_generation_judge import (
    format_quality_warning,
    judge_reference_graph,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--reference-id", type=int)
    target.add_argument("--assignment-id", type=int)
    target.add_argument("--all", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--demote-invalid", action="store_true")
    return parser.parse_args()


def _warning_texts(quality: dict[str, Any]) -> list[str]:
    return [format_quality_warning(item) for item in quality.get("warnings") or []]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        query = select(ReferenceGraph).order_by(ReferenceGraph.id)
        if args.reference_id:
            query = query.where(ReferenceGraph.id == args.reference_id)
        elif args.assignment_id:
            assignment = await session.get(Assignment, args.assignment_id)
            if not assignment:
                raise SystemExit(f"Assignment {args.assignment_id} not found")
            query = query.where(ReferenceGraph.id == assignment.reference_graph_id)

        references = list((await session.execute(query)).scalars().all())
        if not references:
            raise SystemExit("No reference graphs matched the requested target")

        reference_ids = [row.id for row in references]
        assignments = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.reference_graph_id.in_(reference_ids))
                )
            )
            .scalars()
            .all()
        )
        assignments_by_reference: dict[int, list[Assignment]] = {}
        for assignment in assignments:
            assignments_by_reference.setdefault(assignment.reference_graph_id, []).append(assignment)

        rows: list[dict[str, Any]] = []
        issue_counts: Counter[str] = Counter()
        demoted_assignment_ids: list[int] = []

        for reference in references:
            try:
                graph = GraphSchema.model_validate(reference.graph_data or {})
                quality = judge_reference_graph(graph)
            except Exception as exc:
                quality = {
                    "accepted": False,
                    "quality_score": 0.0,
                    "critical_count": 1,
                    "warning_count": 1,
                    "warnings": [
                        {
                            "severity": "critical",
                            "code": "invalid_graph_schema",
                            "message": str(exc),
                        }
                    ],
                }

            warnings = quality.get("warnings") or []
            issue_codes = [str(item.get("code") or "graph_quality") for item in warnings]
            issue_counts.update(issue_codes)
            linked = assignments_by_reference.get(reference.id, [])

            if args.apply:
                reference.generation_quality = quality
                reference.validation_warnings = _warning_texts(quality)
                if quality.get("critical_count", 0) > 0:
                    reference.status = "needs_teacher_review"
                    reference.approved_by_id = None
                    reference.approved_at = None
                    if args.demote_invalid:
                        for assignment in linked:
                            if assignment.status in {"published", "teacher_approved"}:
                                assignment.status = "needs_teacher_review"
                                assignment.approved_by_id = None
                                assignment.approved_at = None
                                assignment.published_at = None
                                demoted_assignment_ids.append(assignment.id)

            rows.append(
                {
                    "reference_graph_id": reference.id,
                    "title": reference.title,
                    "status_before_or_current": reference.status,
                    "assignment_ids": [item.id for item in linked],
                    "accepted": bool(quality.get("accepted")),
                    "quality_score": quality.get("quality_score"),
                    "critical_count": int(quality.get("critical_count", 0)),
                    "warning_count": int(quality.get("warning_count", 0)),
                    "issue_codes": issue_codes,
                }
            )

        if args.apply:
            await session.commit()

        return {
            "mode": "apply" if args.apply else "dry_run",
            "demote_invalid": bool(args.demote_invalid),
            "references_checked": len(rows),
            "references_with_critical": sum(row["critical_count"] > 0 for row in rows),
            "demoted_assignment_ids": sorted(set(demoted_assignment_ids)),
            "issue_counts": dict(issue_counts.most_common()),
            "results": rows,
        }


def main() -> None:
    args = _arguments()
    if args.demote_invalid and not args.apply:
        raise SystemExit("--demote-invalid requires --apply")
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
