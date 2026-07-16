"""Repair detached sub-graphs in stored reference graphs.

Uses the SAME connectivity repair as the generation pipeline
(`repair_graph_connectivity`): reconnects each detached island's entry node to
the main clinical chain with a clinically-valid edge, or prunes it when no
defensible bridge exists. Re-judges afterwards and refreshes
generation_quality / validation_warnings.

Dry-run by default (prints what WOULD change). Pass --apply to persist.

    cd backend
    python scripts/fix_detached_reference_graphs.py            # dry run (report)
    python scripts/fix_detached_reference_graphs.py --apply    # write changes
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
from app.services.graph_generation_judge import (
    judge_reference_graph,
    repair_graph_connectivity,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Repair detached sub-graphs in reference graphs.")
    parser.add_argument("--apply", action="store_true", help="Persist changes (default: dry run).")
    args = parser.parse_args()

    stats = {"total": 0, "detached": 0, "reconnected_edges": 0, "pruned_nodes": 0, "updated": 0}

    async with AsyncSessionLocal() as session:
        refs = (await session.execute(select(ReferenceGraph))).scalars().all()
        for ref in refs:
            stats["total"] += 1
            data = ref.graph_data or {}
            nodes = list(data.get("nodes", []))
            edges = list(data.get("edges", []))
            if not nodes:
                continue

            new_nodes, new_edges, actions = repair_graph_connectivity(nodes, edges)
            if not actions:
                continue

            stats["detached"] += 1
            reconnected = [a for a in actions if a["type"] == "reconnected"]
            pruned = [a for a in actions if a["type"] == "pruned"]
            stats["reconnected_edges"] += len(reconnected)
            stats["pruned_nodes"] += sum(len(a["node_ids"]) for a in pruned)

            print(f"\n#{ref.id} '{(ref.title or '')[:50]}'")
            for a in reconnected:
                e = a["edge"]
                print(f"   reconnect: '{a['entry_label']}'  ({e['source']}→{e['target']} {e['label']})")
            for a in pruned:
                print(f"   prune:     {', '.join(str(x) for x in a['labels'])}")

            if args.apply:
                schema = GraphSchema.model_validate({"nodes": new_nodes, "edges": new_edges})
                quality = judge_reference_graph(schema)
                ref.graph_data = schema.model_dump()
                ref.generation_quality = quality
                ref.validation_warnings = [
                    f"{str(w.get('severity','')).upper()} {w.get('code','')}: {w.get('message','')}"
                    for w in quality.get("warnings", [])
                ]
                # A repaired graph carries auto-added edges — send it back for review.
                ref.status = "draft"
                stats["updated"] += 1

        if args.apply:
            await session.commit()

    print("\nSTATS:", stats)
    print("DRY RUN — no changes written. Re-run with --apply to persist." if not args.apply
          else "Changes committed. Repaired graphs set to status='draft' for teacher review.")


if __name__ == "__main__":
    asyncio.run(main())
