"""Russian localization helpers for cardiology demo benchmark cases."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CASE_RU_META: dict[str, dict[str, Any]] = {
    "cardio_chronic_hf_10": {
        "title": "Хроническая сердечная недостаточность: фенотип, терапия по протоколу и мониторинг",
        "task": {
            "title": "Хроническая сердечная недостаточность: фенотип, терапия по протоколу и мониторинг",
            "description": (
                "Пациент с одышкой, периферическими отёками и сниженной переносимостью нагрузки. "
                "Постройте граф, который связывает клиническую застойность, эхокардиографический фенотип "
                "и натрийуретические пептиды с ведением хронической сердечной недостаточности, "
                "болезнь-модифицирующей терапией и мониторингом."
            ),
            "protocol_focus": "Хроническая сердечная недостаточность",
            "target_competency": (
                "Построить граф хронической сердечной недостаточности с сохранением "
                "непрерывности пути от диагноза к терапии."
            ),
            "expected_sections": [
                "оценка застойности",
                "эхокардиография",
                "натрийуретические пептиды",
                "болезнь-модифицирующая терапия",
                "мониторинг",
            ],
            "checklist": [
                "выявить признаки застойности",
                "подтвердить дисфункцию сердца",
                "связать диагноз с терапией по протоколу",
                "включить мониторинг",
                "избегать изолированной симптоматической терапии без диагноза",
            ],
            "red_flags": [
                "отсутствие болезнь-модифицирующей терапии при подтверждённой сердечной недостаточности",
            ],
        },
    },
    "cardio_pulmonary_htn_11": {
        "title": "Лёгочная гипертензия: эхо-подозрение и подтверждающий путь",
        "task": {
            "title": "Лёгочная гипертензия: эхо-подозрение и подтверждающий путь",
            "description": (
                "У пациента необъяснимая одышка, признаки перегрузки правых отделов сердца "
                "и эхокардиографическая вероятность лёгочной гипертензии. Граф должен разделять "
                "подозрение и подтверждённый диагноз, включать гемодинамическое подтверждение "
                "и путь специализированного лечения."
            ),
            "protocol_focus": "Лёгочная гипертензия",
            "target_competency": (
                "Построить граф лёгочной гипертензии с разделением подозрения, "
                "подтверждения и терапевтического пути."
            ),
            "expected_sections": [
                "клиническое подозрение",
                "эхокардиография",
                "катетеризация сердца",
                "этиология",
                "специализированная терапия",
            ],
            "checklist": [
                "зафиксировать клиническое подозрение",
                "подтвердить вероятность по ЭхоКГ",
                "включить инвазивную оценку при необходимости",
                "связать диагноз с лечением",
            ],
            "red_flags": [
                "назначение специфической терапии без подтверждения диагноза",
            ],
        },
    },
    "cardio_mitral_stenosis_pregnancy_12": {
        "title": "Беременность при митральном стенозе: риск, наблюдение и тактика",
        "task": {
            "title": "Беременность при митральном стенозе: риск, наблюдение и тактика",
            "description": (
                "Беременная пациентка с митральным стенозом требует графа, который связывает "
                "клиническую картину, эхокардиографическое подтверждение, оценку гемодинамического "
                "риска, тактику ведения беременности и мониторинг."
            ),
            "protocol_focus": "Ведение беременности при митральном стенозе",
            "target_competency": (
                "Построить безопасный граф ведения беременности при митральном стенозе "
                "с учётом риска декомпенсации."
            ),
        },
    },
}

NODE_LABEL_RU: dict[str, str] = {
    "Patient with dyspnea, edema and reduced exercise tolerance": (
        "Пациент с одышкой, отёками и сниженной переносимостью нагрузки"
    ),
    "Progressive exertional dyspnea and peripheral edema": (
        "Нарастающая одышка при нагрузке и периферические отёки"
    ),
    "Echocardiography shows reduced or abnormal ventricular function": (
        "ЭхоКГ: сниженная или нарушенная функция желудочков"
    ),
    "Elevated natriuretic peptides support heart failure": (
        "Повышенные натрийуретические пептиды в пользу сердечной недостаточности"
    ),
    "Chronic heart failure": "Хроническая сердечная недостаточность",
    "Guideline-directed disease-modifying therapy": (
        "Болезнь-модифицирующая терапия по клиническому протоколу"
    ),
    "Volume management and referral for advanced care when indicated": (
        "Коррекция объёма и направление на специализированную помощь при показаниях"
    ),
    "Renal function, potassium, blood pressure, symptoms and weight": (
        "Функция почек, калий, АД, симптомы и масса тела"
    ),
    "Patient with unexplained dyspnea and syncope episodes": (
        "Пациент с необъяснимой одышкой и эпизодами обмороков"
    ),
    "Pulmonary hypertension with defined etiology": (
        "Лёгочная гипертензия с установленной этиологией"
    ),
    "Dyspnea and reduced exercise tolerance during pregnancy": (
        "Одышка и снижение переносимости нагрузки во время беременности"
    ),
    "Echocardiography confirms significant mitral stenosis": (
        "ЭхоКГ подтверждает значимый митральный стеноз"
    ),
    "Dyspnea with signs of right heart overload": (
        "Одышка с признаками перегрузки правых отделов сердца"
    ),
    "Echo suggests high probability of pulmonary hypertension": (
        "ЭхоКГ: высокая вероятность лёгочной гипертензии"
    ),
    "Right-heart catheterization confirms hemodynamics": (
        "Катетеризация правых отделов подтверждает гемодинамику"
    ),
    "Etiology-specific pulmonary hypertension therapy": (
        "Этиотропная терапия лёгочной гипертензии"
    ),
    "Referral to pulmonary hypertension specialist center": (
        "Направление в специализированный центр лёгочной гипертензии"
    ),
    "Functional class, oxygenation, echo and treatment tolerance": (
        "Функциональный класс, оксигенация, ЭхоКГ и переносимость терапии"
    ),
    "Pregnant patient with known rheumatic mitral stenosis": (
        "Беременная пациентка с ревматическим митральным стенозом"
    ),
    "Maternal-fetal risk stratification is high": (
        "Высокий материнско-плодовый риск при стратификации"
    ),
    "Pregnancy complicated by significant mitral stenosis": (
        "Беременность, осложнённая значимым митральным стенозом"
    ),
    "Pregnancy-compatible rate control and anticoagulation when indicated": (
        "Контроль ЧСС и антикоагуляция, совместимые с беременностью, при показаниях"
    ),
    "Multidisciplinary cardiology-obstetric intervention planning": (
        "Междисциплинарное кардио-акушерское планирование вмешательства"
    ),
    "Maternal hemodynamics, fetal status and decompensation signs": (
        "Материнская гемодинамика, состояние плода и признаки декомпенсации"
    ),
}

DEMO_TIME_LIMIT_MINUTES = 45


def _localize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(graph)
    for node in payload.get("nodes") or []:
        data = node.get("data") or {}
        label = data.get("label")
        if isinstance(label, str) and label in NODE_LABEL_RU:
            data["label"] = NODE_LABEL_RU[label]
            node["data"] = data
    return payload


def localize_case(case: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(case)
    case_id = payload.get("case_id")
    meta = CASE_RU_META.get(case_id)
    if meta:
        if meta.get("title"):
            payload["title"] = meta["title"]
        task = payload.setdefault("task", {})
        task_meta = meta.get("task") or {}
        for key, value in task_meta.items():
            task[key] = value

    payload["reference_graph"] = _localize_graph(payload.get("reference_graph") or {})
    for variant in payload.get("variants") or []:
        student_graph = variant.get("student_graph")
        if isinstance(student_graph, dict):
            variant["student_graph"] = _localize_graph(student_graph)
    return payload
