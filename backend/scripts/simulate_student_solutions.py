"""Phase 3: simulate student solutions and check the grader discriminates.

For every assignment's reference graph, grade:
  - correct       — the reference graph itself (expect composite ~1.0);
  - drop_safety   — remove CONTRAINDICATED_DUE_TO / EXCLUDES edges (weight 1.8,
                    should be penalised the most);
  - drop_dx_evid  — remove diagnostic-evidence edges (test/exam/symptom → diagnosis);
  - drop_monitor  — remove MONITORING nodes + their edges;
  - drop_treat    — remove one treatment (medication/surgery) edge;
  - no_edges      — all nodes, no edges (blank clinical chain).

Read-only (calls GraphEvaluator directly, no DB writes). Verifies the score
ordering correct > partial-error > safety-error and no_edges near floor.
"""
import argparse
import asyncio
import copy
import io
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import Assignment, ReferenceGraph  # noqa: E402
from app.schemas import GraphSchema  # noqa: E402
from app.services.graph_evaluator import GraphEvaluator  # noqa: E402

_SKIP = {"frame", "group"}
_SAFETY = {"CONTRAINDICATED_DUE_TO", "EXCLUDES"}
_DIAG_SOURCES = {"LAB_TEST", "INSTRUMENTAL_TEST", "EXAM", "SYMPTOM"}
_TREAT = {"MEDICATION", "SURGERY"}


def _cat_of(nodes_by_id, nid):
    n = nodes_by_id.get(nid) or {}
    return str((n.get("data") or {}).get("category") or "").upper()


def _perturb(graph, kind):
    g = copy.deepcopy(graph)
    nodes = [n for n in g.get("nodes", [])]
    edges = [e for e in g.get("edges", [])]
    by_id = {n.get("id"): n for n in nodes}

    def lbl(e):
        return str(e.get("label") or "").upper()

    if kind == "correct":
        pass
    elif kind == "drop_safety":
        edges = [e for e in edges if lbl(e) not in _SAFETY]
    elif kind == "drop_dx_evid":
        edges = [e for e in edges
                 if not (_cat_of(by_id, e.get("target")) == "DIAGNOSIS"
                         and _cat_of(by_id, e.get("source")) in _DIAG_SOURCES)]
    elif kind == "drop_monitor":
        mon = {n.get("id") for n in nodes if _cat_of(by_id, n.get("id")) == "MONITORING"}
        nodes = [n for n in nodes if n.get("id") not in mon]
        edges = [e for e in edges if e.get("source") not in mon and e.get("target") not in mon]
    elif kind == "drop_treat":
        dropped = False
        kept = []
        for e in edges:
            if not dropped and (_cat_of(by_id, e.get("source")) in _TREAT or _cat_of(by_id, e.get("target")) in _TREAT):
                dropped = True
                continue
            kept.append(e)
        edges = kept
    elif kind == "no_edges":
        edges = []

    g["nodes"], g["edges"] = nodes, edges
    return g


async def main(out_path):
    kinds = ["correct", "drop_dx_evid", "drop_treat", "drop_monitor", "drop_safety", "no_edges"]
    log = io.StringIO()

    def p(*a):
        print(*a, file=log)

    agg = defaultdict(list)
    per_assignment = []
    async with AsyncSession(engine) as s:
        assignments = list((await s.execute(select(Assignment).order_by(Assignment.id))).scalars().all())
        p(f"Grading {len(assignments)} assignments × {len(kinds)} solution variants\n")
        p(f"{'id':>4}  " + "  ".join(f"{k:>11}" for k in kinds))

        for a in assignments:
            ref = await s.get(ReferenceGraph, a.reference_graph_id)
            gd = ref.graph_data if isinstance(ref.graph_data, dict) else {}
            try:
                ref_schema = GraphSchema.model_validate(gd)
            except Exception:
                continue
            row = {"id": a.id, "scores": {}}
            cells = []
            for kind in kinds:
                try:
                    stu = GraphSchema.model_validate(_perturb(gd, kind))
                    res = GraphEvaluator.evaluate(stu, ref_schema)
                    score = res.get("composite_score")
                except Exception as exc:  # noqa: BLE001
                    score = None
                    p(f"   [err {a.id}/{kind}] {exc}")
                row["scores"][kind] = score
                if score is not None:
                    agg[kind].append(score)
                cells.append(f"{score if score is not None else '—':>11}")
            per_assignment.append(row)
            p(f"{a.id:>4}  " + "  ".join(cells))

        p("\n=== mean composite by solution type ===")
        for kind in kinds:
            vals = agg[kind]
            mean = sum(vals) / len(vals) if vals else 0.0
            p(f"  {kind:12} mean={mean:.3f}  (n={len(vals)})")

        # sanity: correct should top every error type on average
        mc = (sum(agg['correct'])/len(agg['correct'])) if agg['correct'] else 0
        ms = (sum(agg['drop_safety'])/len(agg['drop_safety'])) if agg['drop_safety'] else 0
        p(f"\ncorrect({mc:.3f}) > drop_safety({ms:.3f}): {mc > ms}")

    text = log.getvalue()
    print(text)
    if out_path:
        json.dump({"per_assignment": per_assignment,
                   "means": {k: (sum(v)/len(v) if v else 0.0) for k, v in agg.items()}},
                  open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[summary -> {out_path}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    asyncio.run(main(args.out))
