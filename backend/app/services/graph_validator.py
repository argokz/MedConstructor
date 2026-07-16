import json
import asyncio
from typing import Dict, Any, List
import numpy as np
from pydantic import BaseModel
from openai import AsyncOpenAI
from collections import defaultdict, deque

from app.schemas import GraphSchema, EdgeSchema, NodeSchema
from app.config import get_settings
from app.services.text_embeddings import encode_texts_sync

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)

class ValidationResult(BaseModel):
    is_valid: bool
    score: int  # Итоговая взвешенная оценка (0-100)
    node_coverage: float  # Покрытие узлов (0.0-1.0)
    structural_correctness: float  # Правильность связей (0.0-1.0)
    chain_completeness: float  # Связность цепочки рассуждений (0.0-1.0)
    missing_nodes: List[str]
    incorrect_edges: List[str]
    feedback_message: str

def _compute_node_embeddings(user_labels: List[str], golden_labels: List[str]) -> Dict[str, np.ndarray]:
    """
    Кодирует уникальные метки узлов в векторные эмбеддинги.
    """
    unique_labels = list(set(user_labels + golden_labels))
    if not unique_labels:
        return {}
    
    # encode_texts_sync нормализует векторы на выходе, косинусное сходство = скалярное произведение.
    vectors = encode_texts_sync(settings, unique_labels)
    return {lbl: np.array(vec, dtype=np.float64) for lbl, vec in zip(unique_labels, vectors)}

def calculate_crp_reward(
    user_graph: GraphSchema, 
    golden_graph: GraphSchema,
    embeddings: Dict[str, np.ndarray],
    entity_threshold: float = 0.75
) -> Dict[str, Any]:
    """
    Вычисляет математические метрики Clinical Reasoning Procedure (CRP) Reward по методологии MedConstructor.
    """
    gt_nodes = golden_graph.nodes
    gen_nodes = user_graph.nodes
    
    if not gt_nodes:
        return {
            "node_coverage": 1.0,
            "structural_correctness": 1.0,
            "chain_completeness": 1.0,
            "missing_nodes": [],
            "incorrect_edges": [],
            "gt_to_gen_mappings": {}
        }
    
    if not gen_nodes:
        return {
            "node_coverage": 0.0,
            "structural_correctness": 0.0,
            "chain_completeness": 0.0,
            "missing_nodes": [n.data.label for n in gt_nodes],
            "incorrect_edges": [],
            "gt_to_gen_mappings": {}
        }

    # 1. Рассчитываем Node Coverage
    total_max_sim = 0.0
    missing_nodes = []
    gt_to_gen_mappings = defaultdict(list)
    
    for gt_n in gt_nodes:
        gt_lbl = gt_n.data.label
        gt_vec = embeddings.get(gt_lbl)
        
        max_sim = 0.0
        best_gen_id = None
        
        for gen_n in gen_nodes:
            gen_lbl = gen_n.data.label
            gen_vec = embeddings.get(gen_lbl)
            
            if gt_vec is not None and gen_vec is not None:
                # Векторы уже нормализованы, сходство = dot product
                sim = float(np.dot(gt_vec, gen_vec))
            else:
                sim = 1.0 if gt_lbl.lower() == gen_lbl.lower() else 0.0
                
            if sim > max_sim:
                max_sim = sim
                best_gen_id = gen_n.id
                
        total_max_sim += max_sim
        
        if max_sim >= entity_threshold:
            gt_to_gen_mappings[gt_n.id].append(best_gen_id)
        else:
            missing_nodes.append(gt_lbl)
            
    node_coverage = total_max_sim / len(gt_nodes)

    # 2. Рассчитываем Structural Correctness
    gt_edges = golden_graph.edges
    gen_edges = user_graph.edges
    
    if not gt_edges:
        return {
            "node_coverage": node_coverage,
            "structural_correctness": 1.0,
            "chain_completeness": 1.0,
            "missing_nodes": missing_nodes,
            "incorrect_edges": [],
            "gt_to_gen_mappings": gt_to_gen_mappings
        }
        
    recalled_edges = set()
    incorrect_edges = []
    
    # Быстрый поиск ребер пользователя
    user_edge_lookup = {(e.source, e.target, e.label): e for e in gen_edges}
    
    for gt_e in gt_edges:
        # Ищем, сопоставил ли студент это ребро
        s_matches = gt_to_gen_mappings.get(gt_e.source, [])
        t_matches = gt_to_gen_mappings.get(gt_e.target, [])
        
        found = False
        for s_m in s_matches:
            for t_m in t_matches:
                if (s_m, t_m, gt_e.label) in user_edge_lookup:
                    recalled_edges.add((gt_e.source, gt_e.label, gt_e.target))
                    found = True
                    break
            if found:
                break
                
        if not found:
            # Если ребро не найдено, это ошибка структуры
            gt_s_lbl = next((n.data.label for n in gt_nodes if n.id == gt_e.source), "Unknown")
            gt_t_lbl = next((n.data.label for n in gt_nodes if n.id == gt_e.target), "Unknown")
            incorrect_edges.append(f"Пропущена или неверно связана зависимость: [{gt_s_lbl}] -> ({gt_e.label}) -> [{gt_t_lbl}]")
            
    structural_correctness = len(recalled_edges) / len(gt_edges)

    # 3. Рассчитываем Chain Completeness (связность цепочки через поиск компонент)
    chain_completeness = 0.0
    if recalled_edges:
        adj = defaultdict(set)
        recalled_nodes = set()
        for s, r, t in recalled_edges:
            adj[s].add(t)
            adj[t].add(s)
            recalled_nodes.add(s)
            recalled_nodes.add(t)
            
        visited = set()
        max_edges_in_component = 0
        
        for node in recalled_nodes:
            if node not in visited:
                component_nodes = set()
                q = deque([node])
                visited.add(node)
                while q:
                    curr = q.popleft()
                    component_nodes.add(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            q.append(neighbor)
                            
                # Считаем количество ребер в этой компоненте связности
                edges_count = sum(1 for s, r, t in recalled_edges if s in component_nodes and t in component_nodes)
                if edges_count > max_edges_in_component:
                    max_edges_in_component = edges_count
                    
        chain_completeness = max_edges_in_component / len(gt_edges)
    else:
        chain_completeness = 0.0

    return {
        "node_coverage": node_coverage,
        "structural_correctness": structural_correctness,
        "chain_completeness": chain_completeness,
        "missing_nodes": missing_nodes,
        "incorrect_edges": incorrect_edges,
        "gt_to_gen_mappings": gt_to_gen_mappings
    }

async def validate_user_graph(user_graph: GraphSchema, golden_graph: GraphSchema, protocol_context: str) -> ValidationResult:
    """
    Смысловая проверка собранного графа с вычислением математического CRP Reward
    и генерацией поясняющего фидбека от AI.
    """
    # 1. Извлекаем метки узлов и считаем эмбеддинги
    user_labels = [n.data.label for n in user_graph.nodes]
    golden_labels = [n.data.label for n in golden_graph.nodes]
    
    embeddings = await asyncio.to_thread(_compute_node_embeddings, user_labels, golden_labels)
    
    # 2. Вычисляем CRP Reward
    crp = calculate_crp_reward(user_graph, golden_graph, embeddings)
    
    # Взвешенная оценка (40% покрытие, 30% структура, 30% связность цепочки)
    weighted_score = int(
        (0.40 * crp["node_coverage"] + 
         0.30 * crp["structural_correctness"] + 
         0.30 * crp["chain_completeness"]) * 100
    )
    
    is_valid = weighted_score >= 80

    # 3. Подготовка промпта для ИИ для генерации развернутого фидбека
    prompt = f"""
Ты — AI Judge (строгий медицинский экзаменатор) по методологии MedConstructor.
Твоя задача — проанализировать математические метрики соответствия графа студента эталонному графу (Golden Path) и написать развернутый, конструктивный отзыв на русском языке.

Контекст клинического протокола:
{protocol_context}

Математический анализ сходства (CRP Reward):
- Общая оценка: {weighted_score} / 100
- Покрытие узлов (Node Coverage): {crp['node_coverage']:.2f}
- Правильность структуры связей (Structural Correctness): {crp['structural_correctness']:.2f}
- Связность клинической логики (Chain Completeness): {crp['chain_completeness']:.2f}

Выявленные пропущенные понятия:
{crp['missing_nodes']}

Выявленные структурные разрывы/ошибки в связях:
{crp['incorrect_edges']}

Сформируй развернутое пояснение (feedback_message) для студента:
1. Конкретно укажи, какие важные обследования, диагнозы или препараты он пропустил (ссылаясь на протокол).
2. Объясни, почему его текущие связи нарушают клиническую логику (например, назначено лечение без подтверждающей диагностики).
3. Похвали за правильные шаги, если они есть.
Пиши профессиональным, академическим языком.

Выведи результат строго в формате JSON, соответствующем этой схеме:
{{
    "feedback_message": "Текст с разбором ошибок, ссылками на протокол и рекомендациями."
}}
Выведи только JSON (без ```json).
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": "You are a medical AI judge. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```json"):
            result_text = result_text.replace("```json\n", "").replace("\n```", "")
            
        data = json.loads(result_text)
        feedback = data.get("feedback_message", "Не удалось сгенерировать подробный отзыв.")
        
    except Exception as e:
        print(f"Error during AI validation: {e}")
        feedback = "Система успешно рассчитала математические оценки, но произошел сбой при генерации развернутого текстового разбора ИИ."

    return ValidationResult(
        is_valid=is_valid,
        score=weighted_score,
        node_coverage=round(crp["node_coverage"], 2),
        structural_correctness=round(crp["structural_correctness"], 2),
        chain_completeness=round(crp["chain_completeness"], 2),
        missing_nodes=crp["missing_nodes"],
        incorrect_edges=crp["incorrect_edges"],
        feedback_message=feedback
    )
