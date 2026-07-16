import json
import re
import time
from collections import OrderedDict
from typing import Any, AsyncIterator

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClinicalProtocol, MedicalNode, ProtocolChunk, StudentTask, StudentTaskAttempt
from app.schemas import EdgeType, GraphSchema, NodeType
from app.services import morphology
from app.services.concept_palette import _CATALOG_SOURCES, _GRAPH_CATEGORY_TO_DB
from app.services.graph_generation_judge import (
    format_quality_warning,
    judge_reference_graph,
    repair_graph_connectivity,
)
from app.services.llm_router import llm_router

try:
    from prometheus_client import Histogram

    RAG_EMBED_MS = Histogram("rag_embed_ms", "RAG embedding latency in milliseconds")
    RAG_SEARCH_MS = Histogram("rag_search_ms", "RAG vector search latency in milliseconds")
    RAG_LLM_MS = Histogram("rag_llm_ms", "RAG LLM generation latency in milliseconds")
except ImportError:  # pragma: no cover
    RAG_EMBED_MS = RAG_SEARCH_MS = RAG_LLM_MS = None

EMBEDDING_CACHE_MAX = 256
_embedding_cache: OrderedDict[str, list[float]] = OrderedDict()

LOW_SIGNAL_SECTION_MARKERS = {
    "отправить файл себе на почту",
    "прикреплённые файлы",
    "прикрепленные файлы",
    "внимание!",
}

LOW_SIGNAL_TEXT_MARKERS = {
    "ajax-loader",
    "data:image",
    "login.medelement.com",
    "закрыть список разделов",
}

LOW_PRIORITY_SECTION_MARKERS = {
    "источники и литература",
    "информация",
    "прикреплённые файлы",
    "прикрепленные файлы",
    "краткое описание",
}

TITLE_MATCH_STOP_TOKENS = {
    "диагностика",
    "диагностике",
    "лечение",
    "лечении",
    "терапия",
    "терапии",
    "госпитализация",
    "госпитализации",
    "классификация",
    "профилактика",
    "профилактики",
    "помощь",
    "помощи",
    "неотложная",
    "стационар",
    "амбулатория",
    "препараты",
    "ведение",
    "клинический",
    "клинические",
    "клиническим",
    "клинических",
    "протокол",
    "протоколы",
    "протоколам",
    "протоколов",
    "профиль",
    "профилю",
    "приложение",
    "приложения",
    "болезнь",
    "синдром",
}

RAG_SYSTEM_PROMPT = """Вы профессиональный медицинский эксперт. Ваша задача — дать точный ответ на вопрос пользователя, основываясь ИСКЛЮЧИТЕЛЬНО на предоставленных медицинских протоколах (Источниках).

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Внимательно сопоставляйте заболевание из вопроса с названием протокола (оно указано в заголовке каждого источника). Не берите тактику лечения из протокола по другому заболеванию.
2. Если в предоставленных источниках нет информации ИМЕННО по запрашиваемому заболеванию или вопросу, ответьте: "Извините, в доступных клинических протоколах нет информации по данному вопросу."
3. Если информация найдена, дайте развернутый структурированный ответ (используйте Markdown).
4. Обязательно ссылайтесь на источники в формате [1], [2] и т.д. в тексте ответа."""

MEDCONSTRUCTOR_GRAPH_RULES = """
### Правила построения графа (MedConstructor):

#### 1. Чистота сущностей (Entity Purity) и Компактность:
- ОБЯЗАТЕЛЬНО объединяйте все данные профиля пациента (возраст, пол, хронические заболевания) в ОДИН узел PATIENT_PROFILE. Не создавайте отдельные узлы для каждой характеристики!
- Группируйте схожие или системно связанные симптомы в 1-2 комплексных узла SYMPTOM, чтобы избежать загромождения графа десятками мелких узлов (например, объедините все диспепсические расстройства в один узел).
- Разделяйте сложные понятия на элементарные узлы только там, где это необходимо для проверки логики клинических решений. Во всех остальных случаях делайте граф максимально компактным.

#### 2. Связующие выводы (Bridging Inference):
- Заполняйте логические пустоты. Не допускайте скачков от симптома к диагнозу без промежуточного исследования.

#### 3. Онтология:
- NodeType: PATIENT_PROFILE, SYMPTOM, EXAM, LAB_TEST, INSTRUMENTAL_TEST, DIAGNOSIS, MEDICATION, SURGERY, MONITORING.
- EdgeType: DETERMINES, REQUIRES_CONFIRMATION, EXCLUDES, INDICATED_FOR, CONTRAINDICATED_DUE_TO.
- MEDICATION используйте только для конкретного препарата, класса препаратов или лекарственной терапии. Не относите к MEDICATION наблюдение, контроль, измерение, консультации и повторные обследования.
- MONITORING используйте для наблюдения, контроля показателей, повторного измерения, динамического ведения, follow-up и мониторинга состояния матери/плода.
- INDICATED_FOR: от DIAGNOSIS к MEDICATION/SURGERY/MONITORING.
- CONTRAINDICATED_DUE_TO: от MEDICATION/SURGERY к PATIENT_PROFILE/DIAGNOSIS/SYMPTOM.

Координаты position можно указывать как {"x": 0, "y": 0}; клиент все равно назначит раскладку автоматически.
"""

SCENARIO_SUGGESTIONS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scenarios"],
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "description",
                    "difficulty",
                    "target_competency",
                    "expected_reasoning_steps",
                    "red_flags",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "difficulty": {"type": "string"},
                    "target_competency": {"type": "string"},
                    "expected_reasoning_steps": {"type": "array", "items": {"type": "string"}},
                    "red_flags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

CLINICAL_TASK_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_description", "expected_diagnosis", "expected_treatment"],
    "properties": {
        "case_description": {"type": "string"},
        "expected_diagnosis": {"type": "string"},
        "expected_treatment": {"type": "string"},
    },
}

STUDENT_VALIDATION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "feedback", "is_correct_diagnosis", "is_correct_treatment"],
    "properties": {
        "score": {"type": "number"},
        "feedback": {"type": "string"},
        "is_correct_diagnosis": {"type": "boolean"},
        "is_correct_treatment": {"type": "boolean"},
    },
}

GRAPH_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nodes", "edges"],
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "position", "data"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "position": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["x", "y"],
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                        },
                    },
                    "data": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["label", "category"],
                        "properties": {
                            "label": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": [item.value for item in NodeType],
                            },
                        },
                    },
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "source", "target", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {
                        "type": "string",
                        "enum": [item.value for item in EdgeType],
                    },
                },
            },
        },
    },
}


def _cache_key(text: str, protocol_id: int | None = None) -> str:
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return f"{protocol_id or 'all'}:{normalized}"


def _extract_section_prefix(text: str) -> str:
    match = re.match(r"\[Секция:\s*([^\]]+)\]", text)
    return match.group(1).strip() if match else ""


def _title_match_boost(question: str, title: str) -> float:
    raw_tokens = {t for t in re.findall(r"[a-zа-яё0-9]{3,}", question.lower())}
    q_tokens = {token for token in raw_tokens if token not in TITLE_MATCH_STOP_TOKENS}
    if not q_tokens:
        q_tokens = raw_tokens
    if not q_tokens:
        return 0.0
    title_lower = title.lower()
    hits = sum(1 for t in q_tokens if t in title_lower)
    return min(1.0, hits / max(1, len(q_tokens)))


def _query_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zа-яё0-9]{4,}", text.lower())}


QUERY_TERM_EXPANSIONS = (
    (("гипертенз",), ("гипотензив", "антигипертенз"), 2),
    (("лечен",), ("терап", "фармаколог"), 1),
    (("терап",), ("лечен",), 1),
    (("мониторинг",), ("наблюден", "контроль", "ктг"), 1),
    (("наблюден",), ("мониторинг", "контроль", "ктг"), 1),
    (("внематоч",), ("эктопическ",), 1),
    (("сепсис",), ("септичес", "антибактериаль"), 1),
)


def _keyword_overlap_boost(query: str, text: str) -> float:
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return 0.0
    query_lower = query.lower()
    text_lower = text.lower()
    hits = sum(1 for token in query_tokens if token in text_lower)
    for query_markers, text_markers, weight in QUERY_TERM_EXPANSIONS:
        if any(marker in query_lower for marker in query_markers) and any(
            marker in text_lower for marker in text_markers
        ):
            hits += weight
    return min(1.0, hits / max(1, len(query_tokens)))


SECTION_INTENT_RULES = {
    "diagnostics": {
        "query": ("диагност", "диагноз", "обслед", "узи", "анализ", "лаборатор", "инструмент"),
        "section": ("диагност", "диагноз", "обслед", "узи", "анализ", "лаборатор", "инструмент"),
    },
    "treatment": {
        "query": ("лечен", "терап", "препарат", "антибактериаль", "гипотензив"),
        "section": ("лечен", "терап", "препарат", "фармаколог", "антибактериаль", "гипотензив"),
    },
    "hospitalization": {
        "query": ("госпитал", "стационар", "экстренн"),
        "section": ("госпитал", "стационар", "экстренн"),
    },
    "classification": {
        "query": ("классификац", "степен", "форма"),
        "section": ("классификац", "степен", "форма"),
    },
    "prevention": {
        "query": ("профилактик", "предотвращ", "профилакт"),
        "section": ("профилактик", "предотвращ", "профилакт"),
    },
    "monitoring": {
        "query": ("наблюден", "мониторинг", "контроль", "ктг", "плод", "антенаталь", "постнаталь"),
        "section": ("наблюден", "мониторинг", "контроль", "ктг", "плод", "антенаталь", "кардиотограф"),
    },
}


def _intent_matches(text: str, markers: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)


def _query_section_intents(query: str) -> set[str]:
    return {
        intent
        for intent, rules in SECTION_INTENT_RULES.items()
        if _intent_matches(query, rules["query"])
    }


def _section_title_intents(section: str) -> set[str]:
    return {
        intent
        for intent, rules in SECTION_INTENT_RULES.items()
        if _intent_matches(section, rules["section"])
    }


def _section_intent_boost(query: str, section: str, text: str) -> float:
    desired = _query_section_intents(query)
    if not desired:
        return 0.0

    title_hits = desired.intersection(_section_title_intents(section))
    body_hits = {
        intent
        for intent, rules in SECTION_INTENT_RULES.items()
        if intent in desired and _intent_matches(text[:1200], rules["section"])
    }
    title_score = len(title_hits) / len(desired)
    body_score = len(body_hits) / len(desired)
    return min(1.0, max(title_score, body_score * 0.5))


def _is_query_target_section(query: str, text: str) -> bool:
    desired = _query_section_intents(query)
    if not desired:
        return False
    section = _extract_section_prefix(text)
    return bool(desired.intersection(_section_title_intents(section)))


def _section_intent_diversify(
    scored: list[tuple[ProtocolChunk, str, float, set[str]]],
    question: str,
    final_k: int,
) -> list[tuple[ProtocolChunk, str, float]]:
    desired = _query_section_intents(question)
    if not desired:
        return [(chunk, title, score) for chunk, title, score, _ in scored[:final_k]]

    selected: list[tuple[ProtocolChunk, str, float, set[str]]] = []
    selected_ids: set[int] = set()
    covered: set[str] = set()

    for intent in desired:
        if intent in covered:
            continue
        matches = [
            candidate
            for candidate in scored
            if id(candidate) not in selected_ids and intent in candidate[3]
        ]
        best = max(
            matches,
            key=lambda candidate: (
                1.0 / max(1, len(candidate[3])),
                candidate[2],
            ),
            default=None,
        )
        if best:
            selected.append(best)
            selected_ids.add(id(best))
            covered.update(best[3])

    for candidate in scored:
        if len(selected) >= final_k:
            break
        if id(candidate) in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(id(candidate))

    selected.sort(key=lambda item: item[2], reverse=True)
    return [(chunk, title, score) for chunk, title, score, _ in selected[:final_k]]


def _is_low_signal_chunk(text: str) -> bool:
    lowered = text.lower()
    section = _extract_section_prefix(text).lower()
    if section in LOW_SIGNAL_SECTION_MARKERS:
        return True
    if any(marker in lowered for marker in LOW_SIGNAL_TEXT_MARKERS):
        return True
    if re.search(r"a{80,}", lowered):
        return True

    body = re.sub(r"^\[Секция:[^\]]+\]\s*", "", text).strip()
    alnum_count = len(re.findall(r"[a-zа-яё0-9]", body.lower()))
    if alnum_count < 80:
        return True
    if body.count("|") > 25 and alnum_count / max(1, len(body)) < 0.25:
        return True
    return False


def _is_low_priority_for_query(query: str, text: str) -> bool:
    if not _query_section_intents(query):
        return False
    section = _extract_section_prefix(text).lower()
    return section in LOW_PRIORITY_SECTION_MARKERS


def _infer_category_from_label(label: str, current_category: str) -> str | None:
    normalized = label.lower().strip()
    if not normalized:
        return None

    monitoring_markers = (
        "контроль",
        "мониторинг",
        "наблюдение",
        "follow-up",
        "фоллоу",
        "повторное измерение",
        "динамическое ведение",
        "последующий уход",
        "постнатальный уход",
        "кардиотография",
        "ктг",
    )
    if any(marker in normalized for marker in monitoring_markers):
        return "MONITORING"

    if current_category == "MEDICATION":
        lab_markers = ("анализ", "крови", "мочи", "протеинур", "тромбоцит", "креатинин")
        instrumental_markers = ("узи", "допплер", "допплерометр", "кт ", "мрт", "рентген")
        exam_markers = ("осмотр", "пальпац", "аускультац", "измерение ад", "артериального давления")
        if any(marker in normalized for marker in lab_markers):
            return "LAB_TEST"
        if any(marker in normalized for marker in instrumental_markers):
            return "INSTRUMENTAL_TEST"
        if any(marker in normalized for marker in exam_markers):
            return "EXAM"

    return None


class RAGService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_embedding(self, text: str, protocol_id: int | None = None) -> list[float]:
        key = _cache_key(text, protocol_id)
        if key in _embedding_cache:
            _embedding_cache.move_to_end(key)
            return _embedding_cache[key]

        t0 = time.perf_counter()
        vec = await llm_router.get_embedding(text)
        if RAG_EMBED_MS:
            RAG_EMBED_MS.observe((time.perf_counter() - t0) * 1000)

        _embedding_cache[key] = vec
        _embedding_cache.move_to_end(key)
        while len(_embedding_cache) > EMBEDDING_CACHE_MAX:
            _embedding_cache.popitem(last=False)
        return vec

    async def _vector_search_with_titles(
        self,
        query_embedding: list[float],
        limit: int = 5,
        protocol_id: int | None = None,
        protocol_ids: list[int] | None = None,
        title_filter: str | None = None,
    ) -> list[tuple[ProtocolChunk, str, float]]:
        distance = ProtocolChunk.embedding.l2_distance(query_embedding)
        stmt = (
            select(ProtocolChunk, ClinicalProtocol.title, distance.label("distance"))
            .join(ClinicalProtocol, ProtocolChunk.protocol_id == ClinicalProtocol.id)
        )

        if protocol_id:
            stmt = stmt.where(ProtocolChunk.protocol_id == protocol_id)
        elif protocol_ids:
            stmt = stmt.where(ProtocolChunk.protocol_id.in_(protocol_ids))

        if title_filter and len(title_filter) >= 3:
            pattern = f"%{title_filter}%"
            stmt = stmt.where(ClinicalProtocol.title.ilike(pattern))

        stmt = stmt.order_by(distance).limit(limit)
        result = await self.session.execute(stmt)
        return [(row[0], row[1], float(row[2])) for row in result.all()]

    async def _title_candidate_protocol_ids(self, query: str, limit: int = 8) -> list[int]:
        tokens = _query_tokens(query)
        if not tokens:
            return []

        # Index-backed prefilter (pg_trgm GIN on title): only titles containing at
        # least one query substring can score > 0 below, so this LIKE-OR is a strict
        # superset of the previous full table scan -- identical ranking, no O(N) scan.
        substrings = {t for t in re.findall(r"[a-zа-яё0-9]{3,}", query.lower())}
        substrings.update(token[:6] for token in tokens if len(token) >= 7)
        substrings = {s for s in substrings if len(s) >= 3}
        if not substrings:
            return []

        conditions = [ClinicalProtocol.title.ilike(f"%{s}%") for s in substrings]
        rows = await self.session.execute(
            select(ClinicalProtocol.id, ClinicalProtocol.title).where(or_(*conditions))
        )
        scored: list[tuple[float, int]] = []
        for protocol_id, title in rows.all():
            title_lower = (title or "").lower()
            score = _title_match_boost(query, title_lower)
            for token in tokens:
                if len(token) >= 7 and token[:6] in title_lower:
                    score += 0.2
            if score > 0:
                scored.append((score, int(protocol_id)))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [protocol_id for _, protocol_id in scored[:limit]]

    def _dedup_and_rerank(
        self,
        candidates: list[tuple[ProtocolChunk, str, float]],
        question: str,
        final_k: int,
    ) -> list[tuple[ProtocolChunk, str, float]]:
        seen: set[tuple[int, str]] = set()
        scored: list[tuple[ProtocolChunk, str, float, set[str]]] = []
        useful_candidates = [
            item
            for item in candidates
            if (
                not _is_low_signal_chunk(item[0].text_content)
                or _is_query_target_section(question, item[0].text_content)
            )
        ]
        pool = useful_candidates or candidates

        focused_candidates = [
            item
            for item in pool
            if not _is_low_priority_for_query(question, item[0].text_content)
        ]
        if len(focused_candidates) >= final_k:
            pool = focused_candidates

        title_focused_candidates = [
            item for item in pool if _title_match_boost(question, item[1]) >= 0.25
        ]
        if len(title_focused_candidates) >= final_k:
            pool = title_focused_candidates

        for chunk, title, distance in pool:
            section = _extract_section_prefix(chunk.text_content)
            dedup_key = (chunk.protocol_id, section or str(chunk.chunk_index))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            vector_score = 1.0 / (1.0 + distance)
            title_boost = _title_match_boost(question, title)
            content_boost = _keyword_overlap_boost(
                question,
                f"{section}\n{chunk.text_content[:1200]}",
            )
            section_boost = _section_intent_boost(question, section, chunk.text_content)
            fusion = (
                0.50 * vector_score
                + 0.22 * title_boost
                + 0.16 * content_boost
                + 0.12 * section_boost
            )
            scored.append((chunk, title, fusion, _section_title_intents(section)))

        scored.sort(key=lambda x: x[2], reverse=True)
        return _section_intent_diversify(scored, question, final_k)

    async def retrieve_chunks(
        self,
        query: str,
        limit: int = 18,
        protocol_id: int | None = None,
        protocol_ids: list[int] | None = None,
    ) -> list[tuple[ProtocolChunk, str]]:
        retrieve_k = max(limit * 5, 32) if protocol_id else max(limit * 6, 80)
        final_k = min(limit, 10) if protocol_id else limit

        query_embedding = await self.get_embedding(query, protocol_id)

        t0 = time.perf_counter()
        candidates = await self._vector_search_with_titles(
            query_embedding,
            limit=retrieve_k,
            protocol_id=protocol_id,
            protocol_ids=protocol_ids,
        )
        if not protocol_id and not protocol_ids:
            title_protocol_ids = await self._title_candidate_protocol_ids(query)
            if title_protocol_ids:
                candidates.extend(
                    await self._vector_search_with_titles(
                        query_embedding,
                        limit=max(100, limit * 10),
                        protocol_ids=title_protocol_ids,
                    )
                )
        if RAG_SEARCH_MS:
            RAG_SEARCH_MS.observe((time.perf_counter() - t0) * 1000)

        ranked = self._dedup_and_rerank(candidates, query, final_k)
        return [(chunk, title) for chunk, title, _ in ranked]

    async def vector_search(
        self, query: str, limit: int = 5, protocol_id: int | None = None
    ) -> list[ProtocolChunk]:
        rows = await self.retrieve_chunks(query, limit=limit, protocol_id=protocol_id)
        return [chunk for chunk, _ in rows]

    def _build_context(self, chunks_with_titles: list[tuple[ProtocolChunk, str]]) -> tuple[str, list[dict]]:
        sources = []
        context_parts = []

        for i, (chunk, title) in enumerate(chunks_with_titles):
            source_id = f"[{i + 1}]"
            section = _extract_section_prefix(chunk.text_content)
            context_parts.append(
                f"Источник {source_id} (Протокол '{title}'"
                + (f", секция '{section}'" if section else "")
                + f"):\n{chunk.text_content}\n"
            )
            sources.append({
                "id": source_id,
                "protocol_id": chunk.protocol_id,
                "protocol_title": title,
                "section": section,
                "text": chunk.text_content,
            })

        return "\n".join(context_parts), sources

    async def ask_question(self, question: str, protocol_id: int | None = None) -> dict:
        chunks_with_titles = await self.retrieve_chunks(
            question, limit=18, protocol_id=protocol_id
        )

        if not chunks_with_titles:
            return {"answer": "Не найдено релевантной информации по вашему запросу.", "sources": []}

        context, sources = self._build_context(chunks_with_titles)
        user_prompt = f"ВОПРОС:\n{question}\n\nИСТОЧНИКИ ДЛЯ ОТВЕТА:\n{context}"

        t0 = time.perf_counter()
        answer = await llm_router.chat_completion_messages(
            system_prompt=RAG_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        if RAG_LLM_MS:
            RAG_LLM_MS.observe((time.perf_counter() - t0) * 1000)

        return {"answer": answer, "sources": sources}

    async def ask_question_stream(
        self, question: str, protocol_id: int | None = None
    ) -> AsyncIterator[str]:
        chunks_with_titles = await self.retrieve_chunks(
            question, limit=18, protocol_id=protocol_id
        )

        if not chunks_with_titles:
            yield json.dumps({"type": "error", "content": "Не найдено релевантной информации."})
            return

        context, sources = self._build_context(chunks_with_titles)
        yield json.dumps({"type": "sources", "content": sources})

        user_prompt = f"ВОПРОС:\n{question}\n\nИСТОЧНИКИ ДЛЯ ОТВЕТА:\n{context}"

        async for token in llm_router.chat_completion_stream(
            system_prompt=RAG_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        ):
            yield json.dumps({"type": "token", "content": token})

        yield json.dumps({"type": "done"})

    async def generate_clinical_task(self, protocol_id: int) -> StudentTask:
        protocol = await self.session.get(ClinicalProtocol, protocol_id)
        if not protocol:
            raise ValueError(f"Protocol {protocol_id} not found")

        prompt = f"""
        Вы опытный медицинский экзаменатор.
        Основываясь на следующем клиническом протоколе ({protocol.title}):
        {protocol.text_content[:20000]}...

        Сгенерируйте клиническую задачу для студента-медика.
        Формат ответа должен быть строго в JSON:
        {{
            "case_description": "Описание клинического случая",
            "expected_diagnosis": "Ожидаемый диагноз",
            "expected_treatment": "Краткий план лечения"
        }}
        """

        response_text = await llm_router.chat_completion_json_schema(
            name="clinical_task",
            schema=CLINICAL_TASK_JSON_SCHEMA,
            system_prompt="You generate clinically plausible medical teaching tasks and return only JSON.",
            user_prompt=prompt,
        )
        data = json.loads(response_text)

        task = StudentTask(
            protocol_id=protocol_id,
            case_description=data["case_description"],
            expected_diagnosis=data["expected_diagnosis"],
            expected_treatment=data["expected_treatment"],
        )
        self.session.add(task)
        await self.session.commit()
        return task

    async def validate_student_answer(
        self, task_id: int, student_id: int, student_answer: str
    ) -> StudentTaskAttempt:
        task = await self.session.get(StudentTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        protocol = await self.session.get(ClinicalProtocol, task.protocol_id)

        prompt = f"""
        Вы медицинский эксперт-оценщик.
        Задача: {task.case_description}
        Ожидаемый диагноз: {task.expected_diagnosis}
        Ожидаемое лечение по протоколу "{protocol.title}": {task.expected_treatment}
        Ответ студента: {student_answer}

        Оцените по 100-балльной шкале. Формат JSON:
        {{"score": 85, "feedback": "...", "is_correct_diagnosis": true, "is_correct_treatment": false}}
        """

        response_text = await llm_router.chat_completion_json_schema(
            name="student_answer_validation",
            schema=STUDENT_VALIDATION_JSON_SCHEMA,
            system_prompt="You grade medical student answers and return only JSON.",
            user_prompt=prompt,
        )
        validation_result = json.loads(response_text)

        attempt = StudentTaskAttempt(
            task_id=task_id,
            student_id=student_id,
            student_answer=student_answer,
            validation_result=validation_result,
            score=validation_result.get("score", 0),
        )
        self.session.add(attempt)
        await self.session.commit()
        return attempt

    async def generate_scenarios(self, protocol_ids: list[int]) -> list[dict]:
        protocols = []
        for pid in protocol_ids:
            p = await self.session.get(ClinicalProtocol, pid)
            if p:
                protocols.append(p)

        if not protocols:
            raise ValueError("Протоколы не найдены")

        context_parts = []
        for p in protocols:
            chunks = await self.retrieve_chunks(
                p.title, limit=5, protocol_ids=[p.id]
            )
            if chunks:
                text = "\n".join(c.text_content for c, _ in chunks)
            else:
                text = p.text_content[:8000]
            context_parts.append(f"Протокол '{p.title}':\n{text}")

        context = "\n\n".join(context_parts)

        prompt = f"""
        Вы опытный медицинский преподаватель. На основе клинических протоколов:
        {context}

        Сгенерируй 3-5 разнообразных клинических сценариев для студентов-медиков.
        ВАЖНО: все title и description — СТРОГО на русском языке, без английских слов.
        Для каждого сценария укажи:
        - difficulty: базовый / средний / сложный
        - target_competency: какая компетенция проверяется
        - expected_reasoning_steps: 3-6 ожидаемых шагов клинического рассуждения
        - red_flags: опасные признаки или критические ошибки, которые студент не должен пропустить

        Верни JSON:
        {{
          "scenarios": [
            {{
              "title": "...",
              "description": "...",
              "difficulty": "средний",
              "target_competency": "...",
              "expected_reasoning_steps": ["...", "..."],
              "red_flags": ["...", "..."]
            }}
          ]
        }}
        """

        response_text = await llm_router.chat_completion_json_schema(
            name="scenario_suggestions",
            schema=SCENARIO_SUGGESTIONS_JSON_SCHEMA,
            system_prompt="You generate clinically plausible teaching scenarios and return only JSON.",
            user_prompt=prompt,
        )
        import re
        match = re.search(r"\{[\s\S]*\}", response_text)
        if match:
            response_text = match.group()
        data = json.loads(response_text)
        scenarios = []
        for item in data.get("scenarios", []):
            if not isinstance(item, dict):
                continue
            scenarios.append({
                "title": str(item.get("title") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "difficulty": str(item.get("difficulty") or "").strip() or None,
                "target_competency": str(item.get("target_competency") or "").strip() or None,
                "expected_reasoning_steps": [
                    str(step).strip()
                    for step in item.get("expected_reasoning_steps", [])
                    if str(step).strip()
                ][:6],
                "red_flags": [
                    str(flag).strip()
                    for flag in item.get("red_flags", [])
                    if str(flag).strip()
                ][:6],
            })
        return scenarios

    def _normalize_graph_payload(self, raw: dict) -> tuple[dict, list[str]]:
        warnings: list[str] = []
        nodes = raw.get("nodes", [])
        edges = raw.get("edges", [])

        category_map = {e.value: e for e in NodeType}
        edge_map = {e.value: e for e in EdgeType}

        normalized_nodes = []
        for node in nodes:
            data = node.get("data", {})
            node_type_raw = str(node.get("type", "")).upper().strip()
            category_candidates = [
                data.get("category"),
                node.get("category"),
                node_type_raw,
            ]
            cat_raw = next(
                (
                    str(candidate).upper().strip()
                    for candidate in category_candidates
                    if str(candidate).upper().strip() in category_map
                ),
                "SYMPTOM",
            )
            if cat_raw not in category_map:
                warnings.append(f"Неизвестная категория '{cat_raw}' → SYMPTOM")
                cat_raw = "SYMPTOM"
            label = str(data.get("label", "")).strip()
            inferred_category = _infer_category_from_label(label, cat_raw)
            if inferred_category and inferred_category != cat_raw:
                warnings.append(
                    f"Категория узла '{label}' уточнена: {cat_raw} → {inferred_category}"
                )
                cat_raw = inferred_category
            node_type = node.get("type", "med")
            if str(node_type).upper().strip() in category_map:
                node_type = "med"

            normalized_nodes.append({
                "id": str(node.get("id", f"node_{len(normalized_nodes)}")),
                "type": node_type,
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": label,
                    "category": cat_raw,
                },
            })

        normalized_edges = []
        node_categories = {
            node["id"]: node["data"]["category"]
            for node in normalized_nodes
        }
        for edge in edges:
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source not in node_categories or target not in node_categories:
                warnings.append(f"Связь '{edge.get('id')}' пропущена: неизвестный source/target")
                continue

            rel_raw = str(edge.get("label", "DETERMINES")).upper().strip()
            if rel_raw not in edge_map:
                warnings.append(f"Неизвестный тип связи '{rel_raw}' → DETERMINES")
                rel_raw = "DETERMINES"

            source_category = node_categories[source]
            target_category = node_categories[target]
            if rel_raw == "INDICATED_FOR" and not (
                source_category == "DIAGNOSIS"
                and target_category in {"MEDICATION", "SURGERY", "MONITORING"}
            ):
                replacement = "REQUIRES_CONFIRMATION" if source_category == "DIAGNOSIS" else "DETERMINES"
                warnings.append(
                    "Недопустимая связь INDICATED_FOR "
                    f"{source_category}->{target_category} → {replacement}"
                )
                rel_raw = replacement
            elif rel_raw == "CONTRAINDICATED_DUE_TO" and not (
                source_category in {"MEDICATION", "SURGERY"}
                and target_category in {"PATIENT_PROFILE", "DIAGNOSIS", "SYMPTOM"}
            ):
                warnings.append(
                    "Недопустимая связь CONTRAINDICATED_DUE_TO "
                    f"{source_category}->{target_category} → DETERMINES"
                )
                rel_raw = "DETERMINES"

            normalized_edges.append({
                "id": str(edge.get("id", f"edge_{len(normalized_edges)}")),
                "source": source,
                "target": target,
                "label": rel_raw,
            })

        return {"nodes": normalized_nodes, "edges": normalized_edges}, warnings

    async def _align_blocks_to_catalog(self, normalized: dict) -> dict:
        """Make every generated block exist in the catalog (Step 3 invariant).

        For each block: if a catalog node has the same lemma-key (and does not
        differ by a digit/single-letter discriminator — so «гепатит D» is never
        snapped onto «гепатит B»), rewrite the label to that catalog node's
        canonical wording (prefer curated over bulk-extracted). Otherwise ingest
        the block as a new protocol-grounded catalog node so the invariant holds.
        """
        source_rank = {
            "protocol_graph": 0, "medelement": 1, "medelement_terms": 1,
            "clinical_protocols": 2, "protocols": 2, "protocol_extracted": 3,
        }
        skip_types = {"frame", "group"}
        snapped = ingested = 0

        for node in normalized.get("nodes", []):
            if node.get("type") in skip_types:
                continue
            data = node.get("data") or {}
            category = str(data.get("category") or "").upper().strip()
            label = (data.get("label") or "").strip()
            db_category = _GRAPH_CATEGORY_TO_DB.get(category)
            if not db_category or not label:
                continue

            key = morphology.lemmas(label) or frozenset({label.lower()})
            tokens = list(morphology.lemmas(label))
            pool_stmt = (
                select(MedicalNode)
                .where(MedicalNode.category == db_category)
                .where(MedicalNode.source.in_(_CATALOG_SOURCES))
            )
            if tokens:
                pool_stmt = pool_stmt.where(
                    or_(*[MedicalNode.name.ilike(f"%{t}%") for t in tokens])
                )
            pool = list((await self.session.execute(pool_stmt.limit(200))).scalars().all())

            label_raw = set(re.findall(r"[a-zа-яё0-9]+", label.lower()))
            best = None
            for row in pool:
                if row.name.strip().lower() == label.lower():
                    best = row
                    break
                row_key = morphology.lemmas(row.name) or frozenset({row.name.lower()})
                if row_key != key:
                    continue
                # Same lemma-key, but block the letter/digit discriminator case
                # that lemmatisation hides (D↔B, IgG↔IgM, 45↔55).
                symdiff = label_raw ^ set(re.findall(r"[a-zа-яё0-9]+", row.name.lower()))
                if any(len(t) == 1 or any(c.isdigit() for c in t) for t in symdiff):
                    continue
                if best is None or source_rank.get(row.source, 9) < source_rank.get(best.source, 9):
                    best = row

            if best is not None:
                if best.name != label:
                    data["label"] = best.name
                    snapped += 1
            else:
                self.session.add(MedicalNode(name=label, category=db_category, source="protocol_graph"))
                ingested += 1

        if ingested:
            await self.session.flush()
        return {"snapped": snapped, "ingested": ingested}

    async def generate_reference_graph(
        self,
        protocol_ids: list[int],
        scenario_title: str,
        scenario_description: str,
    ) -> dict:
        protocols = []
        for pid in protocol_ids:
            p = await self.session.get(ClinicalProtocol, pid)
            if p:
                protocols.append(p)

        if not protocols:
            raise ValueError("Протоколы не найдены")

        query = f"{scenario_title}. {scenario_description}"
        chunks_with_titles = await self.retrieve_chunks(
            query, limit=10, protocol_ids=protocol_ids
        )

        generation_context = []
        context_parts = []
        for chunk, title in chunks_with_titles:
            section = _extract_section_prefix(chunk.text_content)
            generation_context.append({
                "protocol_id": chunk.protocol_id,
                "protocol_title": title,
                "section": section,
                "chunk_index": chunk.chunk_index,
                # store the retrieved text so the RAG evidence the LLM relied on
                # is auditable (kept bounded for storage).
                "text": (chunk.text_content or "")[:1500],
            })
            context_parts.append(
                f"[Протокол '{title}'"
                + (f", секция '{section}'" if section else "")
                + f"]:\n{chunk.text_content}"
            )

        if not context_parts:
            for p in protocols:
                context_parts.append(f"Протокол '{p.title}':\n{p.text_content[:8000]}")

        context = "\n\n".join(context_parts)

        prompt = f"""
        Вы медицинский эксперт-методист по методологии MedConstructor.
        Клинический сценарий:
        Название: {scenario_title}
        Описание: {scenario_description}

        Релевантные выдержки из клинических протоколов:
        {context}

        Постройте эталонный граф клинического мышления (ReferenceGraph).
        {MEDCONSTRUCTOR_GRAPH_RULES}

        Верни СТРОГО JSON:
        {{
          "nodes": [
            {{"id": "node_1", "type": "med", "data": {{"label": "Кашель", "category": "SYMPTOM"}}}}
          ],
          "edges": [
            {{"id": "edge_1", "source": "node_1", "target": "node_2", "label": "DETERMINES"}}
          ]
        }}

        Построй полный граф клинического мышления:
        - профиль пациента, симптомы, обследования (осмотр/лаборатория/инструментальная), диагноз, лечение;
        - где протокол это поддерживает, ОБЯЗАТЕЛЬНО добавь:
          * MONITORING — шаг наблюдения/контроля после начала лечения;
          * CONTRAINDICATED_DUE_TO — хотя бы одно противопоказание/red-flag безопасности
            (от MEDICATION/SURGERY к фактору пациента, диагнозу или симптому), если в протоколе
            есть противопоказания, предостережения или меры предосторожности;
          * EXCLUDES — ключевой дифференциальный диагноз, который нужно исключить, если протокол
            описывает дифференциальную диагностику или опасные альтернативы.
        Не выдумывай противопоказания и исключения, которых нет в протоколе; но если они есть —
        не пропускай их, так как безопасность является центральным элементом оценки.

        Клинические guardrails для высокорисковых кардиологических сценариев:
        - STEMI / инфаркт миокарда с подъемом ST: ЭКГ с подъемом ST является диагностическим якорем
          экстренной тактики; тропонин можно добавить как лабораторный шаг, но НЕЛЬЗЯ строить граф так,
          будто реперфузия ожидает результат тропонина. Обязательно добавляй явную стратегию реперфузии
          (первичное ЧКВ; фибринолиз при задержке ЧКВ и отсутствии противопоказаний, если это следует
          из протокола).
        - ТЭЛА: при высокой клинической вероятности не используй D-димер как подтверждающий тест.
          Диагноз должен быть связан с визуализацией (КТ-ангиопульмонография/КТ-ангиография или другой
          подтверждающий метод из протокола). Отдельно отражай гемодинамическую нестабильность,
          риск кровотечения и показания/противопоказания к тромболизису или антикоагуляции.
        - Легочная гипертензия: ЭхоКГ формирует подозрение/вероятность, но не должно напрямую
          подтверждать окончательный диагноз. Для финального диагноза добавляй катетеризацию правых
          отделов сердца или гемодинамическое подтверждение, если это предусмотрено протоколом.
          Лечение связывай с диагнозом после определения этиологии/клинической группы.
        - Фибрилляция предсердий: перед антикоагуляцией добавляй оценку риска инсульта, риска
          кровотечения/почечной функции и исключение клапанной ФП (механический клапан/митральный
          стеноз), если это релевантно протоколу.
        - Расслоение аорты: диагноз должен быть связан с КТ-ангиографией или другим подтверждающим
          методом из протокола. Тромболизис при подозрении на расслоение должен быть противопоказан.
          Для Stanford A добавляй срочную хирургическую маршрутизацию, обезболивание и контроль
          АД/ЧСС.
        - Гипертоническая экстренная ситуация: обязательно показывай поражение органов-мишеней,
          профильное обследование (например, нейровизуализацию при неврологических симптомах) и
          управляемое снижение АД; не изображай тактику как немедленную нормализацию давления.

        Связность (ОБЯЗАТЕЛЬНО): у каждого узла должна быть хотя бы одна связь, изолированных узлов быть не должно.
        - Фактор противопоказания бери из УЖЕ существующих узлов профиля пациента или симптомов
          (CONTRAINDICATED_DUE_TO от препарата/операции к этому узлу); не создавай отдельный «висячий» узел.
        - Исключаемый дифференциальный диагноз присоединяй ребром EXCLUDES от того исследования,
          симптома или основного диагноза, который его исключает (источник EXCLUDES → исключаемый диагноз).
        - Основной (рабочий) диагноз обязан иметь входящее ребро от диагностического узла
          (осмотр/лаборатория/инструментальное исследование).

        ЯЗЫК: все label узлов — СТРОГО на русском языке (медицинская терминология),
        без английских слов и транслитерации.

        ТЕРМИНОЛОГИЯ: используй стандартные, общепринятые названия из клинических
        протоколов (как в справочниках), а не свободные переформулировки —
        например «ЭКГ», «общий анализ крови», «инфаркт миокарда», а не описательные
        варианты. Это нужно, чтобы блоки совпадали с каталогом.
        """

        response_text = await llm_router.chat_completion_json_schema(
            name="medconstructor_reference_graph",
            schema=GRAPH_JSON_SCHEMA,
            system_prompt="You generate valid MedConstructor reference graphs and return only JSON.",
            user_prompt=prompt,
        )
        import re
        match = re.search(r"\{[\s\S]*\}", response_text)
        if match:
            response_text = match.group()
        raw_graph = json.loads(response_text)

        normalized, warnings = self._normalize_graph_payload(raw_graph)

        # Step 3: snap generated blocks onto existing catalog wording / ingest new
        # ones, so every reference block exists in the catalog (task is solvable
        # and the graph uses shared vocabulary rather than free-text variants).
        alignment = await self._align_blocks_to_catalog(normalized)

        # Step 4: guarantee a single connected clinical graph. The LLM sometimes
        # leaves blocks in a detached island; reconnect them to the main chain
        # (or prune if no clinically-valid bridge exists) so a detached sub-graph
        # can never reach persistence. Every change is surfaced for teacher review.
        repaired_nodes, repaired_edges, repair_actions = repair_graph_connectivity(
            normalized["nodes"], normalized["edges"]
        )
        normalized = {"nodes": repaired_nodes, "edges": repaired_edges}
        for action in repair_actions:
            if action["type"] == "reconnected":
                edge = action["edge"]
                warnings.append(
                    f"AUTO-RECONNECT: блок '{action['entry_label']}' присоединён к основной цепочке "
                    f"({edge['source']}→{edge['target']} {edge['label']}) — проверьте корректность связи."
                )
            else:
                warnings.append(
                    "AUTO-PRUNE: удалены оторванные блоки без клинически корректной связи: "
                    + ", ".join(str(lbl) for lbl in action["labels"])
                )

        graph_schema = None
        try:
            graph_schema = GraphSchema.model_validate(normalized)
        except Exception as exc:
            warnings.append(f"Валидация схемы: {exc}")

        generation_quality = None
        if graph_schema:
            generation_quality = judge_reference_graph(graph_schema)
            warnings.extend(
                format_quality_warning(warning)
                for warning in generation_quality.get("warnings", [])
            )
        else:
            generation_quality = {
                "schema_valid": False,
                "accepted": False,
                "quality_score": 0.0,
                "warning_count": len(warnings),
                "critical_count": 1,
                "warnings": [],
            }

        return {
            "graph": graph_schema.model_dump() if graph_schema else normalized,
            "generation_context": generation_context,
            "validation_warnings": warnings,
            "generation_quality": generation_quality,
            "catalog_alignment": alignment,
        }
