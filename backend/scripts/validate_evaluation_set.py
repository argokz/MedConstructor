"""Phase v3 Step-3 validation over the clustered eval set (source_type eval_v3:*).

Measures, per cluster, the signals mapped to the three validation vectors:
  - branching / exclusion  -> EXCLUDES edges, CONTRAINDICATED_DUE_TO edges;
  - calculators / timings  -> numeric-label density (doses/thresholds/minutes);
  - surgery binary decision -> graphs with BOTH an operative (SURGERY) and a
    conservative (MEDICATION) branch;
  - cyclic titration        -> MONITORING nodes;
  - comorbidity conflict    -> the STEMI+T2DM case: both nosologies present +
    a contraindication/safety edge (conflict resolved).

Read-only; numbers come from stored graphs (no new LLM cost).
"""
import asyncio
import io
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models import ReferenceGraph

_SKIP = {"frame", "group"}
_DOSE = re.compile(r"\d+\s?(мг|мл|г|мкг|ед|ммоль|мин|час|сут|кг|%|мм\s?рт)", re.I)
_DIGIT = re.compile(r"\d")
_CLUSTER_ORDER = ["cardio", "neuro", "endo", "surgery", "peds", "comorbidity"]


def _nodes(g):
    return [n for n in (g or {}).get("nodes", []) if n.get("type") not in _SKIP]


def _cat(n):
    return str((n.get("data") or {}).get("category") or "").upper()


def _edges(g):
    return (g or {}).get("edges", [])


async def main(out_path):
    log = io.StringIO()

    def p(*a):
        print(*a, file=log)

    per = defaultdict(lambda: {"graphs": 0, "nodes": 0, "edges": 0, "excludes": 0,
                               "contra": 0, "monitoring": 0, "num_nodes": 0,
                               "dose_nodes": 0, "surg_decision": 0})
    async with AsyncSession(engine) as s:
        rows = list((await s.execute(
            select(ReferenceGraph).where(ReferenceGraph.source_type.like("eval_v3:%"))
            .order_by(ReferenceGraph.id))).scalars().all())
        comorbid = list((await s.execute(
            select(ReferenceGraph).where(ReferenceGraph.source_type == "eval_v3:comorbidity"))).scalars().all())

        for r in rows:
            cluster = (r.source_type or "").split(":", 1)[-1]
            g = r.graph_data or {}
            ns, es = _nodes(g), _edges(g)
            d = per[cluster]
            d["graphs"] += 1
            d["nodes"] += len(ns)
            d["edges"] += len(es)
            for e in es:
                lab = str(e.get("label") or "").upper()
                if lab == "EXCLUDES":
                    d["excludes"] += 1
                elif lab == "CONTRAINDICATED_DUE_TO":
                    d["contra"] += 1
            cats = [_cat(n) for n in ns]
            d["monitoring"] += cats.count("MONITORING")
            for n in ns:
                label = (n.get("data") or {}).get("label") or ""
                if _DIGIT.search(label):
                    d["num_nodes"] += 1
                if _DOSE.search(label):
                    d["dose_nodes"] += 1
            if "SURGERY" in cats and "MEDICATION" in cats:
                d["surg_decision"] += 1

        p("=== Step-3 signals per cluster (from stored generated graphs) ===")
        p(f"{'cluster':12} {'grf':>3} {'node':>5} {'edge':>5} {'EXCL':>5} {'CONTRA':>6} "
          f"{'MON':>4} {'num%':>5} {'dose':>5} {'surgDec':>7}")
        for cl in _CLUSTER_ORDER:
            d = per.get(cl)
            if not d or not d["graphs"]:
                continue
            numpct = 100 * d["num_nodes"] // max(1, d["nodes"])
            p(f"{cl:12} {d['graphs']:>3} {d['nodes']:>5} {d['edges']:>5} {d['excludes']:>5} "
              f"{d['contra']:>6} {d['monitoring']:>4} {numpct:>4}% {d['dose_nodes']:>5} {d['surg_decision']:>7}")

        # Comorbidity deep-dive
        p("\n=== Comorbidity conflict case (STEMI 489 + T2DM 1716) ===")
        for r in comorbid:
            g = r.graph_data or {}
            ns = _nodes(g)
            labels = " | ".join((n.get("data") or {}).get("label", "") for n in ns).lower()
            has_acute = any(k in labels for k in ["инфаркт", "коронар", "st", "тропонин", "реперфуз"])
            has_chronic = any(k in labels for k in ["диабет", "инсулин", "глюкоз", "гликем", "hba1c"])
            contra = sum(1 for e in _edges(g) if str(e.get("label") or "").upper() == "CONTRAINDICATED_DUE_TO")
            p(f"  A-graph {r.id}: nodes={len(ns)} acute_STEMI={has_acute} chronic_T2DM={has_chronic} "
              f"contraindication_edges={contra}")
            for n in ns:
                lab = (n.get("data") or {}).get("label", "")
                if any(k in lab.lower() for k in ["метформин", "контраст", "гипоглик", "отмен", "коррекц", "инсулин"]):
                    p(f"      conflict-node [{_cat(n)}]: {lab[:80]}")

    text = log.getvalue()
    print(text)
    if out_path:
        json.dump({k: dict(v) for k, v in per.items()}, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[summary -> {out_path}]")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    asyncio.run(main(ap.parse_args().out))
