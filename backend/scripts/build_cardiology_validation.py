"""Build the cardiology blinded-validation benchmark for the 5-expert panel.

For each cardiology protocol: (re)generate a reference graph with retries (keep
the highest-quality attempt), then emit a case with a correct variant + balanced
error variants, each scored by GraphEvaluator (model_metrics). Output matches the
format expected by load_validation_variants.py:

    { "cardiology": { "cases": [...], "graph": {"results": [...]} } }

Usage:
    python scripts/build_cardiology_validation.py --retries 3 \
        --out benchmarks/cardiology_v3_validation.json
    python scripts/load_validation_variants.py \
        --benchmark benchmarks/cardiology_v3_validation.json --cohort cardiology_pilot --per-case 3
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import AsyncSessionLocal
from app.models import ClinicalProtocol
from app.schemas import GraphSchema
from app.services.graph_evaluator import GraphEvaluator
from app.services.graph_generation_judge import judge_reference_graph
from app.services.rag_service import RAGService

CARDIO = [
    (489, "cardio_stemi"),
    (495, "cardio_nste_acs"),
    (502, "cardio_af"),
    (501, "cardio_pe"),
    (829, "cardio_htn_crisis"),
    (504, "cardio_chf"),
    (494, "cardio_endocarditis"),
    (490, "cardio_pah"),
    (482, "cardio_htn"),
    (529, "cardio_myocarditis"),
    (487, "cardio_vt"),
    (832, "cardio_shock"),
]

_SKIP = {"frame", "group"}
_DIAG_SRC = {"LAB_TEST", "INSTRUMENTAL_TEST", "EXAM", "SYMPTOM"}
_TREAT = {"MEDICATION", "SURGERY"}


def _by_id(g):
    return {n.get("id"): n for n in g.get("nodes", [])}


def _cat(by_id, nid):
    return str((by_id.get(nid, {}).get("data") or {}).get("category") or "").upper()


def _variant(graph, kind):
    """Produce an error variant of the reference graph."""
    g = copy.deepcopy(graph)
    nodes, edges = g.get("nodes", []), g.get("edges", [])
    by_id = _by_id(g)
    if kind == "missing_key_diagnostic_step":
        edges = [e for e in edges if not (_cat(by_id, e.get("target")) == "DIAGNOSIS"
                                          and _cat(by_id, e.get("source")) in _DIAG_SRC)]
    elif kind == "missing_critical_action":
        dropped = False
        kept = []
        for e in edges:
            if not dropped and (_cat(by_id, e.get("source")) in _TREAT or _cat(by_id, e.get("target")) in _TREAT):
                dropped = True
                continue
            kept.append(e)
        edges = kept
    elif kind == "wrong_node_category":
        for n in nodes:
            d = n.get("data") or {}
            if str(d.get("category") or "").upper() == "MEDICATION":
                d["category"] = "SYMPTOM"  # miscategorise a therapy as a symptom
                break
    elif kind == "broken_reasoning_chain":
        # sever the diagnosis -> treatment links (chain break)
        edges = [e for e in edges if not (_cat(by_id, e.get("source")) == "DIAGNOSIS"
                                          and _cat(by_id, e.get("target")) in _TREAT)]
    g["nodes"], g["edges"] = nodes, edges
    return g


ERROR_KINDS = ["missing_key_diagnostic_step", "missing_critical_action",
               "broken_reasoning_chain", "wrong_node_category"]


async def _best_graph(svc, session, pid, retries):
    pr = await session.get(ClinicalProtocol, pid)
    scenarios = await svc.generate_scenarios([pid])
    scenario = scenarios[0] if scenarios else {"title": pr.title, "description": f"Случай: {pr.title}."}
    title = scenario.get("title") or pr.title
    description = scenario.get("description") or f"Случай: {pr.title}."
    best = None
    for _ in range(max(1, retries)):
        try:
            result = await svc.generate_reference_graph([pid], title, description)
            graph = result.get("graph") or {}
            schema = GraphSchema.model_validate(graph)
            q = judge_reference_graph(schema)
            score = q.get("quality_score") or 0.0
            if best is None or score > best[0]:
                best = (score, schema.model_dump(), q)
            if q.get("accepted"):
                break
        except Exception as exc:  # noqa: BLE001
            print(f"    [attempt fail {pid}] {exc}")
    return title, description, best


async def main(retries, out_path):
    cases = []
    results = []
    async with AsyncSessionLocal() as session:
        svc = RAGService(session)
        for pid, slug in CARDIO:
            title, description, best = await _best_graph(svc, session, pid, retries)
            if not best:
                print(f"  [skip {pid}] no valid graph")
                continue
            score, ref_graph, quality = best
            ref_schema = GraphSchema.model_validate(ref_graph)
            case_id = f"{slug}_{pid}"

            variants = [{
                "variant_id": "correct_reference_solution",
                "expected_pattern": "all_metrics_high",
                "description": "Полное протокол-обоснованное решение.",
                "student_graph": "__same_as_reference__",
            }]
            # correct metrics
            m = GraphEvaluator.evaluate(ref_schema, ref_schema)
            results.append({"case_id": case_id, "variant_id": "correct_reference_solution", "metrics": m})
            for kind in ERROR_KINDS:
                vg = _variant(ref_graph, kind)
                try:
                    vs = GraphSchema.model_validate(vg)
                    vm = GraphEvaluator.evaluate(vs, ref_schema)
                except Exception:
                    continue
                variants.append({
                    "variant_id": kind, "expected_pattern": kind,
                    "description": "Вариант с типовой ошибкой.", "student_graph": vg,
                })
                results.append({"case_id": case_id, "variant_id": kind, "metrics": vm})

            cases.append({
                "case_id": case_id, "title": title, "protocol_area": "cardiology",
                "task": {"description": description},
                "reference_graph": ref_graph, "variants": variants,
                "source_protocol": pid,
            })
            print(f"  [ok] {pid} {title[:38]!r} q={score} variants={len(variants)}")

    benchmark = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cardiology": {"cases": cases, "graph": {"results": results}},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(benchmark, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nWrote {len(cases)} cases, {len(results)} scored variants -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--out", default="benchmarks/cardiology_v3_validation.json")
    args = ap.parse_args()
    asyncio.run(main(args.retries, args.out))
