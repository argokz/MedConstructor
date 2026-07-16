import json
import asyncio
import random
import sys
import os
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
from app.schemas import GraphSchema, NodeSchema, EdgeSchema, NodeData, NodeType, EdgeType
from app.services.graph_validator import validate_user_graph
from app.config import get_settings

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)

async def convert_triplets_to_schema(triplets: List[List[str]]) -> GraphSchema:
    """
    Использует GPT-4o для конвертации плоских троек MedConstructor в типизированную схему GraphSchema.
    """
    prompt = f"""
Ты — конвертер медицинских данных. Твоя задача — преобразовать плоский граф из троек [субъект, связь, объект] в строго типизированный формат JSON GraphSchema.

Доступные типы узлов (NodeType):
- PATIENT_PROFILE: Характеристики пациента (возраст, пол, сопутствующие болезни)
- SYMPTOM: Жалобы, симптомы
- EXAM: Физикальный осмотр
- LAB_TEST: Лабораторная диагностика
- INSTRUMENTAL_TEST: Инструментальная диагностика (КТ, УЗИ, МРТ)
- DIAGNOSIS: Диагнозы
- MEDICATION: Лекарства
- SURGERY: Операции

Доступные типы связей (EdgeType):
- DETERMINES: Обуславливает, указывает на необходимость
- REQUIRES_CONFIRMATION: Требует подтверждения
- EXCLUDES: Исключает
- INDICATED_FOR: Показано для (направление: DIAGNOSIS -> MEDICATION/SURGERY)
- CONTRAINDICATED_DUE_TO: Противопоказано из-за (направление: MEDICATION/SURGERY -> PATIENT_PROFILE/DIAGNOSIS/SYMPTOM)

Входные тройки MedConstructor:
{json.dumps(triplets, ensure_ascii=False, indent=2)}

Твой ответ должен быть строго валидным JSON, соответствующим схеме GraphSchema:
{{
    "nodes": [
        {{
            "id": "n1",
            "type": "med",
            "position": {{"x": 0, "y": 0}},
            "data": {{"label": "Название на русском или английском", "category": "NodeType"}}
        }}, ...
    ],
    "edges": [
        {{
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "label": "EdgeType"
        }}, ...
    ]
}}

Выведи только JSON (без ```json). Будь предельно аккуратен и сопоставь каждый узел с наиболее подходящим NodeType, а связь — с EdgeType.
"""
    try:
        response = await client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": "You are a helpful data converter. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```json"):
            result_text = result_text.replace("```json\n", "").replace("\n```", "")
            
        data = json.loads(result_text)
        return GraphSchema(**data)
    except Exception as e:
        print(f"Error converting triplets: {e}")
        raise e

def mutate_graph_for_student(golden: GraphSchema) -> GraphSchema:
    """
    Симулирует граф студента, внося искажения в эталонный граф:
    - Удаляет 25% случайных узлов
    - Удаляет соответствующие связи
    - Искажает формулировки некоторых оставшихся узлов для проверки семантического сходства
    """
    nodes = list(golden.nodes)
    edges = list(golden.edges)
    
    # 1. Удаляем 25% случайных узлов
    num_to_delete = max(1, int(len(nodes) * 0.25))
    nodes_to_delete = random.sample(nodes, num_to_delete)
    deleted_ids = {n.id for n in nodes_to_delete}
    
    remaining_nodes = [n for n in nodes if n.id not in deleted_ids]
    
    # 2. Удаляем связи, привязанные к удаленным узлам
    remaining_edges = [e for e in edges if e.source not in deleted_ids and e.target not in deleted_ids]
    
    # 3. Искажаем метки у некоторых узлов (синонимы)
    synonym_map = {
        "blurred vision": "impairment of sight",
        "headache": "severe cephalalgia",
        "nausea": "feeling of sickness",
        "bilious vomiting": "emesis of bile",
        "fever": "high temperature",
        "papilledema": "edema of optic disc",
        "Bouveret's syndrome": "Bouveret obstruction",
        "Posterior Reversible Encephalopathy Syndrome": "PRES syndrome",
        "COVID-19 infection": "coronavirus infection"
    }
    
    mutated_nodes = []
    for n in remaining_nodes:
        new_label = n.data.label
        for orig, syn in synonym_map.items():
            if orig.lower() in n.data.label.lower():
                new_label = n.data.label.lower().replace(orig.lower(), syn)
                break
        
        mutated_nodes.append(
            NodeSchema(
                id=n.id,
                position=n.position,
                data=NodeData(label=new_label, category=n.data.category)
            )
        )
        
    return GraphSchema(nodes=mutated_nodes, edges=remaining_edges)

async def evaluate_case(index: int, case: Dict[str, Any]):
    print(f"\n==================================================")
    print(f"BENCHMARK CASE #{index}: {case.get('answer')}")
    print(f"==================================================")
    
    triplets = case["graph"]["triplets"]
    print(f"Original MedConstructor Triplets count: {len(triplets)}")
    
    # 1. Конвертируем MedConstructor граф в наш GraphSchema
    print("Converting MedConstructor triplets to our clinical schema...")
    try:
        golden_graph = await convert_triplets_to_schema(triplets)
    except Exception:
        print("Conversion failed. Skipping case.")
        return
        
    print(f"Golden Graph: {len(golden_graph.nodes)} nodes, {len(golden_graph.edges)} edges.")
    
    # 2. Симулируем ответ студента
    student_graph = mutate_graph_for_student(golden_graph)
    print(f"Simulated Student Graph: {len(student_graph.nodes)} nodes, {len(student_graph.edges)} edges.")
    
    # 3. Запускаем нашего AI Judge
    print("Running AI Judge validation...")
    result = await validate_user_graph(
        user_graph=student_graph,
        golden_graph=golden_graph,
        protocol_context=case["reasoning_content"]
    )
    
    print("\n[CRP Reward Evaluation Metrics]")
    print(f"- Node Coverage (Покрытие узлов): {result.node_coverage:.2f}")
    print(f"- Structural Correctness (Структура): {result.structural_correctness:.2f}")
    print(f"- Chain Completeness (Связность цепочки): {result.chain_completeness:.2f}")
    print(f"- Final Mathematical Score: {result.score} / 100")
    print(f"- Validation Outcome: {'PASSED' if result.is_valid else 'FAILED'}")
    
    print("\n[Missing Entities identified by Judge]")
    print(result.missing_nodes[:5])  # Выведем первые 5 пропущенных узлов
    
    print("\n[AI Clinical Feedback Highlight]")
    print(result.feedback_message[:400] + "...")

async def main():
    jsonl_path = os.getenv(
        "MEDCONSTRUCTOR_DATASET_JSONL",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "benchmarks",
            "medconstructor_dataset.jsonl",
        ),
    )
    if not os.path.exists(jsonl_path):
        print(f"Error: Dataset not found at {jsonl_path}")
        return
        
    print("Loading MedConstructor Dataset...")
    cases = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            cases.append(json.loads(line))
            
    print(f"Loaded {len(cases)} cases successfully.")
    
    # Выберем первые 3 кейса для оценки
    limit = 3
    for i, case in enumerate(cases[:limit], start=1):
        await evaluate_case(i, case)

if __name__ == "__main__":
    asyncio.run(main())
