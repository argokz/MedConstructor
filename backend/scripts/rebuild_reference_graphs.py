"""Rebuild reference graphs (RU) from fresh protocols using the strengthened generator.

For each curated protocol (newest version), generates a clinical scenario (the task)
and a protocol-grounded reference graph, then creates a paired draft Assignment +
ReferenceGraph for teacher validation. Optionally deletes the previous reference
graphs (and their cascaded demo assignments/attempts) afterwards.

    cd backend
    # dry pilot, no deletion:
    python scripts/rebuild_reference_graphs.py --limit 2
    # full rebuild, replace old set:
    python scripts/rebuild_reference_graphs.py --delete-old
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Assignment, ClinicalProtocol, Discipline, ReferenceGraph, User
from app.schemas import GraphSchema
from app.services.graph_generation_judge import judge_reference_graph
from app.services.rag_service import RAGService

# Curated nosologies. Ordered to span one specialty per item so that a small
# --limit still yields a broad cross-specialty set.
PROTOCOL_KEYWORDS = [
    "инфаркт миокарда с подъемом",        # cardiology
    "бронхиальная астма",                 # pulmonology
    "сахарный диабет 2 типа",             # endocrinology
    "язвенная болезнь",                   # gastroenterology
    "хроническая болезнь почек",          # nephrology
    "ишемический инсульт",                # neurology
    "пневмония",                          # infectious/respiratory
    "преэклампсия",                       # obstetrics
    "фебрильные судороги",                # pediatrics
    "железодефицитная анемия",            # hematology
    "ревматоидный артрит",                # rheumatology
    "мочекаменная болезнь",               # urology
    # remainder (used only when --limit is larger)
    "фибрилляция и трепетание предсердий", "хроническая сердечная недостаточность",
    "артериальная гипертензия", "тромбоэмболия легочной артерии",
    "стабильная ишемическая болезнь", "инфекционный эндокардит",
    "легочная гипертензия", "хроническая обструктивная болезнь",
    "гипотиреоз", "цирроз печени", "панкреатит", "пиелонефрит",
    "эпилепсия", "сепсис", "туберкулез", "гестационный сахарный диабет",
    "бронхиолит",
]


async def _select_protocols(session, keywords: list[str], limit: int | None) -> list[ClinicalProtocol]:
    chosen: dict[int, ClinicalProtocol] = {}
    for kw in keywords:
        rows = await session.execute(
            select(ClinicalProtocol)
            .where(ClinicalProtocol.title.ilike(f"%{kw}%"))
            .order_by(ClinicalProtocol.year.desc().nulls_last(), ClinicalProtocol.id.desc())
            .limit(1)
        )
        p = rows.scalars().first()
        if p and p.id not in chosen:
            chosen[p.id] = p
        if limit and len(chosen) >= limit:
            break
    return list(chosen.values())


async def _get_discipline(session) -> Discipline:
    res = await session.execute(select(Discipline).where(Discipline.name == "Общая медицина"))
    discipline = res.scalars().first()
    if not discipline:
        discipline = Discipline(name="Общая медицина", code="GM01")
        session.add(discipline)
        await session.commit()
        await session.refresh(discipline)
    return discipline


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild RU reference graphs from fresh protocols.")
    parser.add_argument("--limit", type=int, default=None, help="Max protocols to process (pilot).")
    parser.add_argument("--delete-old", action="store_true", help="Delete pre-existing reference graphs afterwards.")
    args = parser.parse_args()

    stats = {"protocols": 0, "graphs_created": 0, "schema_failed": 0, "accepted": 0}
    safety = Counter()

    async with AsyncSessionLocal() as session:
        svc = RAGService(session)
        discipline = await _get_discipline(session)
        teacher = (await session.execute(select(User).where(User.role == "teacher"))).scalars().first()

        old_ids = [r for (r,) in (await session.execute(select(ReferenceGraph.id))).all()]
        protocols = await _select_protocols(session, PROTOCOL_KEYWORDS, args.limit)
        print(f"selected {len(protocols)} protocols; existing reference graphs: {len(old_ids)}")

        for p in protocols:
            stats["protocols"] += 1
            try:
                scenarios = await svc.generate_scenarios([p.id])
                scenario = scenarios[0] if scenarios else {"title": p.title, "description": f"Клинический случай по протоколу: {p.title}."}
                title = scenario.get("title") or p.title
                description = scenario.get("description") or f"Клинический случай по протоколу: {p.title}."
                result = await svc.generate_reference_graph([p.id], title, description)
            except Exception as exc:
                print(f"  [skip] protocol {p.id} '{p.title[:40]}': {exc!r}")
                continue

            graph = result.get("graph") or {}
            try:
                schema = GraphSchema.model_validate(graph)
            except Exception as exc:
                stats["schema_failed"] += 1
                print(f"  [schema-fail] protocol {p.id} '{p.title[:40]}': {exc!r}")
                continue

            quality = judge_reference_graph(schema)
            rels = Counter((e.label.value if hasattr(e.label, "value") else str(e.label)).upper() for e in schema.edges)
            cats = Counter(n.data.category.value for n in schema.nodes)
            if cats.get("MONITORING"):
                safety["monitoring"] += 1
            if rels.get("CONTRAINDICATED_DUE_TO"):
                safety["contraindication"] += 1
            if rels.get("EXCLUDES"):
                safety["excludes"] += 1

            graph_status = "review_ready" if quality.get("critical_count", 0) == 0 else "draft"
            ref = ReferenceGraph(
                title=title,
                description=description,
                graph_data=schema.model_dump(),
                discipline_id=discipline.id,
                status=graph_status,
                source_type="auto_rebuild_v2",
                generation_context=[{"protocol_id": p.id, "protocol_title": p.title, "section": None, "protocol_year": p.year}],
                generation_quality=quality,
                validation_warnings=[f"{str(w.get('severity','')).upper()} {w.get('code','')}: {w.get('message','')}" for w in quality.get("warnings", [])],
            )
            session.add(ref)
            await session.commit()
            await session.refresh(ref)

            assignment = Assignment(
                title=title,
                description=description,
                discipline_id=discipline.id,
                reference_graph_id=ref.id,
                created_by_id=teacher.id if teacher else None,
                status=graph_status,
            )
            session.add(assignment)
            await session.commit()

            stats["graphs_created"] += 1
            if quality.get("accepted"):
                stats["accepted"] += 1
            print(f"  [ok] {p.id} '{title[:42]}' nodes={len(schema.nodes)} q={quality.get('quality_score')} accepted={quality.get('accepted')}")

        if args.delete_old and stats["graphs_created"] > 0:
            from sqlalchemy import delete
            await session.execute(delete(ReferenceGraph).where(ReferenceGraph.id.in_(old_ids)))
            await session.commit()
            print(f"deleted {len(old_ids)} old reference graphs (cascaded assignments/attempts).")

    print("STATS:", stats, "SAFETY_COVERAGE:", dict(safety))


if __name__ == "__main__":
    asyncio.run(main())
