"""Publish assignments whose reference graph passes quality (0 critical warnings).

Makes the generated tasks visible to students (no targets => visible to all),
so the solve -> submit -> review flow can be exercised. Mirrors the publish
endpoint: sets assignment.status=published + approver/timestamps and
reference_graph.status=approved. Idempotent.

    cd backend
    python scripts/publish_assignments.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Assignment, ReferenceGraph, User
from app.schemas import GraphSchema
from app.services.graph_generation_judge import judge_reference_graph


async def main() -> None:
    published = skipped_critical = skipped_empty = 0
    async with AsyncSessionLocal() as session:
        teacher = (await session.execute(select(User).where(User.role == "teacher"))).scalars().first()
        assignments = (await session.execute(select(Assignment))).scalars().all()
        now = datetime.now(timezone.utc)

        for assignment in assignments:
            if (assignment.status or "") == "published":
                continue
            ref = await session.get(ReferenceGraph, assignment.reference_graph_id)
            if not ref or not ref.graph_data:
                skipped_empty += 1
                continue
            try:
                quality = judge_reference_graph(GraphSchema.model_validate(ref.graph_data))
            except Exception:
                skipped_empty += 1
                continue
            if quality.get("critical_count", 0) > 0:
                skipped_critical += 1
                print(f"  [skip-critical] assignment {assignment.id} '{assignment.title[:38]}'")
                continue

            assignment.status = "published"
            assignment.approved_by_id = teacher.id if teacher else None
            assignment.approved_at = now
            assignment.published_at = now
            ref.status = "approved"
            ref.approved_by_id = teacher.id if teacher else None
            ref.approved_at = now
            published += 1

        await session.commit()

    print(f"published={published} skipped_critical={skipped_critical} skipped_empty={skipped_empty}")


if __name__ == "__main__":
    asyncio.run(main())
