"""Build the article evaluation set: 5 clusters x 5 protocols + 1 comorbidity case.

Each cluster targets a distinct clinical-logic type. For every protocol the
pipeline generates a task (scenario) and a reference-graph "solution", storing in
Postgres: the task text (Assignment.description), the RAG chunks the LLM relied
on (ReferenceGraph.generation_context, now incl. text), and the generated
solution (ReferenceGraph.graph_data). Tagged by cluster via source_type.

Also writes docs/eval_data/eval_set_manifest.json (authoritative mapping).

Usage:  python scripts/build_evaluation_set.py            # delete old + build
        python scripts/build_evaluation_set.py --keep-old
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models import Assignment, ClinicalProtocol, Discipline, ReferenceGraph, User
from app.schemas import GraphSchema
from app.services.graph_generation_judge import judge_reference_graph
from app.services.rag_service import RAGService

# cluster -> (logic_type, [protocol_ids])
CLUSTERS = {
    "cardio":  ("hard_thresholds_timing",             [489, 495, 502, 501, 829]),
    "neuro":   ("branching_exclusion",                [678, 689, 671, 696, 673]),
    "endo":    ("cyclic_titration",                   [1715, 1716, 1718, 1702, 1708]),
    "surgery": ("binary_conservative_vs_operative",   [1667, 1670, 1669, 1666, 236]),
    "peds":    ("dynamic_weight_age",                 [1257, 160, 368, 1271, 870]),
}
COMORBID = [([489, 1716], "acute_over_chronic_conflict")]  # ОИМ (urgent) + СД2 (chronic)

_MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "..", "docs", "eval_data", "eval_set_manifest.json")


async def _discipline(session) -> Discipline:
    d = (await session.execute(select(Discipline).where(Discipline.name == "Общая медицина"))).scalars().first()
    if not d:
        d = Discipline(name="Общая медицина", code="GM01")
        session.add(d)
        await session.commit()
        await session.refresh(d)
    return d


async def _build_one(session, svc, discipline, teacher, protocol_ids, cluster, logic_type):
    titles = []
    for pid in protocol_ids:
        pr = await session.get(ClinicalProtocol, pid)
        titles.append(pr.title if pr else str(pid))
    scenarios = await svc.generate_scenarios(protocol_ids)
    scenario = scenarios[0] if scenarios else {"title": titles[0], "description": f"Клинический случай по протоколу: {titles[0]}."}
    title = scenario.get("title") or titles[0]
    description = scenario.get("description") or f"Клинический случай по протоколу: {titles[0]}."

    result = await svc.generate_reference_graph(protocol_ids, title, description)
    graph = result.get("graph") or {}
    schema = GraphSchema.model_validate(graph)
    quality = judge_reference_graph(schema)
    status = "review_ready" if quality.get("critical_count", 0) == 0 else "draft"

    ref = ReferenceGraph(
        title=title, description=description, graph_data=schema.model_dump(),
        discipline_id=discipline.id, status=status,
        source_type=f"eval_v3:{cluster}",
        generation_context=result.get("generation_context") or [],
        generation_quality=quality,
        review_notes=f"cluster={cluster}; logic={logic_type}; protocols={protocol_ids}",
    )
    session.add(ref)
    await session.commit()
    await session.refresh(ref)

    assignment = Assignment(
        title=title, description=description, discipline_id=discipline.id,
        reference_graph_id=ref.id, created_by_id=teacher.id if teacher else None,
        status=status, review_notes=f"cluster={cluster}; logic={logic_type}",
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)

    return {
        "assignment_id": assignment.id, "reference_graph_id": ref.id,
        "cluster": cluster, "logic_type": logic_type,
        "protocol_ids": protocol_ids, "protocol_titles": titles,
        "task_title": title, "nodes": len(schema.nodes), "edges": len(schema.edges),
        "rag_chunks": len(ref.generation_context or []),
        "quality_score": quality.get("quality_score"), "accepted": quality.get("accepted"),
    }


async def main(keep_old: bool) -> None:
    manifest = []
    async with AsyncSessionLocal() as session:
        svc = RAGService(session)
        discipline = await _discipline(session)
        teacher = (await session.execute(select(User).where(User.role == "teacher"))).scalars().first()

        if not keep_old:
            old = [r for (r,) in (await session.execute(select(ReferenceGraph.id))).all()]
            await session.execute(delete(ReferenceGraph).where(ReferenceGraph.id.in_(old)))
            await session.commit()
            print(f"deleted {len(old)} old reference graphs (+cascaded assignments).")

        for cluster, (logic_type, pids) in CLUSTERS.items():
            for pid in pids:
                try:
                    rec = await _build_one(session, svc, discipline, teacher, [pid], cluster, logic_type)
                    manifest.append(rec)
                    print(f"  [{cluster}] {pid} -> A{rec['assignment_id']} "
                          f"nodes={rec['nodes']} q={rec['quality_score']} acc={rec['accepted']}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  [skip {cluster}/{pid}] {exc!r}")

        for pids, logic_type in COMORBID:
            try:
                rec = await _build_one(session, svc, discipline, teacher, pids, "comorbidity", logic_type)
                manifest.append(rec)
                print(f"  [comorbidity] {pids} -> A{rec['assignment_id']} nodes={rec['nodes']} q={rec['quality_score']}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [skip comorbidity/{pids}] {exc!r}")

    os.makedirs(os.path.dirname(_MANIFEST), exist_ok=True)
    json.dump(manifest, open(_MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nBuilt {len(manifest)} assignments. Manifest -> docs/eval_data/eval_set_manifest.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-old", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.keep_old))
