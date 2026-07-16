from types import SimpleNamespace

from app.services.rag_service import (
    RAGService,
    _extract_section_prefix,
    _keyword_overlap_boost,
    _title_match_boost,
)


def test_normalize_graph_payload_uses_node_type_as_category_fallback():
    service = RAGService(session=None)
    raw = {
        "nodes": [
            {
                "id": "n1",
                "type": "PATIENT_PROFILE",
                "data": {"label": "Пациентка, 32 года"},
            },
            {
                "id": "n2",
                "type": "DIAGNOSIS",
                "data": {"label": "Хроническая артериальная гипертензия"},
            },
            {
                "id": "n3",
                "type": "MEDICATION",
                "data": {"label": "Гипотензивная терапия"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "n2", "target": "n3", "label": "INDICATED_FOR"},
        ],
    }

    normalized, warnings = service._normalize_graph_payload(raw)

    assert warnings == []
    assert [node["data"]["category"] for node in normalized["nodes"]] == [
        "PATIENT_PROFILE",
        "DIAGNOSIS",
        "MEDICATION",
    ]
    assert {node["type"] for node in normalized["nodes"]} == {"med"}


def test_dedup_and_rerank_filters_low_signal_chunks():
    service = RAGService(session=None)
    noisy = SimpleNamespace(
        protocol_id=1,
        chunk_index=1,
        text_content="[Секция: Внимание!] Разделы Закрыть список разделов",
    )
    useful = SimpleNamespace(
        protocol_id=2,
        chunk_index=1,
        text_content=(
            "[Секция: Лечение]\n"
            "Гипотензивная терапия при беременности проводится при повышенном "
            "артериальном давлении с мониторингом состояния матери и плода."
        ),
    )

    ranked = service._dedup_and_rerank(
        [
            (noisy, "Нерелевантный протокол", 0.01),
            (useful, "Артериальная гипертензия у беременных", 0.50),
        ],
        "гипотензивная терапия при беременности",
        final_k=5,
    )

    assert [chunk.protocol_id for chunk, _, _ in ranked] == [2]


def test_keyword_overlap_uses_medical_term_expansions():
    assert _keyword_overlap_boost(
        "артериальная гипертензия лечение",
        "Гипотензивная терапия",
    ) > 0.5


def test_title_match_prioritizes_disease_terms_over_generic_section_words():
    query = "Анафилактический шок диагностика неотложная помощь адреналин лечение госпитализация"

    assert _title_match_boost(query, "Анафилактический шок") > _title_match_boost(
        query,
        "Диагностика и лечение акромегалии и гигантизма",
    )


def test_title_match_ignores_generic_clinical_protocol_words():
    query = "Язвенный колит у детей клинический протокол диагностика лечение"

    assert _title_match_boost(query, "Язвенный колит у детей") > _title_match_boost(
        query,
        "Приложение к клиническим протоколам по хирургии",
    )


def test_dedup_and_rerank_diversifies_requested_section_intents():
    service = RAGService(session=None)

    def chunk(protocol_id: int, index: int, section: str, body: str):
        return SimpleNamespace(
            protocol_id=protocol_id,
            chunk_index=index,
            text_content=f"[Секция: {section}]\n{body}",
        )

    long_tail = " ".join(["клинические данные пациентки"] * 30)
    candidates = [
        (
            chunk(86, 1, "Краткое описание", "Артериальная гипертензия у беременных. " + long_tail),
            "Артериальная гипертензия у беременных",
            0.02,
        ),
        (
            chunk(86, 2, "Лечение", "Гипотензивная терапия и выбор тактики родоразрешения. " + long_tail),
            "Артериальная гипертензия у беременных",
            0.08,
        ),
        (
            chunk(86, 3, "Диагностика", "Диагностические критерии и обследование беременной. " + long_tail),
            "Артериальная гипертензия у беременных",
            0.10,
        ),
        (
            chunk(86, 4, "Наблюдение за плодом", "Мониторинг состояния плода и антенатальное наблюдение. " + long_tail),
            "Артериальная гипертензия у беременных",
            0.90,
        ),
    ]

    ranked = service._dedup_and_rerank(
        candidates,
        "артериальная гипертензия у беременных диагностика лечение мониторинг плода",
        final_k=3,
    )
    sections = [_extract_section_prefix(chunk.text_content) for chunk, _, _ in ranked]

    assert "Диагностика" in sections
    assert "Лечение" in sections
    assert "Наблюдение за плодом" in sections


def test_dedup_and_rerank_keeps_short_target_section():
    service = RAGService(session=None)
    short_monitoring = SimpleNamespace(
        protocol_id=86,
        chunk_index=52,
        text_content="[Секция: Наблюдение за плодом]\nКТГ плода.",
    )
    generic = SimpleNamespace(
        protocol_id=86,
        chunk_index=1,
        text_content="[Секция: Краткое описание]\n" + " ".join(["артериальная гипертензия"] * 50),
    )

    ranked = service._dedup_and_rerank(
        [
            (generic, "Артериальная гипертензия у беременных", 0.01),
            (short_monitoring, "Артериальная гипертензия у беременных", 0.80),
        ],
        "мониторинг плода при артериальной гипертензии у беременных",
        final_k=2,
    )
    sections = [_extract_section_prefix(chunk.text_content) for chunk, _, _ in ranked]

    assert "Наблюдение за плодом" in sections


def test_dedup_and_rerank_deprioritizes_low_value_sections_for_targeted_query():
    service = RAGService(session=None)

    def chunk(index: int, section: str, body: str):
        return SimpleNamespace(
            protocol_id=86,
            chunk_index=index,
            text_content=f"[Секция: {section}]\n{body}",
        )

    filler = " ".join(["артериальная гипертензия у беременных"] * 25)
    ranked = service._dedup_and_rerank(
        [
            (chunk(1, "Краткое описание", filler), "Артериальная гипертензия у беременных", 0.01),
            (chunk(2, "Диагностика", "Диагностические критерии. " + filler), "Артериальная гипертензия у беременных", 0.20),
            (chunk(3, "Гипотензивная терапия", "Лечение и гипотензивная терапия. " + filler), "Артериальная гипертензия у беременных", 0.25),
        ],
        "артериальная гипертензия у беременных диагностика лечение",
        final_k=2,
    )
    sections = [_extract_section_prefix(chunk.text_content) for chunk, _, _ in ranked]

    assert "Краткое описание" not in sections
    assert set(sections) == {"Диагностика", "Гипотензивная терапия"}


def test_dedup_and_rerank_includes_prevention_intent():
    service = RAGService(session=None)
    filler = " ".join(["послеродовое кровотечение клиническая тактика"] * 20)
    treatment = SimpleNamespace(
        protocol_id=59,
        chunk_index=1,
        text_content="[Секция: Лечение]\n" + filler,
    )
    prevention = SimpleNamespace(
        protocol_id=59,
        chunk_index=2,
        text_content="[Секция: Профилактика РПК]\nПрофилактика послеродового кровотечения. " + filler,
    )

    ranked = service._dedup_and_rerank(
        [
            (treatment, "Послеродовое кровотечение", 0.05),
            (prevention, "Послеродовое кровотечение", 0.60),
        ],
        "послеродовое кровотечение лечение профилактика",
        final_k=2,
    )
    sections = [_extract_section_prefix(chunk.text_content) for chunk, _, _ in ranked]

    assert "Профилактика РПК" in sections


def test_normalize_graph_payload_downgrades_invalid_indicated_for_edge():
    service = RAGService(session=None)
    raw = {
        "nodes": [
            {
                "id": "diagnosis",
                "type": "med",
                "data": {"label": "Преэклампсия", "category": "DIAGNOSIS"},
            },
            {
                "id": "exam",
                "type": "med",
                "data": {"label": "Физикальный осмотр", "category": "EXAM"},
            },
        ],
        "edges": [
            {
                "id": "edge_1",
                "source": "diagnosis",
                "target": "exam",
                "label": "INDICATED_FOR",
            }
        ],
    }

    normalized, warnings = service._normalize_graph_payload(raw)

    assert normalized["edges"][0]["label"] == "REQUIRES_CONFIRMATION"
    assert any("Недопустимая связь INDICATED_FOR" in warning for warning in warnings)


def test_normalize_graph_payload_reclassifies_monitoring_from_medication():
    service = RAGService(session=None)
    raw = {
        "nodes": [
            {
                "id": "diagnosis",
                "type": "med",
                "data": {"label": "Гестационная гипертензия", "category": "DIAGNOSIS"},
            },
            {
                "id": "monitoring",
                "type": "med",
                "data": {"label": "Контроль артериального давления", "category": "MEDICATION"},
            },
        ],
        "edges": [
            {
                "id": "edge_1",
                "source": "diagnosis",
                "target": "monitoring",
                "label": "INDICATED_FOR",
            }
        ],
    }

    normalized, warnings = service._normalize_graph_payload(raw)

    assert normalized["nodes"][1]["data"]["category"] == "MONITORING"
    assert normalized["edges"][0]["label"] == "INDICATED_FOR"
    assert any("уточнена: MEDICATION → MONITORING" in warning for warning in warnings)
