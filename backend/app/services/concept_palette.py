from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, MedicalNode, ReferenceGraph
from app.services import morphology

# Catalog sources surfaced in the palette: the scraped MedElement protocols plus
# the protocol-derived reference blocks backfilled into the catalog.
_MEDELEMENT_SOURCES = (
    "protocols",
    "clinical_protocols",
    "medelement_terms",
    "medelement",
)
_CATALOG_SOURCES = (*_MEDELEMENT_SOURCES, "protocol_graph")

_GRAPH_CATEGORY_TO_DB: dict[str, str] = {
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

_DEFAULT_SCOPED_CATEGORIES = (
    "PATIENT_PROFILE",
    "SYMPTOM",
    "DIAGNOSIS",
    "MEDICATION",
    "LAB_TEST",
)

_SKIP_NODE_TYPES = frozenset({"frame", "group"})

# Upper bound on candidate rows scored per category (keeps a big category like
# SYMPTOM, ~3k rows, from being fully lemmatised when only the top matches are
# kept). Reference blocks are added unconditionally regardless of this cap.
_CANDIDATE_POOL_LIMIT = 600


def _extract_reference_blocks(
    graph_data: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """Map each graph category -> ordered, de-duplicated reference block labels."""
    blocks: dict[str, list[str]] = {}
    if not graph_data:
        return blocks

    for node in graph_data.get("nodes", []):
        if node.get("type") in _SKIP_NODE_TYPES:
            continue
        node_data = node.get("data") or {}
        category = str(node_data.get("category") or "").upper().strip()
        label = (node_data.get("label") or "").strip()
        if not category or not label:
            continue
        bucket = blocks.setdefault(category, [])
        if label.lower() not in {existing.lower() for existing in bucket}:
            bucket.append(label)
    return blocks


async def build_assignment_palette(
    db: AsyncSession,
    assignment: Assignment,
    reference_graph: ReferenceGraph,
    *,
    per_category: int = 24,
) -> dict[str, Any]:
    """Build a per-assignment palette.

    Guarantees:
    - every block used in the reference graph is present (the task is solvable);
    - distractors are catalog blocks ranked by lemma overlap with the scenario
      text (so a STEMI case no longer surfaces an unrelated HIV-contact block);
    - only categories that actually yield blocks are returned.
    """
    graph_data = reference_graph.graph_data if isinstance(reference_graph.graph_data, dict) else {}
    reference_blocks = _extract_reference_blocks(graph_data)

    categories = set(reference_blocks)
    if not categories:
        categories = set(_DEFAULT_SCOPED_CATEGORIES)

    query_lemmas = morphology.lemmas(f"{assignment.title or ''} {assignment.description or ''}")

    items: list[dict[str, Any]] = []
    returned_categories: list[str] = []

    for graph_category in sorted(categories):
        db_category = _GRAPH_CATEGORY_TO_DB.get(graph_category)
        if not db_category:
            continue

        ref_names = {name.lower() for name in reference_blocks.get(graph_category, [])}

        base_stmt = (
            select(MedicalNode)
            .where(MedicalNode.category == db_category)
            .where(MedicalNode.source.in_(_CATALOG_SOURCES))
        )
        # Prefilter the pool to names sharing a query lemma (ILIKE = recall; the
        # exact lemma-overlap ranking below is precision). Alphabetical-first
        # sampling would miss relevant distractors now that a category can hold
        # 10k+ nodes. Reference blocks missing from this pool are injected below.
        if query_lemmas:
            pool_stmt = base_stmt.where(
                or_(*[MedicalNode.name.ilike(f"%{lemma}%") for lemma in query_lemmas])
            ).limit(_CANDIDATE_POOL_LIMIT)
        else:
            pool_stmt = base_stmt.order_by(MedicalNode.name.asc()).limit(_CANDIDATE_POOL_LIMIT)
        pool = list((await db.execute(pool_stmt)).scalars().all())

        references: list[MedicalNode] = []
        distractors: list[tuple[int, MedicalNode]] = []
        for row in pool:
            if row.name.lower() in ref_names:
                references.append(row)
            else:
                score = morphology.overlap_score(query_lemmas, row.name)
                if score > 0:
                    distractors.append((score, row))

        # Reference blocks not present in the candidate pool (e.g. trimmed by the
        # pool cap) are still injected so the task stays solvable.
        pool_names = {row.name.lower() for row in pool}
        extra_reference_labels = [
            name for name in reference_blocks.get(graph_category, [])
            if name.lower() not in pool_names
        ]

        distractors.sort(key=lambda pair: (-pair[0], pair[1].name.lower()))
        distractor_budget = max(0, per_category - len(references) - len(extra_reference_labels))

        selected: list[dict[str, Any]] = []
        for row in references:
            selected.append({
                "id": row.id,
                "label": row.name,
                "category": graph_category,
                "source": row.source,
                "is_reference": True,
            })
        for label in extra_reference_labels:
            selected.append({
                "id": None,
                "label": label,
                "category": graph_category,
                "source": "reference",
                "is_reference": True,
            })
        for _, row in distractors[:distractor_budget]:
            selected.append({
                "id": row.id,
                "label": row.name,
                "category": graph_category,
                "source": row.source,
                "is_reference": False,
            })

        if selected:
            items.extend(selected)
            returned_categories.append(graph_category)

    return {
        "items": items,
        "categories": returned_categories,
        "scoped": True,
        "keyword_count": len(query_lemmas),
    }
