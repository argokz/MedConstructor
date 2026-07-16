import re
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.models import MedicalNode

router = APIRouter(tags=["concepts"])

_MEDELEMENT_SOURCES = (
    "protocols",
    "clinical_protocols",
    "medelement_terms",
    "medelement",
    "protocol_graph",
)

# Display order for catalog categories; only categories that actually have
# blocks are returned (empty ones are skipped, not shown as dead chips).
_CATEGORY_ORDER = (
    "patient_profile",
    "symptom",
    "exam",
    "lab_test",
    "instrumental_test",
    "disease",
    "medication",
    "surgery",
    "monitoring",
)

_CATEGORY_DISPLAY = {
    "patient_profile": "PATIENT_PROFILE",
    "disease": "DISEASE",
    "symptom": "SYMPTOM",
    "exam": "EXAM",
    "medication": "MEDICATION",
    "lab_test": "LAB_TEST",
    "instrumental_test": "INSTRUMENTAL_TEST",
    "surgery": "SURGERY",
    "monitoring": "MONITORING",
}


def _sanitize_q(raw: str) -> str:
    return re.sub(r"[^\w\s\-.]", "", raw, flags=re.UNICODE).strip()[:80]


def _apply_source_filter(stmt, source: Optional[str]):
    if source and source.strip():
        return stmt.where(MedicalNode.source == source.strip())
    return stmt.where(MedicalNode.source.in_(_MEDELEMENT_SOURCES))


@router.get("/concepts/suggest")
async def suggest_concepts(
    db: DbSession,
    q: str = Query("", min_length=1, max_length=80),
    category: Optional[str] = Query(None, description="Фильтр по категории (disease, medication и т.д.)"),
    source: Optional[str] = Query(
        None,
        description="Фильтр по полю source; по умолчанию — только узлы из протоколов MedElement.",
    ),
    limit: int = Query(20, ge=1, le=50),
) -> list[dict]:
    """Подсказки по `medical_nodes`, извлечённым из клинических протоколов MedElement."""
    term = _sanitize_q(q)
    if len(term) < 2:
        return []
    pattern = f"%{term}%"

    stmt = select(MedicalNode).where(MedicalNode.name.ilike(pattern))
    stmt = _apply_source_filter(stmt, source)
    if category:
        stmt = stmt.where(MedicalNode.category == category.lower())

    result = await db.execute(stmt.order_by(MedicalNode.name.asc()).limit(limit))
    rows = list(result.scalars().all())
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "external_id": r.external_id,
            "source": r.source,
        }
        for r in rows
    ]


@router.get("/concepts/palette")
async def concept_palette(
    db: DbSession,
    per_category: int = Query(24, ge=1, le=80),
    source: Optional[str] = Query(
        None,
        description="Фильтр по полю source; по умолчанию — только узлы из протоколов MedElement.",
    ),
) -> dict:
    """Узлы из протоколов MedElement по категориям — для палитры конструктора."""
    items: list[dict] = []
    total = 0
    for cat in _CATEGORY_ORDER:
        count_stmt = _apply_source_filter(
            select(func.count()).select_from(MedicalNode).where(MedicalNode.category == cat),
            source,
        )
        available = (await db.execute(count_stmt)).scalar() or 0
        if not available:
            continue
        total += available

        stmt = select(MedicalNode).where(MedicalNode.category == cat)
        stmt = _apply_source_filter(stmt, source)
        stmt = stmt.order_by(MedicalNode.name.asc()).limit(per_category)
        result = await db.execute(stmt)
        for r in result.scalars().all():
            items.append(
                {
                    "id": r.id,
                    "label": r.name,
                    "category": _CATEGORY_DISPLAY.get(r.category, r.category.upper()),
                    "source": r.source,
                }
            )
    # `total` = full catalog size (all matching rows); `items` is a capped preview.
    return {"items": items, "total": total}
