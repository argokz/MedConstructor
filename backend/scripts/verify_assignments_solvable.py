"""Phase 2 verification: every assignment is correct and solvable.

For each assignment:
  - build the constructor palette (as the student sees it);
  - confirm EVERY reference-graph block is present in the palette
    (source of the "unsolvable" bug we fixed);
  - report the judge quality (schema/connectivity/safety) of the reference graph.

Read-only. Prints a per-assignment table + totals; JSON summary to
--out for the evaluation doc.
"""
import argparse
import asyncio
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import Assignment, ReferenceGraph  # noqa: E402
from app.schemas import GraphSchema  # noqa: E402
from app.services.concept_palette import _GRAPH_CATEGORY_TO_DB, build_assignment_palette  # noqa: E402
from app.services.graph_generation_judge import judge_reference_graph  # noqa: E402

_SKIP = {"frame", "group"}


def _ref_blocks(graph_data):
    blocks = []
    for node in (graph_data or {}).get("nodes", []):
        if node.get("type") in _SKIP:
            continue
        d = node.get("data") or {}
        cat = str(d.get("category") or "").upper().strip()
        label = (d.get("label") or "").strip()
        if cat and label and _GRAPH_CATEGORY_TO_DB.get(cat):
            blocks.append((cat, label))
    return blocks


async def main(out_path):
    log = io.StringIO()

    def p(*a):
        print(*a, file=log)

    summary = []
    async with AsyncSession(engine) as s:
        assignments = list((await s.execute(select(Assignment).order_by(Assignment.id))).scalars().all())
        p(f"Assignments: {len(assignments)}\n")
        p(f"{'id':>4}  {'title':40}  {'blocks':>6} {'inPal':>6} {'miss':>5}  {'edges':>5}  judge")
        tot_blocks = tot_present = tot_missing = 0
        accepted = 0

        for a in assignments:
            ref = await s.get(ReferenceGraph, a.reference_graph_id)
            if not ref:
                continue
            gd = ref.graph_data if isinstance(ref.graph_data, dict) else {}
            ref_blocks = _ref_blocks(gd)

            res = await build_assignment_palette(s, a, ref, per_category=30)
            palette = {(it["category"], it["label"].strip().lower()) for it in res["items"]}

            missing = [(c, l) for (c, l) in ref_blocks if (c, l.strip().lower()) not in palette]
            present = len(ref_blocks) - len(missing)

            try:
                schema = GraphSchema.model_validate(gd)
                q = judge_reference_graph(schema)
                jscore = q.get("quality_score")
                jok = q.get("accepted")
                edges = len(schema.edges)
            except Exception as exc:  # noqa: BLE001
                jscore, jok, edges = None, False, 0
                p(f"  [schema-fail {a.id}] {exc}")

            tot_blocks += len(ref_blocks)
            tot_present += present
            tot_missing += len(missing)
            accepted += 1 if jok else 0

            p(f"{a.id:>4}  {a.title[:40]:40}  {len(ref_blocks):>6} {present:>6} {len(missing):>5}  {edges:>5}  q={jscore} ok={jok}")
            for c, l in missing:
                p(f"       MISSING FROM PALETTE: [{c}] {l}")
            summary.append({
                "id": a.id, "title": a.title, "blocks": len(ref_blocks),
                "in_palette": present, "missing": len(missing),
                "edges": edges, "judge_score": jscore, "accepted": bool(jok),
            })

        p(f"\nTOTAL: blocks={tot_blocks} in_palette={tot_present} missing={tot_missing} "
          f"| judge-accepted {accepted}/{len(assignments)}")
        p(f"SOLVABLE (0 missing per assignment): "
          f"{sum(1 for x in summary if x['missing']==0)}/{len(summary)}")

    text = log.getvalue()
    print(text)
    if out_path:
        json.dump(summary, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[summary JSON -> {out_path}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    asyncio.run(main(args.out))
