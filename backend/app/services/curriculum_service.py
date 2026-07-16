from __future__ import annotations

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Discipline, ReferenceGraph
from app.schemas import GraphSchema


def _ru_reference_graph_payload() -> GraphSchema:
    return GraphSchema(
        nodes=[
            {"id": "n1", "type": "default", "position": {"x": 80, "y": 100}, "data": {"label": "Инсулинорезистентность", "category": "PATIENT_PROFILE"}},
            {"id": "n2", "type": "default", "position": {"x": 380, "y": 110}, "data": {"label": "Сахарный диабет 2 типа", "category": "DIAGNOSIS"}},
            {"id": "n3", "type": "default", "position": {"x": 700, "y": 40}, "data": {"label": "Полиурия", "category": "SYMPTOM"}},
            {"id": "n4", "type": "default", "position": {"x": 700, "y": 180}, "data": {"label": "Полидипсия", "category": "SYMPTOM"}},
            {"id": "n5", "type": "default", "position": {"x": 380, "y": 300}, "data": {"label": "Метформин", "category": "MEDICATION"}},
        ],
        edges=[
            {"id": "e1", "source": "n1", "target": "n2", "label": "DETERMINES"},
            {"id": "e2", "source": "n2", "target": "n3", "label": "DETERMINES"},
            {"id": "e3", "source": "n2", "target": "n4", "label": "DETERMINES"},
            {"id": "e4", "source": "n2", "target": "n5", "label": "INDICATED_FOR"},
        ],
    )


async def _ensure_discipline(session: AsyncSession) -> int:
    row = await session.execute(select(Discipline).where(Discipline.code == "CLIN"))
    disc = row.scalars().first()
    if disc:
        return disc.id
    disc = Discipline(name="Клиническое мышление", code="CLIN")
    session.add(disc)
    await session.flush()
    return disc.id


async def _ensure_reference_graph(session: AsyncSession, discipline_id: int) -> ReferenceGraph:
    row = await session.execute(select(ReferenceGraph).where(ReferenceGraph.title == "Эталон: диабет и клиническая цепочка"))
    ref = row.scalars().first()
    if ref:
        return ref

    payload = _ru_reference_graph_payload().model_dump()
    ref = ReferenceGraph(
        title="Эталон: диабет и клиническая цепочка",
        description=(
            "Постройте цепочку от патофизиологии к симптомам и выберите препарат. "
            "Система проверяет направленные связи и типы отношений."
        ),
        graph_data=payload,
        discipline_id=discipline_id,
    )
    session.add(ref)
    await session.flush()
    return ref


async def _ensure_assignment(session: AsyncSession, discipline_id: int, reference_graph_id: int) -> Assignment:
    row = await session.execute(select(Assignment).where(Assignment.reference_graph_id == reference_graph_id))
    assignment = row.scalars().first()
    if assignment:
        return assignment

    assignment = Assignment(
        title="Задание: от симптома к причине и терапии",
        description=(
            "Постройте граф клинического мышления: причина -> заболевание -> симптомы -> лечение. "
            "Используйте связи DETERMINES, INDICATED_FOR и проверьте решение."
        ),
        discipline_id=discipline_id,
        reference_graph_id=reference_graph_id,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def ensure_curriculum_baseline(session: AsyncSession) -> Dict[str, int]:
    discipline_id = await _ensure_discipline(session)
    ref = await _ensure_reference_graph(session, discipline_id)
    _ = await _ensure_assignment(session, discipline_id, ref.id)
    await session.commit()

    return {
        "reference_graph_id": ref.id,
        "discipline_id": discipline_id,
    }


def build_default_assignment_template(reference_graph_id: int) -> Dict[str, object]:
    return {
        "title": "Клинический разбор: диабет 2 типа",
        "instructions": [
            "Добавьте узлы причины, заболевания, симптомов и терапии.",
            "Проведите направленные связи между узлами.",
            "Проверьте, чтобы тип связи соответствовал медицинской логике.",
        ],
        "reference_graph_id": reference_graph_id,
    }
