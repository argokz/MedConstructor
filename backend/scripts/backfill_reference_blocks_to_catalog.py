"""Backfill: ingest every reference-graph block into `medical_nodes`.

Reference graphs are generated from clinical protocols (their `generation_context`
links the source protocol_ids), but the LLM writes node labels as free text that
rarely matches the scraped MedElement catalog. As a result a task could reference
a block that does not exist in the palette → the task is literally unsolvable.

This script enforces the invariant "every reference block exists in the catalog"
by inserting each missing block as a protocol-sourced node:
    source     = "protocol_graph"
    external_id = "protocol:<id>"   (first protocol from generation_context)

Idempotent: a (lower(name), db_category) already present in ANY source is skipped.
Reversible: DELETE FROM medical_nodes WHERE source = 'protocol_graph'.

Usage:  python scripts/backfill_reference_blocks_to_catalog.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import MedicalNode, ReferenceGraph  # noqa: E402

# Graph category -> medical_nodes.category. MONITORING is kept distinct (it used
# to collapse into "exam"); the palette read path maps it the same way.
_GRAPH_CATEGORY_TO_DB = {
    "PATIENT_PROFILE": "patient_profile",
    "SYMPTOM": "symptom",
    "EXAM": "exam",
    "LAB_TEST": "lab_test",
    "INSTRUMENTAL_TEST": "instrumental_test",
    "MEDICATION": "medication",
    "SURGERY": "surgery",
    "DIAGNOSIS": "disease",
    "DISEASE": "disease",
    "MONITORING": "monitoring",
}

_SKIP_NODE_TYPES = frozenset({"frame", "group"})
_SOURCE = "protocol_graph"


def _first_protocol_id(reference_graph: ReferenceGraph) -> int | None:
    ctx = reference_graph.generation_context
    if isinstance(ctx, list):
        for entry in ctx:
            if isinstance(entry, dict) and entry.get("protocol_id"):
                return int(entry["protocol_id"])
    return None


async def main(dry_run: bool) -> None:
    inserted = Counter()
    skipped = 0
    async with AsyncSession(engine) as session:
        # Existing (name_lower, category) pairs across ALL sources for dedupe.
        existing_rows = await session.execute(
            select(func.lower(MedicalNode.name), MedicalNode.category)
        )
        existing: set[tuple[str, str]] = {(n, c) for n, c in existing_rows.all()}

        graphs = list((await session.execute(select(ReferenceGraph))).scalars().all())
        new_in_run: set[tuple[str, str]] = set()

        for graph in graphs:
            protocol_id = _first_protocol_id(graph)
            external_id = f"protocol:{protocol_id}" if protocol_id else None
            graph_data = graph.graph_data if isinstance(graph.graph_data, dict) else {}

            for node in graph_data.get("nodes", []):
                if node.get("type") in _SKIP_NODE_TYPES:
                    continue
                data = node.get("data") or {}
                graph_category = str(data.get("category") or "").upper().strip()
                label = (data.get("label") or "").strip()
                db_category = _GRAPH_CATEGORY_TO_DB.get(graph_category)
                if not label or not db_category:
                    continue

                key = (label.lower(), db_category)
                if key in existing or key in new_in_run:
                    skipped += 1
                    continue

                new_in_run.add(key)
                inserted[db_category] += 1
                if not dry_run:
                    session.add(
                        MedicalNode(
                            name=label,
                            category=db_category,
                            external_id=external_id,
                            source=_SOURCE,
                        )
                    )

        if not dry_run:
            await session.commit()

    total = sum(inserted.values())
    print(f"{'[DRY RUN] ' if dry_run else ''}Inserted {total} new catalog nodes "
          f"(source={_SOURCE}); skipped {skipped} already present.")
    for category, count in sorted(inserted.items()):
        print(f"  {category:20} +{count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
