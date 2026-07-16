import json
import logging
import re
from typing import Any, List

from fastapi import HTTPException

from app.config import Settings
from app.schemas import GraphFeedbackResponse, GraphHintsRequest, GraphHintsResponse, HintItem
from app.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)


def _fallback_hints(req: GraphHintsRequest) -> GraphHintsResponse:
    hints: List[HintItem] = []
    for e in req.missing_edges[:3]:
        hints.append(
            HintItem(
                text=f"Проверьте связь «{e.get('source', '')}» → «{e.get('target', '')}» ({e.get('relation', '')}).",
                priority=1,
            )
        )
    for e in req.incorrect_edges[:2]:
        hints.append(
            HintItem(
                text=f"Связь «{e.get('source', '')}» → «{e.get('target', '')}» с типом {e.get('relation', '')} может быть лишней или неверной.",
                priority=2,
            )
        )
    if not hints:
        hints.append(
            HintItem(
                text="Сопоставьте названия концептов с учебным эталоном и уточните типы рёбер (treats, causes, …).",
                priority=1,
            )
        )
    return GraphHintsResponse(
        hints=hints[:5],
        summary="Краткие наводки по результатам сравнения с эталоном.",
    )


async def generate_graph_hints(req: GraphHintsRequest, settings: Settings) -> GraphHintsResponse:
    router = LLMRouter()
    if not router.openai_client and not router.gemini_client:
        return _fallback_hints(req)

    node_labels = [n.data.label for n in req.student_graph.nodes]
    edge_brief = [f"{e.source}->{e.target}:{e.label or '?'}" for e in req.student_graph.edges[:40]]
    prompt = f"""Ты методист по медицинским дисциплинам. Студент строит граф клинических связей.
Узлы (подписи): {', '.join(node_labels[:30])}.
Рёбра (id): {', '.join(edge_brief)}.
Задание reference_graph_id={req.reference_graph_id}.
Пропущенные эталонные связи (labels): {req.missing_edges[:12]}.
Лишние/ошибочные связи: {req.incorrect_edges[:12]}.

Дай 3–5 коротких подсказок на русском: наводящие, без полного решения и без перечисления всего эталона.
Ответь ТОЛЬКО JSON: {{"summary":"одно предложение","hints":[{{"text":"...","priority":1}}]}}
priority: 1 важнее 2."""

    try:
        text = await router.chat_completion(prompt)
    except Exception as exc:
        logger.warning("LLM hints failed: %s", exc)
        return _fallback_hints(req)

    parsed = _parse_json_hints(text)
    if parsed:
        return parsed
    return _fallback_hints(req)


def _parse_json_hints(text: str) -> GraphHintsResponse | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        raw: Any = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    summary = str(raw.get("summary") or "Подсказки по графу.")
    hints_raw = raw.get("hints") or []
    hints: List[HintItem] = []
    if isinstance(hints_raw, list):
        for i, h in enumerate(hints_raw):
            if isinstance(h, dict) and h.get("text"):
                hints.append(HintItem(text=str(h["text"])[:500], priority=int(h.get("priority", i + 1))))
            elif isinstance(h, str):
                hints.append(HintItem(text=h[:500], priority=i + 1))
    if not hints:
        return None
    return GraphHintsResponse(hints=hints[:8], summary=summary[:800])

async def generate_graph_feedback(req: GraphHintsRequest, settings: Settings) -> GraphFeedbackResponse:
    router = LLMRouter()
    if not router.openai_client and not router.gemini_client:
        return GraphFeedbackResponse(feedback="Сервис ИИ в данный момент недоступен для формирования детального отчета.")

    prompt = f"""Ты опытный врач-эксперт и методист. Твоя задача — дать развернутую, научно и практически обоснованную обратную связь студенту-медику по результатам его решения клинического кейса.
Студент построил граф клинических связей.
Задание reference_graph_id={req.reference_graph_id}.

Связи, которые студент пропустил (они есть в эталоне):
{req.missing_edges}

Связи, которые студент указал ошибочно (они неверные или лишние):
{req.incorrect_edges}

Напиши развернутый отчет (в формате Markdown) с подробным описанием:
1. Почему пропущенные связи важны (их клинический и логический смысл).
2. Почему ошибочные связи неверны (в чем ошибка логики, почему это может навредить пациенту или является некорректным).
Отчет должен быть структурированным, поддерживающим (без резкой критики) и научно обоснованным. Обязательно используй списки и выделения Markdown для удобочитаемости."""

    try:
        text = await router.chat_completion(prompt)
        return GraphFeedbackResponse(feedback=text)
    except Exception as exc:
        logger.warning("LLM feedback failed: %s", exc)
        return GraphFeedbackResponse(feedback="Ошибка генерации отчета: " + str(exc))

