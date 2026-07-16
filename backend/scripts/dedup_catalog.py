"""Embedding-based near-duplicate dedup for the medical_nodes catalog.

Lemma-key dedup (during extraction) already collapsed morphological/word-order
duplicates. This pass catches *semantic* near-duplicates with different lemmas
(«ЭКГ» ≈ «электрокардиография», «УЗИ брюшной полости» ≈ «ультразвуковое
исследование органов брюшной полости») via cosine similarity of the OpenAI
text-embedding-3-small vectors, within the same category.

Two-phase by design:
  --dry-run (default): report candidate merge clusters for human review.
  --apply           : merge each cluster into a canonical node — repoint
                      medical_edges to the canonical, delete the duplicates.

Canonical selection prefers provenance we must not lose: reference blocks
(protocol_graph) and curated MedElement terms outrank bulk protocol_extracted;
ties broken by shortest name. So a reference answer-key block is never merged
away in favour of an LLM-extracted variant (keeps tasks solvable).

Requires all catalog nodes to be embedded first: python scripts/vectorize_new_nodes.py
"""
import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402
from app.services import morphology  # noqa: E402

# Guard: two names at cosine>=threshold are still NOT merged if they differ by a
# clinically-critical token — the failure mode of embeddings (гепатит D↔B, IgG↔
# IgM, головной↔спинной, II↔III, 45↔55 лет all sit at 0.95-0.99 similarity).
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_ROMAN = frozenset({"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"})
_IG_RE = re.compile(r"^ig[gmade]$")
# Lemmas whose presence-on-one-side flips clinical meaning (anatomy, laterality,
# severity, route, ordinality, temporality, specialist, …).
_CRITICAL_LEMMAS = frozenset({
    "головной", "спинной", "грудной", "брюшной", "лёгочный", "легочный",
    "левый", "правый", "верхний", "нижний", "передний", "задний",
    "левосторонний", "правосторонний", "двусторонний", "односторонний",
    "проксимальный", "дистальный", "восходящий", "нисходящий",
    "шейный", "поясничный", "крестцовый", "грудный",
    "открытый", "закрытый", "острый", "хронический", "подострый",
    "первичный", "вторичный", "третичный", "первый", "второй", "третий",
    "четвёртый", "четвертый",
    "доброкачественный", "злокачественный", "инвазивный", "неинвазивный",
    "тотальный", "субтотальный", "частичный", "полный",
    "артериальный", "венозный", "систолический", "диастолический", "пульсовой",
    "наркотический", "ненаркотический",
    "внутривенный", "внутримышечный", "подкожный", "пероральный", "внутрикожный",
    "психиатр", "психолог", "психотерапевт", "психиатрический", "психологический",
    "психический", "неврологический", "нервный",
    "мужской", "женский", "детский", "взрослый",
    "лечебный", "диагностический", "профилактический",
    "корригированный", "некорригированный",
})


def _tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(name or "")}


def _is_discriminator(token: str) -> bool:
    if len(token) == 1:
        return True
    if any(ch.isdigit() for ch in token):
        return True
    if token in _ROMAN or _IG_RE.match(token):
        return True
    if token in _CRITICAL_LEMMAS:
        return True
    lemma = morphology.lemmatize_word(token)
    return bool(lemma and lemma in _CRITICAL_LEMMAS)


def _blocked(name_a: str, name_b: str) -> bool:
    """True if the two names differ by a clinically-critical token (do NOT merge)."""
    symdiff = _tokens(name_a) ^ _tokens(name_b)
    return any(_is_discriminator(t) for t in symdiff)

_CATALOG_SOURCES = (
    "protocols", "clinical_protocols", "medelement_terms", "medelement",
    "protocol_graph", "protocol_extracted",
)
# Lower rank = stronger claim to be the canonical (kept) node.
_SOURCE_RANK = {
    "protocol_graph": 0,      # reference answer-key blocks — never merge away
    "medelement": 1,          # curated
    "medelement_terms": 1,
    "clinical_protocols": 2,
    "protocols": 2,
    "protocol_extracted": 3,  # bulk LLM extraction — merge into better sources
}
_CATEGORIES = (
    "patient_profile", "symptom", "exam", "lab_test", "instrumental_test",
    "disease", "medication", "surgery", "monitoring",
)


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


async def _ensure_index(conn) -> None:
    exists = (await conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE tablename='medical_nodes' AND indexname='ix_medical_nodes_embedding_hnsw'"
    ))).first()
    if exists:
        return
    print("Building HNSW index on medical_nodes.embedding (one-time)...")
    await conn.execute(text(
        "CREATE INDEX ix_medical_nodes_embedding_hnsw ON medical_nodes "
        "USING hnsw (embedding vector_cosine_ops)"
    ))
    await conn.commit()
    print("  index built.")


def _canonical(cluster: list[dict]) -> dict:
    return min(cluster, key=lambda n: (_SOURCE_RANK.get(n["source"], 9), len(n["name"]), n["name"].lower()))


async def _cluster_category(conn, category: str, threshold: float, topk: int) -> list[list[dict]]:
    rows = (await conn.execute(
        text("SELECT id, name, source FROM medical_nodes "
             "WHERE category=:c AND source = ANY(:srcs) AND embedding IS NOT NULL"),
        {"c": category, "srcs": list(_CATALOG_SOURCES)},
    )).all()
    nodes = {r.id: {"id": r.id, "name": r.name, "source": r.source} for r in rows}
    if len(nodes) < 2:
        return []

    uf = _UnionFind()
    # HNSW is only used when the query vector is a bound literal (a CTE/subquery
    # join defeats it), and the planner avoids it at 40k rows unless seqscan is
    # discouraged. So: fetch each node's vector, then ANN top-k with it bound.
    for node_id in nodes:
        vec = (await conn.execute(
            text("SELECT embedding::text FROM medical_nodes WHERE id=:id"), {"id": node_id}
        )).scalar()
        neighbours = (await conn.execute(
            text("SELECT id, 1-(embedding <=> (:v)::vector) AS sim FROM medical_nodes "
                 "WHERE id <> :id AND embedding IS NOT NULL "
                 "ORDER BY embedding <=> (:v)::vector LIMIT :k"),
            {"v": vec, "id": node_id, "k": topk},
        )).all()
        for nb in neighbours:
            if nb.sim >= threshold and nb.id in nodes:
                if _blocked(nodes[node_id]["name"], nodes[nb.id]["name"]):
                    continue
                uf.union(node_id, nb.id)

    clusters: dict[int, list[dict]] = defaultdict(list)
    for node_id, data in nodes.items():
        clusters[uf.find(node_id)].append(data)
    return [c for c in clusters.values() if len(c) > 1]


async def main(threshold: float, topk: int, sample: int, apply: bool, only_category: str | None) -> None:
    categories = [only_category] if only_category else list(_CATEGORIES)

    async with engine.connect() as conn:
        null_left = (await conn.execute(text(
            "SELECT count(*) FROM medical_nodes WHERE source = ANY(:s) AND embedding IS NULL"
        ), {"s": list(_CATALOG_SOURCES)})).scalar()
        if null_left:
            print(f"ABORT: {null_left} catalog nodes still lack embeddings. "
                  f"Run: python scripts/vectorize_new_nodes.py")
            return
        await _ensure_index(conn)
        # At 40k rows the planner prefers a seq-scan+sort (~1s/query); discourage
        # it so the HNSW index is used (~ms/query).
        await conn.execute(text("SET enable_seqscan=off"))

        grand_clusters = 0
        grand_removed = 0
        for category in categories:
            clusters = await _cluster_category(conn, category, threshold, topk)
            removed = sum(len(c) - 1 for c in clusters)
            grand_clusters += len(clusters)
            grand_removed += removed
            print(f"\n== {category}: {len(clusters)} merge-clusters, "
                  f"{removed} duplicates would be removed ==")
            for cluster in sorted(clusters, key=len, reverse=True)[:sample]:
                canon = _canonical(cluster)
                print(f"  KEEP  [{canon['source']}] {canon['name']}")
                for node in cluster:
                    if node["id"] != canon["id"]:
                        print(f"    merge<- [{node['source']}] {node['name']}")

            if apply and clusters:
                async with AsyncSession(engine) as session:
                    for cluster in clusters:
                        canon = _canonical(cluster)
                        dup_ids = [n["id"] for n in cluster if n["id"] != canon["id"]]
                        if not dup_ids:
                            continue
                        await session.execute(text(
                            "UPDATE medical_edges SET source_id=:c WHERE source_id = ANY(:d)"),
                            {"c": canon["id"], "d": dup_ids})
                        await session.execute(text(
                            "UPDATE medical_edges SET target_id=:c WHERE target_id = ANY(:d)"),
                            {"c": canon["id"], "d": dup_ids})
                        await session.execute(text(
                            "DELETE FROM medical_nodes WHERE id = ANY(:d)"), {"d": dup_ids})
                    await session.commit()
                print(f"  [APPLIED] {category}: removed {removed} duplicates.")

        print(f"\n{'[APPLIED] ' if apply else '[DRY RUN] '}Total: {grand_clusters} clusters, "
              f"{grand_removed} duplicates{' removed' if apply else ' would be removed'} "
              f"(threshold={threshold}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--topk", type=int, default=15)
    parser.add_argument("--sample", type=int, default=6, help="clusters to print per category (dry-run)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--category", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.threshold, args.topk, args.sample, args.apply, args.category))
