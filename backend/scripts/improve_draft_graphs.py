"""Re-generate low-quality draft reference graphs, keeping the best attempt.

For each `draft` reference graph that has a source protocol, regenerates the
solution graph (the task/description is preserved) up to N times and keeps the
attempt with the best quality (accepted first, then higher quality_score). Only
updates a graph if a strictly better version is found.

    cd backend
    python scripts/improve_draft_graphs.py --retries 3
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ReferenceGraph
from app.schemas import GraphSchema
from app.services.graph_generation_judge import judge_reference_graph
from app.services.rag_service import RAGService


def _quality_texts(quality: dict) -> list[str]:
    return [
        f"{str(w.get('severity','')).upper()} {w.get('code','')}: {w.get('message','')}"
        for w in quality.get("warnings", [])
    ]


def _better(candidate: dict, current: dict) -> bool:
    """True if candidate quality beats current (accepted first, then score)."""
    c_acc = bool(candidate.get("accepted"))
    cur_acc = bool(current.get("accepted"))
    if c_acc != cur_acc:
        return c_acc
    return float(candidate.get("quality_score") or 0) > float(current.get("quality_score") or 0)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Improve low-quality draft reference graphs.")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    improved = unchanged = skipped = 0
    async with AsyncSessionLocal() as session:
        svc = RAGService(session)
        drafts = (await session.execute(select(ReferenceGraph).where(ReferenceGraph.status == "draft"))).scalars().all()
        print(f"draft graphs: {len(drafts)}")

        for g in drafts:
            ctx = (g.generation_context or [{}])
            pid = ctx[0].get("protocol_id") if ctx and isinstance(ctx[0], dict) else None
            if not pid:
                skipped += 1
                print(f"  [skip] #{g.id} no source protocol ({g.title[:40]})")
                continue

            best_quality = g.generation_quality or {"quality_score": 0, "accepted": False}
            best_graph = g.graph_data
            start_score = float(best_quality.get("quality_score") or 0)

            for attempt in range(1, args.retries + 1):
                try:
                    result = await svc.generate_reference_graph([pid], g.title, g.description or g.title)
                    schema = GraphSchema.model_validate(result.get("graph") or {})
                except Exception as exc:
                    print(f"  #{g.id} attempt {attempt} failed: {exc!r}")
                    continue
                quality = judge_reference_graph(schema)
                if _better(quality, best_quality):
                    best_quality = quality
                    best_graph = schema.model_dump()
                if best_quality.get("accepted") and float(best_quality.get("quality_score") or 0) >= 0.97:
                    break

            if float(best_quality.get("quality_score") or 0) > start_score:
                g.graph_data = best_graph
                g.generation_quality = best_quality
                g.validation_warnings = _quality_texts(best_quality)
                g.status = "review_ready" if best_quality.get("critical_count", 0) == 0 else "draft"
                await session.commit()
                improved += 1
                print(f"  [improved] #{g.id} {start_score:.2f} -> {best_quality.get('quality_score')} "
                      f"accepted={best_quality.get('accepted')} status={g.status}")
            else:
                unchanged += 1
                print(f"  [kept] #{g.id} stays {start_score:.2f} (no better attempt)")

    print(f"STATS improved={improved} unchanged={unchanged} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
