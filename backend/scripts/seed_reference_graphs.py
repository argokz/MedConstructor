import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.models import MedicalNode, MedicalEdge, ReferenceGraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def seed_scientific_graph(session: AsyncSession, disease_name: str, symptoms: list, patho: list, drugs: list):
    # 1. Сначала ищем или создаем Узлы
    async def get_or_create(name, category, source="Seed"):
        result = await session.execute(select(MedicalNode).where(MedicalNode.name == name))
        node = result.scalar_one_or_none()
        if not node:
            # Для демо пропустим векторизацию, чтобы не тратить API (или можно раскомментировать llm_router.get_embedding)
            # Из соображений скорости MVP
            node = MedicalNode(name=name, category=category, source=source)
            session.add(node)
            await session.commit()
            await session.refresh(node)
        return node

    disease_node = await get_or_create(disease_name, "disease", "clinical_protocols")
    
    # 2. Создаем связи
    edges_to_add = []
    
    for s_name in symptoms:
        s_node = await get_or_create(s_name, "Symptom", "SNOMED")
        edges_to_add.append(MedicalEdge(source_id=s_node.id, target_id=disease_node.id, relation_type="indicates"))
        
    for p_name in patho:
        p_node = await get_or_create(p_name, "Pathophysiology", "SNOMED")
        edges_to_add.append(MedicalEdge(source_id=p_node.id, target_id=disease_node.id, relation_type="causes"))
        
    for d_name in drugs:
        d_node = await get_or_create(d_name, "medication", "clinical_protocols")
        edges_to_add.append(MedicalEdge(source_id=d_node.id, target_id=disease_node.id, relation_type="treats"))
        
    session.add_all(edges_to_add)
    
    # Также собираем JSON для старого ReferenceGraph, если фронт еще не перешел на MedicalEdge
    graph_data = {
        "nodes": [{"id": disease_name, "type": "Disease"}] + [{"id": n, "type": "Symptom"} for n in symptoms] + [{"id": d, "type": "Pharmacology"} for d in drugs],
        "edges": [{"source": s, "target": disease_name} for s in symptoms] + [{"source": d, "target": disease_name} for d in drugs]
    }
    
    rg = ReferenceGraph(
        title=f"Клинический эталон: {disease_name}",
        description=f"Научная привязка симптомов и лечения к {disease_name}",
        graph_data=graph_data
    )
    session.add(rg)
    await session.commit()
    logger.info(f"Создан эталон для {disease_name}")


async def async_main():
    SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        # Диабет
        await seed_scientific_graph(
            session,
            disease_name="Сахарный диабет 2 типа",
            symptoms=["Полиурия", "Полидипсия", "Гипергликемия"],
            patho=["Инсулинорезистентность"],
            drugs=["Метформин (A10BA02)", "Дапаглифлозин (A10BK01)"]
        )
        
        # Астма
        await seed_scientific_graph(
            session,
            disease_name="Бронхиальная астма",
            symptoms=["Приступы удушья", "Свистящее дыхание", "Кашель"],
            patho=["Бронхоспазм", "Аллергическое воспаление"],
            drugs=["Сальбутамол (R03AC02)", "Будесонид (R03BA02)"]
        )

if __name__ == "__main__":
    asyncio.run(async_main())
