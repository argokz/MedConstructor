"""Threshold sweep for catalog dedup — one ANN pass, cluster counts at several
cosine thresholds, plus sample clusters at a chosen threshold. Read-only.

Helps pick a safe threshold: 0.90 over-merges sibling concepts (КТ грудной ↔
брюшной), so we need to see where merges become only near-identical.
"""
import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402

_CATALOG_SOURCES = (
    "protocols", "clinical_protocols", "medelement_terms", "medelement",
    "protocol_graph", "protocol_extracted",
)
_CATEGORIES = (
    "patient_profile", "symptom", "exam", "lab_test", "instrumental_test",
    "disease", "medication", "surgery", "monitoring",
)
_THRESHOLDS = (0.92, 0.94, 0.95, 0.96, 0.97)


class _UF:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[rb] = ra


def _count(pairs, ids, thr):
    uf = _UF()
    for a, b, s in pairs:
        if s >= thr:
            uf.union(a, b)
    clusters = defaultdict(list)
    for i in ids:
        clusters[uf.find(i)].append(i)
    multi = [c for c in clusters.values() if len(c) > 1]
    return len(multi), sum(len(c) - 1 for c in multi)


async def main(topk, sample_thr, sample_n):
    async with engine.connect() as conn:
        await conn.execute(text("SET enable_seqscan=off"))
        totals = {t: [0, 0] for t in _THRESHOLDS}
        sample_lines = []
        for cat in _CATEGORIES:
            rows = (await conn.execute(text(
                "SELECT id, name, source FROM medical_nodes "
                "WHERE category=:c AND source=ANY(:s) AND embedding IS NOT NULL"),
                {"c": cat, "s": list(_CATALOG_SOURCES)})).all()
            nodes = {r.id: {"name": r.name, "source": r.source} for r in rows}
            ids = list(nodes)
            pairs = []
            for nid in ids:
                vec = (await conn.execute(text(
                    "SELECT embedding::text FROM medical_nodes WHERE id=:id"), {"id": nid})).scalar()
                nbs = (await conn.execute(text(
                    "SELECT id, 1-(embedding <=> (:v)::vector) AS sim FROM medical_nodes "
                    "WHERE id<>:id AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> (:v)::vector LIMIT :k"),
                    {"v": vec, "id": nid, "k": topk})).all()
                for nb in nbs:
                    if nb.id in nodes and nb.sim >= min(_THRESHOLDS):
                        pairs.append((nid, nb.id, nb.sim))
            line = [f"  {cat:18}"]
            for t in _THRESHOLDS:
                cl, rm = _count(pairs, ids, t)
                totals[t][0] += cl; totals[t][1] += rm
                line.append(f"{t}: {rm:4d}")
            print("  ".join(line))

            # sample clusters at sample_thr for this category
            uf = _UF()
            for a, b, s in pairs:
                if s >= sample_thr: uf.union(a, b)
            cm = defaultdict(list)
            for i in ids: cm[uf.find(i)].append(i)
            for c in sorted([c for c in cm.values() if len(c) > 1], key=len, reverse=True)[:sample_n]:
                canon = min(c, key=lambda i: (len(nodes[i]["name"]), nodes[i]["name"]))
                sample_lines.append(f"[{cat}] KEEP: {nodes[canon]['name']}")
                for i in c:
                    if i != canon:
                        sample_lines.append(f"     <- {nodes[i]['name']}")

        print("\n=== TOTAL duplicates removed by threshold ===")
        for t in _THRESHOLDS:
            print(f"  {t}: {totals[t][1]} dups in {totals[t][0]} clusters")
        print(f"\n=== SAMPLE clusters at threshold {sample_thr} ===")
        for ln in sample_lines:
            print(ln)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--sample-thr", type=float, default=0.95)
    ap.add_argument("--sample-n", type=int, default=4)
    args = ap.parse_args()
    asyncio.run(main(args.topk, args.sample_thr, args.sample_n))
