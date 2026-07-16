from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.services.llm_router import LLMRouter


def _fallback_assignment(reference_graph_id: int) -> Dict[str, Any]:
    return {
        "title": "Клиническая задача: диабет 2 типа",
        "student_prompt": (
            "Постройте граф клинического мышления: от патофизиологической причины "
            "к заболеванию, симптомам и выбору препарата."
        ),
        "checklist": [
            "Есть минимум 4 узла: причина, заболевание, симптом, препарат.",
            "Связи направлены и подписаны (causes/indicates/treats).",
            "Нет логически обратных или лишних связей.",
        ],
        "commentary": "Использован локальный шаблон без внешнего ИИ.",
        "reference_graph_id": reference_graph_id,
    }


def _parse_json(text: str) -> Dict[str, Any] | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


async def generate_assignment_with_llm(
    *,
    reference_graph_id: int,
    graph_title: str,
    graph_description: str | None,
    graph_data: Dict[str, Any],
) -> Dict[str, Any]:
    router = LLMRouter()
    if not router.gemini_client:
        return _fallback_assignment(reference_graph_id)

    labels = [str(n.get("data", {}).get("label", "")).strip() for n in graph_data.get("nodes", [])][:18]
    rels = [f"{e.get('source')}->{e.get('target')}:{e.get('label')}" for e in graph_data.get("edges", [])][:20]
    prompt = f"""Ты методист медицинского образования. Сгенерируй задание на русском для студента.

Эталонный граф:
- id: {reference_graph_id}
- title: {graph_title}
- description: {graph_description or 'нет'}
- labels: {labels}
- edges: {rels}

Нужно вернуть только JSON:
{{
  "title": "краткий заголовок задания",
  "student_prompt": "инструкция студенту 2-4 предложения",
  "checklist": ["критерий 1", "критерий 2", "критерий 3"],
  "commentary": "как оценка связана с клиническим мышлением"
}}
"""
    try:
        raw = await router.chat_completion(prompt)
        parsed = _parse_json(raw) or {}
        title = str(parsed.get("title") or "").strip()
        student_prompt = str(parsed.get("student_prompt") or "").strip()
        checklist = parsed.get("checklist") or []
        commentary = str(parsed.get("commentary") or "").strip()
        if not title or not student_prompt or not isinstance(checklist, list):
            return _fallback_assignment(reference_graph_id)
        clean_checklist: List[str] = [str(item).strip()[:400] for item in checklist if str(item).strip()]
        if not clean_checklist:
            return _fallback_assignment(reference_graph_id)
        return {
            "title": title[:200],
            "student_prompt": student_prompt[:1200],
            "checklist": clean_checklist[:6],
            "commentary": (commentary or "Сформировано языковой моделью для учебного сценария.")[:1200],
            "reference_graph_id": reference_graph_id,
        }
    except Exception:
        return _fallback_assignment(reference_graph_id)
