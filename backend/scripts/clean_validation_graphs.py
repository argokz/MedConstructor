"""Connect disconnected clinical clusters in cardiology validation graphs.

Some references contain a differential-diagnosis / exclusion cluster (internally
linked via EXCLUDES) that is not attached to the main clinical chain, so it reads
as a separate floating graph. Per the expert-panel requirement (every block
connected, no separate sub-graphs), this attaches each disconnected cluster to the
main graph with a single DETERMINES edge from a main-graph anchor (patient profile
/ symptom) to the cluster's entry node. The SAME edge is added to the reference and
to every variant's student graph, so it never changes the difference between them
(designed error variants keep their score). Metrics are recomputed.

    cd backend
    python scripts/clean_validation_graphs.py            # dry run
    python scripts/clean_validation_graphs.py --apply    # write
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ValidationVariant
from app.schemas import GraphSchema
from app.services.graph_evaluator import GraphEvaluator

METRIC_KEYS = (
    "edge_f1", "weighted_edge_f1", "node_coverage", "category_accuracy",
    "directed_path_completeness", "safety_penalty", "unsafe_extra_action",
    "missing_critical_action", "diagnostic_evidence_gap", "clinical_connectivity_gap", "composite_score",
)
ANCHOR_PRIORITY = ["PATIENT_PROFILE", "SYMPTOM", "DIAGNOSIS", "EXAM"]


def _category(node: dict) -> str:
    return str((node.get("data") or {}).get("category") or node.get("category") or "").upper()


def _components(graph: dict) -> list[set[str]]:
    nodes = [str(n.get("id")) for n in graph.get("nodes", [])]
    id_set = set(nodes)
    adj: dict[str, set[str]] = defaultdict(set)
    for e in graph.get("edges", []):
        s, t = str(e.get("source")), str(e.get("target"))
        if s in id_set and t in id_set:
            adj[s].add(t); adj[t].add(s)
    seen: set[str] = set(); comps: list[set[str]] = []
    for n in nodes:
        if n in seen:
            continue
        stack, comp = [n], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.add(x); stack.extend(adj[x] - seen)
        comps.append(comp)
    return comps


def _connecting_edges(reference: dict) -> list[dict]:
    """Compute DETERMINES edges (main anchor -> cluster entry) to attach every
    disconnected cluster of the reference to its main component."""
    nodes = reference.get("nodes", [])
    by_id = {str(n.get("id")): n for n in nodes}
    comps = _components(reference)
    if len(comps) <= 1:
        return []
    diag = {i for i, n in by_id.items() if _category(n) == "DIAGNOSIS"}
    main = max(comps, key=lambda c: (1 if c & diag else 0, len(c)))

    def pick(ids: set[str], priority: list[str]) -> str | None:
        for cat in priority:
            for i in sorted(ids):
                if _category(by_id.get(i, {})) == cat:
                    return i
        return next(iter(sorted(ids)), None)

    # Incoming degree within cluster to prefer an "entry" (root) node.
    indeg: dict[str, int] = defaultdict(int)
    for e in reference.get("edges", []):
        indeg[str(e.get("target"))] += 1

    main_anchor = pick(main, ANCHOR_PRIORITY)
    edges: list[dict] = []
    for comp in comps:
        if comp is main or not main_anchor:
            continue
        # entry = cluster node with lowest in-degree (prefer exam/symptom-like)
        entry = min(sorted(comp), key=lambda i: (indeg[i], 0 if _category(by_id.get(i, {})) in ("EXAM", "SYMPTOM", "LAB_TEST", "INSTRUMENTAL_TEST") else 1))
        edges.append({
            "id": f"auto_link_{main_anchor}_{entry}",
            "source": main_anchor,
            "target": entry,
            "label": "DETERMINES",
        })
    return edges


def _add_edges(graph: dict, edges: list[dict]) -> dict:
    if not edges:
        return graph
    ids = {str(n.get("id")) for n in graph.get("nodes", [])}
    existing = {(str(e.get("source")), str(e.get("target"))) for e in graph.get("edges", [])}
    add = [
        e for e in edges
        if str(e["source"]) in ids and str(e["target"]) in ids
        and (str(e["source"]), str(e["target"])) not in existing
    ]
    if not add:
        return graph
    return {**graph, "edges": [*graph.get("edges", []), *add]}


def _stats(graph: dict) -> tuple[int, int]:
    comps = _components(graph)
    nodes = [str(n.get("id")) for n in graph.get("nodes", [])]
    deg: dict[str, int] = defaultdict(int)
    ids = set(nodes)
    for e in graph.get("edges", []):
        if str(e.get("source")) in ids and str(e.get("target")) in ids:
            deg[str(e["source"])] += 1; deg[str(e["target"])] += 1
    orphans = sum(1 for n in nodes if deg[n] == 0)
    return orphans, len(comps)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Connect disconnected clusters in validation graphs.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cohort", default="cardiology_pilot")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        variants = (await session.execute(
            select(ValidationVariant).where(
                ValidationVariant.cohort == args.cohort, ValidationVariant.is_active == 1
            )
        )).scalars().all()

        by_case: dict[str, list[ValidationVariant]] = defaultdict(list)
        for v in variants:
            by_case[v.case_id].append(v)

        cases_fixed = updated = 0
        for case_id, group in by_case.items():
            edges = _connecting_edges(group[0].reference_graph or {})
            if not edges:
                continue
            cases_fixed += 1
            for v in group:
                student_new = _add_edges(v.student_graph or {}, edges)
                ref_new = _add_edges(v.reference_graph or {}, edges)
                new_metrics = dict(v.model_metrics or {})
                try:
                    metrics = GraphEvaluator.evaluate(
                        GraphSchema.model_validate(student_new),
                        GraphSchema.model_validate(ref_new),
                    )
                    new_metrics.update({k: metrics[k] for k in METRIC_KEYS if k in metrics})
                except Exception as exc:
                    print(f"  [warn] eval {v.case_id}/{v.variant_id}: {exc!r}")
                o, c = _stats(ref_new)
                print(f"  {v.case_id}/{v.variant_id}: +{len(edges)} edge(s) ref(orphans={o},comps={c}) composite={new_metrics.get('composite_score')}")
                if args.apply:
                    v.student_graph = student_new
                    v.reference_graph = ref_new
                    v.model_metrics = new_metrics
                    updated += 1
        if args.apply:
            await session.commit()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] cases_connected={cases_fixed} variants_updated={updated}")


if __name__ == "__main__":
    asyncio.run(main())
