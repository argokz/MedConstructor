from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import app.services.graph_evaluator as graph_evaluator_module
from app.schemas import GraphSchema
from app.services.benchmarking import aggregate_graph_quality_results, aggregate_graph_results
from app.services.expert_evaluation import analyze_expert_ratings
from app.services.graph_evaluator import GraphEvaluator
from app.services.graph_generation_judge import judge_reference_graph


CARDIOLOGY_ALGORITHM_VERSION = "cardiology-synthetic-1.0"
DEFAULT_SEED = 20260617
EXPERT_EVALUATION_SCALE = "0-100 raw score, normalized to 0-1 for analysis"
EXPERT_PANEL_MODE = "synthetic_proxy"
DEFAULT_PROTOCOL_SOURCE_IDS: dict[str, dict[str, Any]] = {
    "cardio_stemi_01": {
        "protocol_id": 489,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_nstemi_02": {
        "protocol_id": 495,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_hf_03": {
        "protocol_id": 493,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_af_04": {
        "protocol_id": 502,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_htn_05": {
        "protocol_id": 482,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_dissection_06": {
        "protocol_id": 169,
        "source_fit": "adjacent_aorta_protocol",
        "source_note": (
            "No direct aortic dissection protocol was found in the local cardiology "
            "section; this red-flag control case is anchored to the nearest aortic "
            "vascular protocol in the knowledge base."
        ),
    },
    "cardio_pe_07": {
        "protocol_id": 501,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_endocarditis_08": {
        "protocol_id": 494,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_stable_angina_09": {
        "protocol_id": 488,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_chronic_hf_10": {
        "protocol_id": 504,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_pulmonary_htn_11": {
        "protocol_id": 490,
        "source_fit": "direct_cardiology_protocol",
    },
    "cardio_mitral_stenosis_pregnancy_12": {
        "protocol_id": 9,
        "source_fit": "direct_cardiology_protocol",
    },
}

GRAPH_METRIC_KEYS = (
    "edge_f1",
    "weighted_edge_f1",
    "node_coverage",
    "category_accuracy",
    "directed_path_completeness",
    "safety_penalty",
    "unsafe_extra_action",
    "missing_critical_action",
    "diagnostic_evidence_gap",
    "clinical_connectivity_gap",
    "composite_score",
)

PATTERN_EXPERT_TARGETS = {
    "all_metrics_high": 0.97,
    "recall_and_node_coverage_drop": 0.58,
    "category_accuracy_drop": 0.78,
    "missing_critical_action_penalty": 0.50,
    "critical_relation_penalty": 0.45,
    "unsafe_extra_action_cap": 0.34,
    "directed_path_drop": 0.55,
    "directed_path_zero": 0.38,
}

PATTERN_NOISE = {
    "all_metrics_high": 0.015,
    "category_accuracy_drop": 0.045,
    "recall_and_node_coverage_drop": 0.055,
    "missing_critical_action_penalty": 0.06,
    "critical_relation_penalty": 0.065,
    "unsafe_extra_action_cap": 0.07,
    "directed_path_drop": 0.055,
    "directed_path_zero": 0.06,
}

PATTERN_COMMENTS = {
    "all_metrics_high": "Решение клинически полное: сохранена диагностическая цепочка и терапевтические действия.",
    "recall_and_node_coverage_drop": "Существенно неполный ответ: пропущен диагностический или клинический элемент.",
    "category_accuracy_drop": "Содержание в целом распознано, но нарушена клиническая классификация узла.",
    "missing_critical_action_penalty": "Пропущено критически важное действие лечения или мониторинга.",
    "critical_relation_penalty": "Неверно отражена критическая связь, влияющая на безопасность решения.",
    "unsafe_extra_action_cap": "Добавлено потенциально опасное действие, которое эксперт должен резко штрафовать.",
    "directed_path_drop": "Нарушена причинно-диагностическая цепочка от данных пациента к решению.",
    "directed_path_zero": "Клиническая цепочка практически разорвана.",
}


def _generated_at() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _node(node_id: str, label: str, category: str, x: float, y: float) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "default",
        "position": {"x": x, "y": y},
        "data": {"label": label, "category": category},
    }


def _edge(edge_id: str, source: str, target: str, label: str) -> dict[str, Any]:
    return {"id": edge_id, "source": source, "target": target, "label": label}


def _graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"nodes": nodes, "edges": edges}
    GraphSchema.model_validate(payload)
    return payload


def _without_node(graph: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    payload = deepcopy(graph)
    payload["nodes"] = [node for node in payload.get("nodes", []) if str(node.get("id")) != node_id]
    payload["edges"] = [
        edge
        for edge in payload.get("edges", [])
        if str(edge.get("source")) != node_id and str(edge.get("target")) != node_id
    ]
    GraphSchema.model_validate(payload)
    return payload


def _without_edge(graph: Mapping[str, Any], edge_id: str) -> dict[str, Any]:
    payload = deepcopy(graph)
    payload["edges"] = [edge for edge in payload.get("edges", []) if str(edge.get("id")) != edge_id]
    GraphSchema.model_validate(payload)
    return payload


def _change_category(graph: Mapping[str, Any], node_id: str, category: str) -> dict[str, Any]:
    payload = deepcopy(graph)
    for node in payload.get("nodes", []):
        if str(node.get("id")) == node_id:
            node.setdefault("data", {})["category"] = category
            break
    GraphSchema.model_validate(payload)
    return payload


def _add_indicated_medication(
    graph: Mapping[str, Any],
    diagnosis_id: str,
    medication_id: str,
    label: str,
) -> dict[str, Any]:
    payload = deepcopy(graph)
    payload.setdefault("nodes", []).append(
        _node(medication_id, label, "MEDICATION", 900.0, 500.0)
    )
    payload.setdefault("edges", []).append(
        _edge(f"e_{diagnosis_id}_{medication_id}", diagnosis_id, medication_id, "INDICATED_FOR")
    )
    GraphSchema.model_validate(payload)
    return payload


def _replace_contraindication_with_indication(
    graph: Mapping[str, Any],
    diagnosis_id: str,
    medication_id: str,
    contraindication_edge_id: str,
) -> dict[str, Any]:
    payload = _without_edge(graph, contraindication_edge_id)
    payload.setdefault("edges", []).append(
        _edge(f"e_{diagnosis_id}_{medication_id}_unsafe_indication", diagnosis_id, medication_id, "INDICATED_FOR")
    )
    GraphSchema.model_validate(payload)
    return payload


def _student_graph_payload(reference_graph: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    explicit = variant.get("student_graph")
    if explicit == "__same_as_reference__":
        return deepcopy(reference_graph)
    if isinstance(explicit, dict):
        return deepcopy(explicit)
    raise ValueError(f"Cardiology synthetic variant has no explicit student_graph: {variant.get('variant_id')}")


def _graph_pattern_check(pattern: str | None, metrics: Mapping[str, Any]) -> dict[str, Any]:
    if not pattern:
        return {"passed": None, "reason": "No expected_pattern provided."}

    composite = float(metrics.get("composite_score") or 0.0)
    weighted_edge_f1 = float(metrics.get("weighted_edge_f1") or 0.0)
    node_coverage = float(metrics.get("node_coverage") or 0.0)
    category_accuracy = float(metrics.get("category_accuracy") or 0.0)
    directed_path = float(metrics.get("directed_path_completeness") or 0.0)
    unsafe_extra = float(metrics.get("unsafe_extra_action") or 0.0)
    missing_critical = float(metrics.get("missing_critical_action") or 0.0)
    safety_penalty = float(metrics.get("safety_penalty") or 0.0)

    checks = {
        "all_metrics_high": (
            composite >= 0.95
            and weighted_edge_f1 >= 0.95
            and node_coverage >= 0.95
            and category_accuracy >= 0.95
            and directed_path >= 0.95
            and safety_penalty == 0.0,
            "Expected a near-perfect graph with no safety penalty.",
        ),
        "recall_and_node_coverage_drop": (
            node_coverage < 0.95 and composite < 0.95,
            "Expected missing clinical content to reduce node coverage and composite score.",
        ),
        "category_accuracy_drop": (
            category_accuracy < 0.95 and composite < 1.0,
            "Expected a wrong node category to reduce category-aware metrics.",
        ),
        "critical_relation_penalty": (
            weighted_edge_f1 < 0.95 and composite < 0.90,
            "Expected an incorrect critical relation to reduce weighted edge F1 and composite score.",
        ),
        "unsafe_extra_action_cap": (
            unsafe_extra > 0.0 and composite <= 0.75,
            "Expected an extra unsafe action to trigger the hard score cap.",
        ),
        "directed_path_zero": (
            directed_path <= 0.05 and composite < 0.85,
            "Expected a broken clinical chain to collapse directed path completeness.",
        ),
        "directed_path_drop": (
            directed_path < 0.95 and composite < 0.95,
            "Expected a broken clinical chain to reduce directed path completeness.",
        ),
        "missing_critical_action_penalty": (
            missing_critical > 0.0 and composite <= 0.85,
            "Expected a missing critical treatment or contraindication edge to be penalized.",
        ),
    }
    passed, reason = checks.get(
        pattern,
        (None, f"No benchmark assertion is defined for expected_pattern={pattern!r}."),
    )
    return {"passed": passed, "reason": reason}


def _task_quality(task: Mapping[str, Any]) -> dict[str, Any]:
    criteria = {
        "has_protocol_focus": bool(task.get("protocol_focus")),
        "description_min_180_chars": len(str(task.get("description") or "")) >= 180,
        "has_expected_sections": len(task.get("expected_sections") or []) >= 3,
        "has_checklist": len(task.get("checklist") or []) >= 4,
        "has_red_flags": len(task.get("red_flags") or []) >= 1,
        "has_target_competency": bool(task.get("target_competency")),
    }
    score = round(sum(1 for passed in criteria.values() if passed) / len(criteria), 4)
    return {
        "task_quality_score": score,
        "task_quality_accepted": score >= 0.85,
        "task_quality_criteria": criteria,
    }


def _prune_to_main_component(graph: dict[str, Any]) -> dict[str, Any]:
    """Drop orphan nodes and disconnected clusters so a reference graph is one
    connected clinical chain (prefers the component holding a DIAGNOSIS node).
    Applied to references before variant derivation so no accidental floating
    blocks reach the expert panel."""
    from collections import defaultdict

    nodes = graph.get("nodes", [])
    node_ids = [str(n.get("id")) for n in nodes]
    id_set = set(node_ids)
    edges = [
        e for e in graph.get("edges", [])
        if str(e.get("source")) in id_set and str(e.get("target")) in id_set
    ]
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[str(e["source"])].add(str(e["target"]))
        adj[str(e["target"])].add(str(e["source"]))
    seen: set[str] = set()
    comps: list[set[str]] = []
    for n in node_ids:
        if n in seen:
            continue
        stack, comp = [n], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.add(x)
            stack.extend(adj[x] - seen)
        comps.append(comp)
    if len(comps) <= 1:
        return {**graph, "edges": edges}
    diag_ids = {
        str(n.get("id"))
        for n in nodes
        if str((n.get("data") or {}).get("category") or "").upper() == "DIAGNOSIS"
    }
    keep = max(comps, key=lambda c: (1 if c & diag_ids else 0, len(c)))
    return {
        **graph,
        "nodes": [n for n in nodes if str(n.get("id")) in keep],
        "edges": [e for e in edges if str(e["source"]) in keep and str(e["target"]) in keep],
    }


def _case(
    case_id: str,
    title: str,
    protocol_focus: str,
    description: str,
    expected_sections: list[str],
    checklist: list[str],
    red_flags: list[str],
    target_competency: str,
    reference_graph: dict[str, Any],
    diagnostic_node_id: str,
    wrong_category_node_id: str,
    critical_edge_id: str,
    chain_edge_id: str,
    diagnosis_node_id: str,
    unsafe_label: str,
    contraindication: tuple[str, str] | None = None,
) -> dict[str, Any]:
    # Clean the reference to a single connected clinical chain before deriving
    # variants, so no orphan / disconnected blocks reach the expert panel and the
    # error variants are injected onto a clean base.
    reference_graph = _prune_to_main_component(reference_graph)
    task = {
        "title": title,
        "description": description,
        "protocol_focus": protocol_focus,
        "expected_sections": expected_sections,
        "checklist": checklist,
        "red_flags": red_flags,
        "difficulty": "advanced",
        "target_competency": target_competency,
        **_task_quality(
            {
                "description": description,
                "protocol_focus": protocol_focus,
                "expected_sections": expected_sections,
                "checklist": checklist,
                "red_flags": red_flags,
                "target_competency": target_competency,
            }
        ),
    }
    variants = [
        {
            "variant_id": "correct_reference_solution",
            "expected_pattern": "all_metrics_high",
            "description": "Студент построил граф, совпадающий с эталонной клинической цепочкой.",
            "student_graph": "__same_as_reference__",
        },
        {
            "variant_id": "missing_key_diagnostic_step",
            "expected_pattern": "recall_and_node_coverage_drop",
            "description": "Пропущен ключевой диагностический шаг протокола.",
            "student_graph": _without_node(reference_graph, diagnostic_node_id),
        },
        {
            "variant_id": "wrong_node_category",
            "expected_pattern": "category_accuracy_drop",
            "description": "Клинический элемент оставлен, но отнесен к неверной категории.",
            "student_graph": _change_category(reference_graph, wrong_category_node_id, "MEDICATION"),
        },
        {
            "variant_id": "missing_critical_action",
            "expected_pattern": "missing_critical_action_penalty",
            "description": "Критическое лечебное или мониторинговое действие не связано с диагнозом.",
            "student_graph": _without_edge(reference_graph, critical_edge_id),
        },
        {
            "variant_id": "broken_reasoning_chain",
            "expected_pattern": "directed_path_drop",
            "description": "Разорвана причинная цепочка между диагностическим фактом и диагнозом.",
            "student_graph": _without_edge(reference_graph, chain_edge_id),
        },
        {
            "variant_id": "unsafe_extra_action",
            "expected_pattern": "unsafe_extra_action_cap",
            "description": "Добавлено потенциально небезопасное действие, отсутствующее в эталоне.",
            "student_graph": _add_indicated_medication(
                reference_graph,
                diagnosis_node_id,
                f"{case_id}_unsafe_med",
                unsafe_label,
            ),
        },
    ]
    if contraindication:
        medication_id, edge_id = contraindication
        variants.append(
            {
                "variant_id": "contraindication_reversed_to_indication",
                "expected_pattern": "critical_relation_penalty",
                "description": "Противопоказанное действие ошибочно превращено в показанное.",
                "student_graph": _replace_contraindication_with_indication(
                    reference_graph,
                    diagnosis_node_id,
                    medication_id,
                    edge_id,
                ),
            }
        )
    return {
        "case_id": case_id,
        "title": title,
        "protocol_area": "cardiology",
        "task": task,
        "reference_graph": reference_graph,
        "variants": variants,
        "metadata": {
            "source": "synthetic_protocol_derived_cardiology_control_seed",
            "requires_expert_review": True,
            "error_taxonomy": sorted({variant["expected_pattern"] for variant in variants}),
            "algorithm_version": CARDIOLOGY_ALGORITHM_VERSION,
        },
    }


def _merge_protocol_sources(
    protocol_sources: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    merged = {case_id: deepcopy(source) for case_id, source in DEFAULT_PROTOCOL_SOURCE_IDS.items()}
    for case_id, source in (protocol_sources or {}).items():
        if not isinstance(source, Mapping):
            continue
        merged.setdefault(case_id, {}).update(dict(source))
    return merged


def _attach_protocol_sources(
    cases: list[dict[str, Any]],
    protocol_sources: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    sources = _merge_protocol_sources(protocol_sources)
    for case in cases:
        case_id = str(case.get("case_id") or "")
        source = sources.get(case_id)
        if not source:
            continue
        source_copy = deepcopy(source)
        case["source_protocol"] = source_copy
        case.setdefault("task", {})["source_protocol"] = deepcopy(source_copy)
        case.setdefault("metadata", {})["source_protocol"] = deepcopy(source_copy)


def _external_protocol_id(source: Mapping[str, Any]) -> str | None:
    explicit = source.get("protocol_external_id") or source.get("external_protocol_id")
    if explicit not in (None, ""):
        return str(explicit)
    match = re.search(r"/(\d+)(?:\?.*)?$", str(source.get("protocol_url") or ""))
    return match.group(1) if match else None


def _source_protocol_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        source = case.get("source_protocol") or {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "case_title": case.get("title"),
                "database_protocol_id": source.get("protocol_id"),
                "source_protocol_id": _external_protocol_id(source),
                "protocol_title": source.get("protocol_title"),
                "protocol_year": source.get("protocol_year"),
                "protocol_sections": source.get("protocol_sections") or [],
                "protocol_chunk_count": source.get("protocol_chunk_count"),
                "protocol_url": source.get("protocol_url"),
                "source_fit": source.get("source_fit"),
                "source_note": source.get("source_note"),
            }
        )
    return rows


def _protocol_control_case(
    *,
    prefix: str,
    case_id: str,
    title: str,
    protocol_focus: str,
    description: str,
    expected_sections: list[str],
    checklist: list[str],
    red_flags: list[str],
    target_competency: str,
    patient_label: str,
    symptom_label: str,
    diagnostic_label: str,
    evidence_label: str,
    evidence_category: str,
    diagnosis_label: str,
    medication_label: str,
    action_label: str,
    action_category: str,
    monitoring_label: str,
    unsafe_label: str,
    suspicion_label: str | None = None,
    etiology_label: str | None = None,
) -> dict[str, Any]:
    if suspicion_label:
        nodes = [
            _node(f"{prefix}_p", patient_label, "PATIENT_PROFILE", 0, 0),
            _node(f"{prefix}_s", symptom_label, "SYMPTOM", 220, 0),
            _node(f"{prefix}_test", diagnostic_label, "INSTRUMENTAL_TEST", 440, -140),
            _node(f"{prefix}_suspicion", suspicion_label, "DIAGNOSIS", 600, -90),
            _node(f"{prefix}_evidence", evidence_label, evidence_category, 600, 95),
            _node(f"{prefix}_dx", diagnosis_label, "DIAGNOSIS", 780, 0),
            _node(f"{prefix}_med", medication_label, "MEDICATION", 1000, -120),
            _node(f"{prefix}_action", action_label, action_category, 1000, 0),
            _node(f"{prefix}_monitor", monitoring_label, "MONITORING", 1000, 120),
        ]
        edges = [
            _edge(f"{prefix}_e1", f"{prefix}_p", f"{prefix}_s", "DETERMINES"),
            _edge(f"{prefix}_e2", f"{prefix}_s", f"{prefix}_test", "REQUIRES_CONFIRMATION"),
            _edge(f"{prefix}_e3", f"{prefix}_test", f"{prefix}_suspicion", "DETERMINES"),
            _edge(f"{prefix}_e4", f"{prefix}_suspicion", f"{prefix}_evidence", "REQUIRES_CONFIRMATION"),
            _edge(f"{prefix}_e5", f"{prefix}_evidence", f"{prefix}_dx", "DETERMINES"),
            _edge(f"{prefix}_e6", f"{prefix}_dx", f"{prefix}_med", "INDICATED_FOR"),
            _edge(f"{prefix}_e7", f"{prefix}_dx", f"{prefix}_action", "INDICATED_FOR"),
            _edge(f"{prefix}_e8", f"{prefix}_dx", f"{prefix}_monitor", "INDICATED_FOR"),
        ]
        if etiology_label:
            nodes.append(_node(f"{prefix}_etiology", etiology_label, "EXAM", 780, 150))
            edges = [
                edge for edge in edges if edge["id"] != f"{prefix}_e6"
            ] + [
                _edge(f"{prefix}_e9", f"{prefix}_dx", f"{prefix}_etiology", "REQUIRES_CONFIRMATION"),
                _edge(f"{prefix}_e10", f"{prefix}_etiology", f"{prefix}_med", "DETERMINES"),
            ]
    else:
        nodes = [
            _node(f"{prefix}_p", patient_label, "PATIENT_PROFILE", 0, 0),
            _node(f"{prefix}_s", symptom_label, "SYMPTOM", 220, 0),
            _node(f"{prefix}_test", diagnostic_label, "INSTRUMENTAL_TEST", 440, -100),
            _node(f"{prefix}_evidence", evidence_label, evidence_category, 440, 95),
            _node(f"{prefix}_dx", diagnosis_label, "DIAGNOSIS", 660, 0),
            _node(f"{prefix}_med", medication_label, "MEDICATION", 880, -120),
            _node(f"{prefix}_action", action_label, action_category, 880, 0),
            _node(f"{prefix}_monitor", monitoring_label, "MONITORING", 880, 120),
        ]
        edges = [
            _edge(f"{prefix}_e1", f"{prefix}_p", f"{prefix}_s", "DETERMINES"),
            _edge(f"{prefix}_e2", f"{prefix}_s", f"{prefix}_test", "REQUIRES_CONFIRMATION"),
            _edge(f"{prefix}_e3", f"{prefix}_s", f"{prefix}_evidence", "REQUIRES_CONFIRMATION"),
            _edge(f"{prefix}_e4", f"{prefix}_test", f"{prefix}_dx", "DETERMINES"),
            _edge(f"{prefix}_e5", f"{prefix}_evidence", f"{prefix}_dx", "REQUIRES_CONFIRMATION"),
            _edge(f"{prefix}_e6", f"{prefix}_dx", f"{prefix}_med", "INDICATED_FOR"),
            _edge(f"{prefix}_e7", f"{prefix}_dx", f"{prefix}_action", "INDICATED_FOR"),
            _edge(f"{prefix}_e8", f"{prefix}_dx", f"{prefix}_monitor", "INDICATED_FOR"),
        ]
    graph = _graph(nodes, edges)
    return _case(
        case_id,
        title,
        protocol_focus,
        description,
        expected_sections,
        checklist,
        red_flags,
        target_competency,
        graph,
        diagnostic_node_id=f"{prefix}_test",
        wrong_category_node_id=f"{prefix}_monitor",
        critical_edge_id=f"{prefix}_e7",
        chain_edge_id=f"{prefix}_e4",
        diagnosis_node_id=f"{prefix}_dx",
        unsafe_label=unsafe_label,
    )


def _additional_protocol_control_cases() -> list[dict[str, Any]]:
    return [
        _protocol_control_case(
            prefix="c9",
            case_id="cardio_stable_angina_09",
            title="Стабильная стенокардия: подтверждение ишемии и антиангинальная стратегия",
            protocol_focus="Стабильная ИБС / стенокардия напряжения",
            description=(
                "Пациент 62 лет с воспроизводимым давящим загрудинным дискомфортом при нагрузке, "
                "проходящим в покое. Постройте граф от характера симптомов и подтверждения ишемии к "
                "диагнозу стабильной стенокардии, антиангинальной терапии, коррекции коронарного риска и наблюдению."
            ),
            expected_sections=["оценка симптомов", "тестирование ишемии", "стратификация риска", "антиангинальная терапия", "наблюдение"],
            checklist=["отличить стабильные симптомы от ОКС", "подтвердить ишемию", "связать диагноз с антиангинальной терапией", "включить контроль факторов риска", "включить динамическое наблюдение"],
            red_flags=["трактовка стабильной стенокардии как низкого риска без исключения нестабильных симптомов"],
            target_competency="Распознавать стабильную ИБС и строить безопасный диагностико-лечебный граф.",
            patient_label="Пациент 62 лет с загрудинным дискомфортом при нагрузке",
            symptom_label="Предсказуемая боль в груди при нагрузке, проходящая в покое",
            diagnostic_label="Нагрузочный тест или коронарная визуализация подтверждают ишемию",
            evidence_label="Профиль риска: гипертония, дислипидемия и курение",
            evidence_category="EXAM",
            diagnosis_label="Стабильная стенокардия напряжения",
            medication_label="Антиангинальная терапия и вторичная профилактика",
            action_label="Коронарная ангиография при сохранении признаков высокого риска",
            action_category="SURGERY",
            monitoring_label="Наблюдение симптомов, АД, липидов и переносимости терапии",
            unsafe_label="Немедленный тромболизис несмотря на стабильные симптомы",
        ),
        _protocol_control_case(
            prefix="c10",
            case_id="cardio_chronic_hf_10",
            title="Хроническая сердечная недостаточность: фенотип, терапия по рекомендациям и мониторинг",
            protocol_focus="Хроническая сердечная недостаточность",
            description=(
                "Пациент с одышкой, отёками и сниженной переносимостью нагрузки. Требуется граф, "
                "связывающий клинические признаки застоя, эхокардиографический фенотип и уровень "
                "натрийуретических пептидов с ведением хронической сердечной недостаточности, болезнь-модифицирующей терапией и мониторингом."
            ),
            expected_sections=["оценка застоя", "эхокардиография", "натрийуретические пептиды", "болезнь-модифицирующая терапия", "мониторинг"],
            checklist=["выявить застой", "подтвердить дисфункцию сердца", "связать диагноз с терапией по рекомендациям", "включить мониторинг", "не ограничиваться только симптоматическим лечением"],
            red_flags=["отсутствие болезнь-модифицирующей терапии при подтверждённой сердечной недостаточности"],
            target_competency="Строить граф хронической СН, сохраняя непрерывность от диагноза к терапии.",
            patient_label="Пациент с одышкой, отёками и сниженной переносимостью нагрузки",
            symptom_label="Прогрессирующая одышка при нагрузке и периферические отёки",
            diagnostic_label="Эхокардиография показывает сниженную или нарушенную функцию желудочков",
            evidence_label="Повышенные натрийуретические пептиды подтверждают сердечную недостаточность",
            evidence_category="LAB_TEST",
            diagnosis_label="Хроническая сердечная недостаточность",
            medication_label="Болезнь-модифицирующая терапия по клиническим рекомендациям",
            action_label="Коррекция объёма и направление на специализированную помощь при показаниях",
            action_category="SURGERY",
            monitoring_label="Функция почек, калий, артериальное давление, симптомы и вес",
            unsafe_label="Отмена болезнь-модифицирующей терапии после улучшения симптомов",
        ),
        _protocol_control_case(
            prefix="c11",
            case_id="cardio_pulmonary_htn_11",
            title="Лёгочная гипертензия: подозрение по ЭхоКГ и маршрут подтверждения",
            protocol_focus="Лёгочная гипертензия",
            description=(
                "У пациента необъяснимая одышка, признаки перегрузки правых отделов сердца и "
                "эхокардиографическая вероятность лёгочной гипертензии. Граф должен разделять подозрение и "
                "подтверждённый диагноз и включать подтверждающую оценку гемодинамики и маршрут специализированного лечения."
            ),
            expected_sections=["клиническое подозрение", "эхокардиография", "оценка правых отделов сердца", "поиск этиологии", "специализированное лечение"],
            checklist=["выявить перегрузку правых отделов", "не приравнивать подозрение по ЭхоКГ к окончательному диагнозу", "включить подтверждающую оценку", "связать этиологию с терапией", "включить наблюдение"],
            red_flags=["начало таргетной терапии без подтверждения и оценки этиологии"],
            target_competency="Отразить поэтапную диагностику лёгочной гипертензии и избежать преждевременной терапии.",
            patient_label="Пациент с необъяснимой одышкой и эпизодами синкопе",
            symptom_label="Одышка с признаками перегрузки правых отделов сердца",
            diagnostic_label="ЭхоКГ указывает на высокую вероятность лёгочной гипертензии",
            evidence_label="Катетеризация правых отделов подтверждает гемодинамику",
            evidence_category="INSTRUMENTAL_TEST",
            diagnosis_label="Подтверждённая лёгочная гипертензия",
            medication_label="Терапия после подтверждения диагноза и определения группы ЛГ",
            action_label="Направление в специализированный центр по лёгочной гипертензии",
            action_category="SURGERY",
            monitoring_label="Функциональный класс, оксигенация, ЭхоКГ и переносимость лечения",
            unsafe_label="Назначение таргетного лёгочного вазодилататора без подтверждения",
            suspicion_label="Подозрение на лёгочную гипертензию",
            etiology_label="Определение этиологии и клинической группы лёгочной гипертензии",
        ),
        _protocol_control_case(
            prefix="c12",
            case_id="cardio_mitral_stenosis_pregnancy_12",
            title="Беременность при митральном стенозе: материнский риск и согласованное ведение",
            protocol_focus="Беременность при митральном стенозе",
            description=(
                "Беременная пациентка с одышкой и установленным ревматическим митральным стенозом. "
                "Требуется граф, связывающий материнские симптомы, эхокардиографическую тяжесть, "
                "стратификацию материнско-плодового риска, безопасную медикаментозную тактику и мультидисциплинарный мониторинг."
            ),
            expected_sections=["материнские симптомы", "эхокардиография", "стратификация риска", "безопасная терапия при беременности", "мультидисциплинарный мониторинг"],
            checklist=["оценить тяжесть по ЭхоКГ", "включить материнско-плодовый риск", "избегать небезопасных препаратов", "связать тяжёлый стеноз со специализированным вмешательством", "включить акушерско-кардиологический мониторинг"],
            red_flags=["небезопасная антикоагуляция или отсроченное вмешательство при декомпенсации"],
            target_competency="Интегрировать кардиологические и акушерские требования безопасности в графе-решении.",
            patient_label="Беременная пациентка с установленным ревматическим митральным стенозом",
            symptom_label="Одышка и сниженная переносимость нагрузки во время беременности",
            diagnostic_label="Эхокардиография подтверждает значимый митральный стеноз",
            evidence_label="Стратификация материнско-плодового риска высокая",
            evidence_category="EXAM",
            diagnosis_label="Беременность, осложнённая значимым митральным стенозом",
            medication_label="Совместимый с беременностью контроль ритма и антикоагуляция при показаниях",
            action_label="Планирование мультидисциплинарного кардио-акушерского вмешательства",
            action_category="SURGERY",
            monitoring_label="Материнская гемодинамика, состояние плода и признаки декомпенсации",
            unsafe_label="Применение противопоказанного препарата без оценки безопасности при беременности",
        ),
    ]


def _english_prose_words(text: str) -> int:
    """Count lowercase Latin words of >=4 letters — a signal of English prose.
    Uppercase/mixed medical abbreviations and scores (ST, aVF, NSTEMI,
    CHA2DS2-VASc, Stanford) and Cyrillic text do not match, so they pass."""
    return len(re.findall(r"[a-z]{4,}", text or ""))


def _assert_cases_russian(cases: list[dict[str, Any]]) -> None:
    """Fail the build if any case title/description or graph node label reads as
    English prose (>=2 lowercase Latin words). Guarantees the cardiology set can
    never be regenerated in English while still allowing medical abbreviations."""
    problems: list[str] = []
    for case in cases:
        checks: list[tuple[str, str]] = [
            ("title", str(case.get("title") or "")),
            ("description", str((case.get("task") or {}).get("description") or "")),
        ]
        for node in (case.get("reference_graph") or {}).get("nodes", []):
            checks.append(("node", str((node.get("data") or {}).get("label") or "")))
        for field, text in checks:
            if _english_prose_words(text) >= 2:
                problems.append(f"{case.get('case_id')} [{field}]: {text[:70]}")
    if problems:
        raise ValueError(
            "Cardiology seed contains non-Russian (English) content — all graphs must be in Russian:\n  "
            + "\n  ".join(problems)
        )


def build_cardiology_seed(
    case_count: int | None = None,
    protocol_sources: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    stemi = _graph(
        [
            _node("c1_p", "Мужчина 58 лет, боль за грудиной 45 минут", "PATIENT_PROFILE", 0, 0),
            _node("c1_s", "Давящая боль с иррадиацией и холодный пот", "SYMPTOM", 220, 0),
            _node("c1_ecg", "ЭКГ: элевация ST в II, III, aVF", "INSTRUMENTAL_TEST", 440, -90),
            _node("c1_trop", "Тропонин берется без задержки реперфузии", "LAB_TEST", 440, 90),
            _node("c1_rv", "Оценка правожелудочкового инфаркта при нижнем STEMI", "INSTRUMENTAL_TEST", 660, 130),
            _node("c1_dx", "Острый инфаркт миокарда с подъемом ST", "DIAGNOSIS", 660, 0),
            _node("c1_antithrombotic", "Аспирин, ингибитор P2Y12 и антикоагулянт", "MEDICATION", 880, -120),
            _node("c1_pci", "Первичное ЧКВ без ожидания тропонина", "SURGERY", 880, -10),
            _node("c1_fibrinolysis", "Фибринолиз при задержке ЧКВ и отсутствии противопоказаний", "MEDICATION", 880, 120),
            _node("c1_monitor", "Непрерывный мониторинг ЭКГ и гемодинамики", "MONITORING", 880, 250),
        ],
        [
            _edge("c1_e1", "c1_p", "c1_s", "DETERMINES"),
            _edge("c1_e2", "c1_s", "c1_ecg", "REQUIRES_CONFIRMATION"),
            _edge("c1_e3", "c1_s", "c1_trop", "REQUIRES_CONFIRMATION"),
            _edge("c1_e4", "c1_ecg", "c1_dx", "DETERMINES"),
            _edge("c1_e5", "c1_ecg", "c1_rv", "REQUIRES_CONFIRMATION"),
            _edge("c1_e6", "c1_dx", "c1_antithrombotic", "INDICATED_FOR"),
            _edge("c1_e7", "c1_dx", "c1_pci", "INDICATED_FOR"),
            _edge("c1_e8", "c1_dx", "c1_monitor", "INDICATED_FOR"),
            _edge("c1_e9", "c1_dx", "c1_fibrinolysis", "INDICATED_FOR"),
            _edge("c1_e10", "c1_dx", "c1_trop", "REQUIRES_CONFIRMATION"),
            _edge("c1_e11", "c1_trop", "c1_monitor", "DETERMINES"),
            _edge("c1_e12", "c1_dx", "c1_rv", "REQUIRES_CONFIRMATION"),
            _edge("c1_e13", "c1_rv", "c1_monitor", "DETERMINES"),
        ],
    )
    cases.append(
        _case(
            "cardio_stemi_01",
            "ОКС с подъемом ST: диагностика и реперфузия",
            "Острый коронарный синдром / инфаркт миокарда с подъемом ST",
            "Пациент 58 лет поступает с интенсивной давящей болью за грудиной, холодным потом и длительностью симптомов менее часа. Нужно построить граф клинического решения: от жалоб и ЭКГ до диагноза STEMI, антитромботической терапии, реперфузии и мониторинга.",
            ["экстренная диагностика", "ЭКГ", "кардиомаркеры", "реперфузия", "антитромботическая терапия"],
            ["учесть длительность боли", "назначить ЭКГ", "не задерживать реперфузию ожиданием тропонина", "связать диагноз с первичным ЧКВ", "указать фибринолиз при задержке ЧКВ и мониторинг"],
            ["задержка реперфузии", "ожидание тропонина перед реперфузией при STEMI", "назначение небезопасной альтернативной терапии вместо ЧКВ"],
            "Распознавание STEMI и построение безопасной диагностико-лечебной цепочки.",
            stemi,
            diagnostic_node_id="c1_ecg",
            wrong_category_node_id="c1_monitor",
            critical_edge_id="c1_e7",
            chain_edge_id="c1_e4",
            diagnosis_node_id="c1_dx",
            unsafe_label="Отложить реперфузию и выполнить нагрузочный тест",
        )
    )

    nstemi = _graph(
        [
            _node("c2_p", "Женщина 67 лет, диабет и гипертония", "PATIENT_PROFILE", 0, 0),
            _node("c2_s", "Нестабильная боль в груди в покое", "SYMPTOM", 220, 0),
            _node("c2_ecg", "ЭКГ без стойкой элевации ST", "INSTRUMENTAL_TEST", 440, -120),
            _node("c2_trop", "Рост тропонина в динамике", "LAB_TEST", 440, 0),
            _node("c2_risk", "Высокий риск по GRACE", "EXAM", 440, 120),
            _node("c2_dx", "NSTEMI высокого риска", "DIAGNOSIS", 660, 0),
            _node("c2_dapt", "Двойная антиагрегантная терапия и антикоагулянт", "MEDICATION", 880, -100),
            _node("c2_angio", "Ранняя инвазивная коронарография", "SURGERY", 880, 20),
            _node("c2_monitor", "Мониторинг ишемии и гемодинамики", "MONITORING", 880, 140),
        ],
        [
            _edge("c2_e1", "c2_p", "c2_s", "DETERMINES"),
            _edge("c2_e2", "c2_s", "c2_ecg", "REQUIRES_CONFIRMATION"),
            _edge("c2_e3", "c2_s", "c2_trop", "REQUIRES_CONFIRMATION"),
            _edge("c2_e4", "c2_trop", "c2_dx", "DETERMINES"),
            _edge("c2_e5", "c2_ecg", "c2_dx", "REQUIRES_CONFIRMATION"),
            _edge("c2_e6", "c2_risk", "c2_dx", "DETERMINES"),
            _edge("c2_e7", "c2_dx", "c2_dapt", "INDICATED_FOR"),
            _edge("c2_e8", "c2_dx", "c2_angio", "INDICATED_FOR"),
            _edge("c2_e9", "c2_dx", "c2_monitor", "INDICATED_FOR"),
        ],
    )
    cases.append(
        _case(
            "cardio_nstemi_02",
            "NSTEMI высокого риска: стратификация и ранняя инвазия",
            "Острый коронарный синдром без подъема ST",
            "Пациентка с диабетом и болью в груди в покое требует отличить нестабильную стенокардию от NSTEMI. Граф должен показать динамику тропонина, оценку риска, отсутствие стойкой элевации ST, диагноз NSTEMI и раннюю инвазивную тактику.",
            ["дифференциальная диагностика ОКС", "тропонин", "оценка риска", "коронарография", "антитромботическая терапия"],
            ["не путать NSTEMI со STEMI", "использовать динамику тропонина", "учесть риск", "связать диагноз с антикоагулянтом", "показать инвазивную стратегию"],
            ["пропуск динамики тропонина", "замена ранней инвазии только наблюдением"],
            "Построение графа NSTEMI с учетом риска и последовательности решений.",
            nstemi,
            diagnostic_node_id="c2_trop",
            wrong_category_node_id="c2_risk",
            critical_edge_id="c2_e8",
            chain_edge_id="c2_e4",
            diagnosis_node_id="c2_dx",
            unsafe_label="Тромболизис при NSTEMI без элевации ST",
        )
    )

    heart_failure = _graph(
        [
            _node("c3_p", "Пациент 74 лет с хронической сердечной недостаточностью", "PATIENT_PROFILE", 0, 0),
            _node("c3_s", "Одышка в покое, ортопноэ и отеки", "SYMPTOM", 220, 0),
            _node("c3_exam", "Влажные хрипы и набухание яремных вен", "EXAM", 440, -120),
            _node("c3_bnp", "NT-proBNP значительно повышен", "LAB_TEST", 440, 0),
            _node("c3_echo", "ЭхоКГ: сниженная фракция выброса", "INSTRUMENTAL_TEST", 440, 120),
            _node("c3_dx", "Острая декомпенсация сердечной недостаточности", "DIAGNOSIS", 660, 0),
            _node("c3_diuretic", "Внутривенный петлевой диуретик", "MEDICATION", 880, -100),
            _node("c3_oxygen", "Кислородная поддержка при гипоксемии", "MONITORING", 880, 20),
            _node("c3_monitor", "Контроль диуреза, креатинина и калия", "MONITORING", 880, 140),
        ],
        [
            _edge("c3_e1", "c3_p", "c3_s", "DETERMINES"),
            _edge("c3_e2", "c3_s", "c3_exam", "REQUIRES_CONFIRMATION"),
            _edge("c3_e3", "c3_s", "c3_bnp", "REQUIRES_CONFIRMATION"),
            _edge("c3_e4", "c3_echo", "c3_dx", "REQUIRES_CONFIRMATION"),
            _edge("c3_e5", "c3_bnp", "c3_dx", "DETERMINES"),
            _edge("c3_e6", "c3_exam", "c3_dx", "DETERMINES"),
            _edge("c3_e7", "c3_dx", "c3_diuretic", "INDICATED_FOR"),
            _edge("c3_e8", "c3_dx", "c3_oxygen", "INDICATED_FOR"),
            _edge("c3_e9", "c3_dx", "c3_monitor", "INDICATED_FOR"),
        ],
    )
    cases.append(
        _case(
            "cardio_hf_03",
            "Острая декомпенсация сердечной недостаточности",
            "Сердечная недостаточность / отек легких",
            "Пациент с известной сердечной недостаточностью поступает с одышкой, ортопноэ, влажными хрипами и отеками. Требуется построить граф от симптомов и объективных признаков к диагнозу декомпенсации, диуретической терапии и мониторингу функции почек.",
            ["клинические признаки застоя", "натрийуретические пептиды", "эхокардиография", "диуретики", "мониторинг"],
            ["выделить симптомы застоя", "подтвердить NT-proBNP", "учесть ЭхоКГ", "связать диагноз с диуретиком", "указать контроль креатинина и калия"],
            ["неучтенный контроль электролитов", "назначение инфузионной нагрузки без показаний"],
            "Связывание признаков застоя с безопасным лечением и мониторингом.",
            heart_failure,
            diagnostic_node_id="c3_bnp",
            wrong_category_node_id="c3_monitor",
            critical_edge_id="c3_e7",
            chain_edge_id="c3_e5",
            diagnosis_node_id="c3_dx",
            unsafe_label="Быстрая инфузионная нагрузка кристаллоидами",
        )
    )

    af = _graph(
        [
            _node("c4_p", "Пациент 76 лет, гипертония и перенесенный инсульт", "PATIENT_PROFILE", 0, 0),
            _node("c4_s", "Нерегулярное сердцебиение и слабость", "SYMPTOM", 220, 0),
            _node("c4_hemo", "Оценка гемодинамической нестабильности", "EXAM", 440, -220),
            _node("c4_pulse", "Нерегулярный пульс 130 в минуту", "EXAM", 440, -90),
            _node("c4_ecg", "ЭКГ: фибрилляция предсердий", "INSTRUMENTAL_TEST", 440, 40),
            _node("c4_valvular", "Исключить механический клапан и значимый митральный стеноз", "INSTRUMENTAL_TEST", 440, 170),
            _node("c4_score", "CHA2DS2-VASc 5 баллов", "EXAM", 660, -150),
            _node("c4_bleed", "HAS-BLED и оценка риска кровотечения", "EXAM", 660, 150),
            _node("c4_dx", "Неклапанная фибрилляция предсердий высокого риска инсульта", "DIAGNOSIS", 660, 0),
            _node("c4_doac", "Пероральный антикоагулянт с учетом функции почек", "MEDICATION", 880, -100),
            _node("c4_rate", "Бета-блокатор или недигидропиридиновый БКК для контроля ЧСС", "MEDICATION", 880, 20),
            _node("c4_monitor", "Контроль креатинина, кровотечений и ЧСС", "MONITORING", 880, 140),
        ],
        [
            _edge("c4_e1", "c4_p", "c4_s", "DETERMINES"),
            _edge("c4_e2", "c4_s", "c4_pulse", "REQUIRES_CONFIRMATION"),
            _edge("c4_e3", "c4_pulse", "c4_ecg", "REQUIRES_CONFIRMATION"),
            _edge("c4_e4", "c4_ecg", "c4_dx", "DETERMINES"),
            _edge("c4_e5", "c4_score", "c4_dx", "DETERMINES"),
            _edge("c4_e6", "c4_dx", "c4_doac", "INDICATED_FOR"),
            _edge("c4_e7", "c4_dx", "c4_rate", "INDICATED_FOR"),
            _edge("c4_e8", "c4_dx", "c4_monitor", "INDICATED_FOR"),
            _edge("c4_e9", "c4_s", "c4_hemo", "REQUIRES_CONFIRMATION"),
            _edge("c4_e10", "c4_valvular", "c4_dx", "EXCLUDES"),
            _edge("c4_e11", "c4_bleed", "c4_doac", "REQUIRES_CONFIRMATION"),
            _edge("c4_e12", "c4_dx", "c4_bleed", "REQUIRES_CONFIRMATION"),
            _edge("c4_e13", "c4_dx", "c4_hemo", "REQUIRES_CONFIRMATION"),
            _edge("c4_e14", "c4_hemo", "c4_rate", "DETERMINES"),
        ],
    )
    cases.append(
        _case(
            "cardio_af_04",
            "Фибрилляция предсердий: риск инсульта и антикоагуляция",
            "Фибрилляция предсердий / профилактика инсульта",
            "Пациент пожилого возраста с гипертонией и перенесенным инсультом имеет нерегулярный пульс и ЭКГ-признаки фибрилляции предсердий. Нужно построить граф, где диагноз связан с оценкой CHA2DS2-VASc, исключением клапанной ФП, оценкой кровотечения, антикоагуляцией, контролем ЧСС и мониторингом осложнений.",
            ["ЭКГ-диагностика", "оценка тромбоэмболического риска", "исключение клапанной ФП", "антикоагуляция", "мониторинг безопасности"],
            ["подтвердить ФП на ЭКГ", "посчитать риск инсульта", "исключить механический клапан или значимый митральный стеноз", "оценить риск кровотечения", "показать антикоагулянт и мониторинг функции почек"],
            ["пропуск антикоагуляции при высоком риске", "игнорирование риска кровотечения", "назначение ПОАК при клапанной ФП без проверки противопоказаний"],
            "Построение графа профилактики инсульта при ФП.",
            af,
            diagnostic_node_id="c4_ecg",
            wrong_category_node_id="c4_score",
            critical_edge_id="c4_e6",
            chain_edge_id="c4_e4",
            diagnosis_node_id="c4_dx",
            unsafe_label="Аспирин вместо антикоагулянта при высоком CHA2DS2-VASc",
        )
    )

    hypertension = _graph(
        [
            _node("c5_p", "Пациент 62 лет, АД 230/125 мм рт. ст.", "PATIENT_PROFILE", 0, 0),
            _node("c5_s", "Головная боль, боль в груди и спутанность", "SYMPTOM", 220, 0),
            _node("c5_exam", "Очаговый неврологический дефицит", "EXAM", 440, -120),
            _node("c5_labs", "Креатинин и тропонин для оценки поражения органов", "LAB_TEST", 440, 0),
            _node("c5_ecg", "ЭКГ для исключения ишемии", "INSTRUMENTAL_TEST", 440, 120),
            _node("c5_neuroimaging", "КТ/нейровизуализация при очаговом неврологическом дефиците", "INSTRUMENTAL_TEST", 660, -170),
            _node("c5_dx", "Гипертоническая экстренная ситуация с поражением органов", "DIAGNOSIS", 660, 0),
            _node("c5_iv", "Внутривенное титруемое снижение АД", "MEDICATION", 880, -100),
            _node("c5_tempo", "Снижение АД на 20-25% в первый час с дальнейшей титрацией", "MONITORING", 880, 20),
            _node("c5_icu", "Мониторинг АД в условиях интенсивной терапии", "MONITORING", 880, 140),
            _node("c5_urgent", "Гипертоническая неотложность без поражения органов", "DIAGNOSIS", 660, 150),
        ],
        [
            _edge("c5_e1", "c5_p", "c5_s", "DETERMINES"),
            _edge("c5_e2", "c5_s", "c5_exam", "REQUIRES_CONFIRMATION"),
            _edge("c5_e3", "c5_s", "c5_labs", "REQUIRES_CONFIRMATION"),
            _edge("c5_e4", "c5_s", "c5_ecg", "REQUIRES_CONFIRMATION"),
            _edge("c5_e5", "c5_exam", "c5_dx", "DETERMINES"),
            _edge("c5_e6", "c5_labs", "c5_dx", "REQUIRES_CONFIRMATION"),
            _edge("c5_e13", "c5_ecg", "c5_dx", "REQUIRES_CONFIRMATION"),
            _edge("c5_e7", "c5_dx", "c5_urgent", "EXCLUDES"),
            _edge("c5_e8", "c5_dx", "c5_iv", "INDICATED_FOR"),
            _edge("c5_e9", "c5_dx", "c5_icu", "INDICATED_FOR"),
            _edge("c5_e10", "c5_exam", "c5_neuroimaging", "REQUIRES_CONFIRMATION"),
            _edge("c5_e11", "c5_neuroimaging", "c5_dx", "REQUIRES_CONFIRMATION"),
            _edge("c5_e12", "c5_dx", "c5_tempo", "INDICATED_FOR"),
        ],
    )
    cases.append(
        _case(
            "cardio_htn_05",
            "Гипертоническая экстренная ситуация",
            "Артериальная гипертензия / поражение органов-мишеней",
            "У пациента очень высокое артериальное давление сопровождается неврологическими симптомами и болью в груди. Граф должен отделить экстренную ситуацию от неотложности без поражения органов, показать оценку органов-мишеней, нейровизуализацию при очаговом дефиците, внутривенное титруемое лечение, темп снижения АД и мониторинг.",
            ["дифференциация emergency/urgency", "поражение органов", "лабораторная оценка", "нейровизуализация", "темп снижения АД"],
            ["учесть признаки поражения органов", "не снижать давление резко до нормы", "включить нейровизуализацию при очаговом дефиците", "связать диагноз с внутривенной терапией", "показать темп снижения АД и мониторинг"],
            ["резкое бесконтрольное снижение АД", "игнорирование неврологического дефицита"],
            "Различение гипертонической экстренной ситуации и безопасная тактика снижения АД.",
            hypertension,
            diagnostic_node_id="c5_exam",
            wrong_category_node_id="c5_icu",
            critical_edge_id="c5_e8",
            chain_edge_id="c5_e5",
            diagnosis_node_id="c5_dx",
            unsafe_label="Немедленно снизить АД до нормы сублингвальным препаратом",
        )
    )

    dissection = _graph(
        [
            _node("c6_p", "Мужчина 61 год с длительной гипертонией", "PATIENT_PROFILE", 0, 0),
            _node("c6_s", "Внезапная разрывающая боль в груди и спине", "SYMPTOM", 220, 0),
            _node("c6_exam", "Асимметрия пульса и разница АД на руках", "EXAM", 440, -120),
            _node("c6_ct", "КТ-ангиография: расслоение восходящей аорты", "INSTRUMENTAL_TEST", 440, 0),
            _node("c6_trop", "Тропонин не объясняет клинику ОКС", "LAB_TEST", 440, 120),
            _node("c6_dx", "Острое расслоение аорты Stanford A", "DIAGNOSIS", 660, 0),
            _node("c6_beta", "Внутривенный бета-блокатор", "MEDICATION", 880, -190),
            _node("c6_analgesia", "Обезболивание до контроля симпатической активации", "MEDICATION", 880, -70),
            _node("c6_surgery", "Экстренная консультация кардиохирурга и операция", "SURGERY", 880, 50),
            _node("c6_thrombolysis", "Тромболизис", "MEDICATION", 880, 170),
            _node("c6_targets", "Целевые ЧСС и систолическое АД до операции", "MONITORING", 880, 290),
            _node("c6_monitor", "Инвазивный мониторинг АД", "MONITORING", 880, 410),
        ],
        [
            _edge("c6_e1", "c6_p", "c6_s", "DETERMINES"),
            _edge("c6_e2", "c6_s", "c6_exam", "REQUIRES_CONFIRMATION"),
            _edge("c6_e3", "c6_exam", "c6_ct", "REQUIRES_CONFIRMATION"),
            _edge("c6_e4", "c6_ct", "c6_dx", "DETERMINES"),
            _edge("c6_e5", "c6_trop", "c6_dx", "EXCLUDES"),
            _edge("c6_e6", "c6_dx", "c6_beta", "INDICATED_FOR"),
            _edge("c6_e7", "c6_dx", "c6_surgery", "INDICATED_FOR"),
            _edge("c6_e8", "c6_thrombolysis", "c6_dx", "CONTRAINDICATED_DUE_TO"),
            _edge("c6_e9", "c6_dx", "c6_monitor", "INDICATED_FOR"),
            _edge("c6_e10", "c6_dx", "c6_analgesia", "INDICATED_FOR"),
            _edge("c6_e11", "c6_dx", "c6_targets", "INDICATED_FOR"),
        ],
    )
    cases.append(
        _case(
            "cardio_dissection_06",
            "Расслоение аорты Stanford A: запрет тромболизиса",
            "Острый аортальный синдром / расслоение аорты",
            "Пациент с гипертонией и внезапной разрывающей болью требует отличить расслоение аорты от ОКС. Эталонный граф должен включать асимметрию пульса, КТ-ангиографию, диагноз Stanford A, обезболивание, бета-блокатор, цели ЧСС/АД, кардиохирургию и противопоказание к тромболизису.",
            ["дифференциальная диагностика боли в груди", "КТ-ангиография", "контроль ЧСС и АД", "кардиохирургия", "противопоказания"],
            ["распознать red flag расслоения", "подтвердить КТ-ангиографией", "не назначать тромболизис", "связать диагноз с хирургией", "указать обезболивание и целевой контроль ЧСС/АД"],
            ["тромболизис при расслоении", "задержка хирургической консультации"],
            "Выявление противопоказанного действия при остром аортальном синдроме.",
            dissection,
            diagnostic_node_id="c6_ct",
            wrong_category_node_id="c6_monitor",
            critical_edge_id="c6_e7",
            chain_edge_id="c6_e4",
            diagnosis_node_id="c6_dx",
            unsafe_label="Антикоагуляция и тромболизис как при STEMI",
            contraindication=("c6_thrombolysis", "c6_e8"),
        )
    )

    pe = _graph(
        [
            _node("c7_p", "Женщина 45 лет после операции, тахикардия", "PATIENT_PROFILE", 0, 0),
            _node("c7_s", "Одышка, плевритическая боль и сатурация 88%", "SYMPTOM", 220, 0),
            _node("c7_score", "Высокая клиническая вероятность ТЭЛА", "EXAM", 440, -120),
            _node("c7_ct", "КТ-ангиография легочных артерий: эмболия", "INSTRUMENTAL_TEST", 440, 80),
            _node("c7_hemo", "Оценка гемодинамической нестабильности или шока", "EXAM", 660, -150),
            _node("c7_bleeding", "Оценка послеоперационного риска кровотечения", "EXAM", 660, 150),
            _node("c7_dx", "Тромбоэмболия легочной артерии", "DIAGNOSIS", 660, 0),
            _node("c7_heparin", "Терапевтическая антикоагуляция", "MEDICATION", 880, -100),
            _node("c7_thrombolysis", "Реперфузия при шоке или высокой нестабильности", "MEDICATION", 880, 20),
            _node("c7_monitor", "Мониторинг сатурации, давления и кровотечений", "MONITORING", 880, 140),
        ],
        [
            _edge("c7_e1", "c7_p", "c7_s", "DETERMINES"),
            _edge("c7_e2", "c7_s", "c7_score", "REQUIRES_CONFIRMATION"),
            _edge("c7_e3", "c7_score", "c7_ct", "REQUIRES_CONFIRMATION"),
            _edge("c7_e4", "c7_s", "c7_hemo", "REQUIRES_CONFIRMATION"),
            _edge("c7_e5", "c7_ct", "c7_dx", "DETERMINES"),
            _edge("c7_e6", "c7_bleeding", "c7_heparin", "REQUIRES_CONFIRMATION"),
            _edge("c7_e7", "c7_dx", "c7_heparin", "INDICATED_FOR"),
            _edge("c7_e8", "c7_dx", "c7_thrombolysis", "INDICATED_FOR"),
            _edge("c7_e9", "c7_dx", "c7_monitor", "INDICATED_FOR"),
            _edge("c7_e10", "c7_hemo", "c7_thrombolysis", "DETERMINES"),
            _edge("c7_e11", "c7_p", "c7_bleeding", "DETERMINES"),
            _edge("c7_e12", "c7_dx", "c7_hemo", "REQUIRES_CONFIRMATION"),
            _edge("c7_e13", "c7_dx", "c7_bleeding", "REQUIRES_CONFIRMATION"),
        ],
    )
    cases.append(
        _case(
            "cardio_pe_07",
            "ТЭЛА: вероятность, визуализация и антикоагуляция",
            "Тромбоэмболия легочной артерии",
            "Послеоперационная пациентка имеет внезапную одышку, гипоксемию и тахикардию. Нужно построить граф, где клиническая вероятность направляет обследование, КТ-ангиография подтверждает ТЭЛА, а диагноз связан с антикоагуляцией, реперфузией при нестабильности и мониторингом.",
            ["оценка вероятности", "КТ-ангиография", "гемодинамическая нестабильность", "антикоагуляция", "реперфузия при нестабильности"],
            ["оценить клиническую вероятность", "при высокой вероятности направить на КТ-ангиографию без опоры на D-димер", "подтвердить диагноз КТ-ангиографией", "назначить антикоагуляцию с учетом риска кровотечения", "показать мониторинг кровотечения"],
            ["пропуск антикоагуляции", "назначение реперфузии без учета риска"],
            "Обоснование антикоагуляции и реперфузии при ТЭЛА.",
            pe,
            diagnostic_node_id="c7_ct",
            wrong_category_node_id="c7_score",
            critical_edge_id="c7_e7",
            chain_edge_id="c7_e5",
            diagnosis_node_id="c7_dx",
            unsafe_label="Амбулаторное наблюдение без антикоагуляции при подтвержденной ТЭЛА",
        )
    )

    endocarditis = _graph(
        [
            _node("c8_p", "Пациент 39 лет после протезирования клапана", "PATIENT_PROFILE", 0, 0),
            _node("c8_s", "Лихорадка, озноб и новый шум в сердце", "SYMPTOM", 220, 0),
            _node("c8_cultures", "Две пары гемокультур до антибиотиков", "LAB_TEST", 440, -120),
            _node("c8_echo", "ЭхоКГ: вегетация на клапане", "INSTRUMENTAL_TEST", 440, 0),
            _node("c8_exam", "Петехии и признаки эмболии", "EXAM", 440, 120),
            _node("c8_dx", "Инфекционный эндокардит протезированного клапана", "DIAGNOSIS", 660, 0),
            _node("c8_abx", "Эмпирическая внутривенная антибиотикотерапия после культур", "MEDICATION", 880, -100),
            _node("c8_surgery", "Кардиохирургическая оценка при осложнениях", "SURGERY", 880, 20),
            _node("c8_monitor", "Контроль гемокультур, ЭхоКГ и осложнений", "MONITORING", 880, 140),
        ],
        [
            _edge("c8_e1", "c8_p", "c8_s", "DETERMINES"),
            _edge("c8_e2", "c8_s", "c8_cultures", "REQUIRES_CONFIRMATION"),
            _edge("c8_e3", "c8_s", "c8_echo", "REQUIRES_CONFIRMATION"),
            _edge("c8_e4", "c8_echo", "c8_dx", "DETERMINES"),
            _edge("c8_e5", "c8_cultures", "c8_dx", "REQUIRES_CONFIRMATION"),
            _edge("c8_e6", "c8_exam", "c8_dx", "DETERMINES"),
            _edge("c8_e7", "c8_dx", "c8_abx", "INDICATED_FOR"),
            _edge("c8_e8", "c8_dx", "c8_surgery", "INDICATED_FOR"),
            _edge("c8_e9", "c8_dx", "c8_monitor", "INDICATED_FOR"),
        ],
    )
    cases.append(
        _case(
            "cardio_endocarditis_08",
            "Инфекционный эндокардит: культуры, ЭхоКГ и лечение",
            "Инфекционный эндокардит",
            "Пациент с протезированным клапаном имеет лихорадку, озноб и новый шум в сердце. Требуется построить граф, где гемокультуры до антибиотиков и ЭхоКГ ведут к диагнозу эндокардита, а диагноз связан с внутривенной терапией, кардиохирургической оценкой и мониторингом.",
            ["гемокультуры", "эхокардиография", "критерии диагноза", "антибиотикотерапия", "кардиохирургические показания"],
            ["взять культуры до антибиотиков", "подтвердить ЭхоКГ", "связать диагноз с антибиотиками", "показать хирургическую оценку", "указать контроль осложнений"],
            ["антибиотики до гемокультур", "пропуск хирургической оценки при осложнениях"],
            "Построение графа доказательного подтверждения эндокардита и лечения.",
            endocarditis,
            diagnostic_node_id="c8_cultures",
            wrong_category_node_id="c8_monitor",
            critical_edge_id="c8_e7",
            chain_edge_id="c8_e4",
            diagnosis_node_id="c8_dx",
            unsafe_label="Пероральный короткий курс антибиотика без гемокультур",
        )
    )

    cases.extend(_additional_protocol_control_cases())

    _attach_protocol_sources(cases, protocol_sources)

    _assert_cases_russian(cases)

    if case_count is None:
        return cases
    return cases[: max(0, min(case_count, len(cases)))]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _expert_comment(pattern: str, score: float) -> str:
    base = PATTERN_COMMENTS.get(pattern, "Экспертная оценка основана на полноте и безопасности клинической цепочки.")
    if score >= 0.9:
        return base
    if score <= 0.45:
        return f"{base} Итоговая оценка снижена из-за риска для пациента или потери ключевого решения."
    return f"{base} Требуется доработка перед принятием ответа."


def _build_synthetic_rater_panel(expert_count: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    statuses = ("practicing_cardiologist", "cardiology_faculty", "cardiology_clinician_educator")
    countries = ("anonymized_country_A", "anonymized_country_B", "anonymized_country_C")
    organizations = ("university_hospital", "cardiology_department", "teaching_clinic")
    experts: list[dict[str, Any]] = []
    for index in range(1, expert_count + 1):
        experts.append(
            {
                "expert_id": f"synthetic_rater_{index:02d}",
                "panel_mode": EXPERT_PANEL_MODE,
                "status": statuses[(index - 1) % len(statuses)],
                "country_region": countries[(index - 1) % len(countries)],
                "organization_type": organizations[(index - 1) % len(organizations)],
                "strictness": rng.gauss(0.0, 0.028),
                "variability": max(0.006, rng.gauss(0.018, 0.006)),
                "experience_years": rng.randint(5, 24),
            }
        )
    return experts


def _expert_panel_profile(expert_count: int, seed: int, item_count: int) -> dict[str, Any]:
    experts = _build_synthetic_rater_panel(expert_count, seed)
    experience = [int(item["experience_years"]) for item in experts]
    return {
        "panel_mode": EXPERT_PANEL_MODE,
        "is_human_subject_data": False,
        "publication_claim_allowed": False,
        "expert_count": expert_count,
        "status_categories": sorted({str(item["status"]) for item in experts}),
        "experience_years_min": min(experience) if experience else None,
        "experience_years_max": max(experience) if experience else None,
        "experience_years_mean": round(mean(experience), 2) if experience else None,
        "country_regions": sorted({str(item["country_region"]) for item in experts}),
        "organization_types": sorted({str(item["organization_type"]) for item in experts}),
        "evaluation_scale": EXPERT_EVALUATION_SCALE,
        "blind_evaluation_design": (
            "Each review item hides expected_pattern, model score, safety labels, and reference key. "
            "Items are randomized for reviewers; analysis joins ratings to the hidden key after collection."
        ),
        "same_items_for_all_experts": True,
        "items_per_expert": item_count,
        "expected_rating_count": expert_count * item_count,
        "expert_records": [
            {
                "expert_id": item["expert_id"],
                "panel_mode": item["panel_mode"],
                "status": item["status"],
                "experience_years": item["experience_years"],
                "country_region": item["country_region"],
                "organization_type": item["organization_type"],
            }
            for item in experts
        ],
    }


def _prospective_human_study_protocol(item_count: int) -> dict[str, Any]:
    return {
        "status": "prospective_design_not_executed_by_this_synthetic_fixture",
        "minimum_target_expert_count": 5,
        "eligible_statuses": [
            "cardiologists",
            "cardiology faculty",
            "practicing clinicians with cardiology workload",
        ],
        "minimum_experience_years": 5,
        "recommended_experience_range_years": "5-20+",
        "country_and_organization_reporting": (
            "Report country and organization only in anonymized aggregate form, for example: "
            "university hospital, cardiology department, teaching clinic."
        ),
        "rating_scale": EXPERT_EVALUATION_SCALE,
        "rating_instruction": (
            "Score clinical adequacy and safety of each graph solution: 0 means clinically unacceptable "
            "or unsafe, 100 means fully acceptable and protocol-consistent. Scores are normalized to 0-1."
        ),
        "blind_evaluation": (
            "Experts receive the clinical task, the student graph, and optional protocol excerpt, but do "
            "not receive model score, expected error pattern, variant label, or system recommendation."
        ),
        "same_items_for_all_experts": True,
        "items_per_expert": item_count,
        "planned_items_per_expert": item_count,
        "agreement_metrics": [
            "mean pairwise Spearman",
            "intraclass correlation coefficient if raw human ratings are collected",
            "Krippendorff alpha as optional robustness metric",
        ],
        "publication_rule": (
            "A human cardiologist validation claim is allowed only after imported human ratings and "
            "anonymized expert metadata are available in benchmark artifacts."
        ),
    }


def simulate_synthetic_ratings(
    benchmark: Mapping[str, Any],
    *,
    expert_count: int = 3,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    rng = random.Random(seed + 1009)
    experts = _build_synthetic_rater_panel(expert_count, seed)

    rows: list[dict[str, Any]] = []
    for result in benchmark.get("graph", {}).get("results", []) or []:
        pattern = str(result.get("expected_pattern") or "")
        metrics = result.get("metrics") or {}
        model_score = float(metrics.get("composite_score") or 0.0)
        clinical_target = PATTERN_EXPERT_TARGETS.get(pattern, model_score)
        base_score = 0.55 * clinical_target + 0.45 * model_score
        if pattern == "category_accuracy_drop":
            base_score = max(base_score, 0.72)
        if pattern in {"unsafe_extra_action_cap", "critical_relation_penalty"}:
            base_score = min(base_score, clinical_target + 0.08)

        for expert in experts:
            noise_sd = PATTERN_NOISE.get(pattern, 0.05) + float(expert["variability"])
            score = _clamp(base_score + float(expert["strictness"]) + rng.gauss(0.0, noise_sd))
            confidence = _clamp(0.82 + rng.gauss(0.0, 0.07) - (0.08 if pattern == "category_accuracy_drop" else 0.0), 0.55, 0.98)
            rows.append(
                {
                    "expert_id": expert["expert_id"],
                    "panel_mode": expert["panel_mode"],
                    "specialty": "cardiology",
                    "expert_status": expert["status"],
                    "experience_years": expert["experience_years"],
                    "country_region": expert["country_region"],
                    "organization_type": expert["organization_type"],
                    "evaluation_scale": EXPERT_EVALUATION_SCALE,
                    "case_id": result.get("case_id"),
                    "variant_id": result.get("variant_id"),
                    "expected_pattern": pattern,
                    "model_score": model_score,
                    "expert_score": round(score, 4),
                    "expert_score_0_100": round(score * 100, 1),
                    "confidence": round(confidence, 3),
                    "expert_comment": _expert_comment(pattern, score),
                }
            )
    return rows


def _task_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        task = case.get("task") or {}
        graph = case.get("reference_graph") or {}
        source = case.get("source_protocol") or task.get("source_protocol") or {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "protocol_area": case.get("protocol_area"),
                "database_protocol_id": source.get("protocol_id"),
                "source_protocol_id": _external_protocol_id(source),
                "source_protocol_title": source.get("protocol_title"),
                "source_protocol_year": source.get("protocol_year"),
                "source_protocol_sections": source.get("protocol_sections") or [],
                "source_protocol_chunk_count": source.get("protocol_chunk_count"),
                "source_protocol_url": source.get("protocol_url"),
                "source_fit": source.get("source_fit"),
                "source_note": source.get("source_note"),
                "protocol_focus": task.get("protocol_focus"),
                "difficulty": task.get("difficulty"),
                "target_competency": task.get("target_competency"),
                "task_quality_score": task.get("task_quality_score"),
                "task_quality_accepted": task.get("task_quality_accepted"),
                "expected_sections": task.get("expected_sections") or [],
                "red_flags": task.get("red_flags") or [],
                "checklist_count": len(task.get("checklist") or []),
                "description_chars": len(str(task.get("description") or "")),
                "reference_node_count": len(graph.get("nodes") or []),
                "reference_edge_count": len(graph.get("edges") or []),
                "variant_count": len(case.get("variants") or []),
            }
        )
    return rows


def _recommendation_for_result(result: Mapping[str, Any]) -> str:
    pattern = str(result.get("expected_pattern") or "")
    metrics = result.get("metrics") or {}
    missing_nodes = int(result.get("missing_nodes_count") or 0)
    missing_edges = int(result.get("missing_edges_count") or 0)
    safety = result.get("safety_findings") or []

    if pattern == "all_metrics_high" and float(metrics.get("composite_score") or 0.0) >= 0.95:
        return "Ответ можно принимать: граф сохраняет диагностическую цепочку, лечение и мониторинг."
    if safety:
        return "Проверить назначение: система обнаружила небезопасное лишнее действие или потерю критической связи безопасности."
    if pattern == "category_accuracy_drop":
        return "Уточнить тип узла: диагностический тест, мониторинг и лекарственная терапия должны быть разведены по категориям."
    if pattern == "missing_critical_action_penalty":
        return "Вернуть критическое действие в цепочку от диагноза: лечение/мониторинг не должны быть изолированными."
    if pattern in {"directed_path_drop", "directed_path_zero"}:
        return "Восстановить направленную причинную цепочку от симптомов и обследования к диагнозу и действиям."
    if missing_nodes or missing_edges:
        return "Дополнить пропущенные клинические элементы и связи, затем повторить автоматическую оценку."
    return "Требуется экспертная проверка расхождения между ожидаемым паттерном и рассчитанными метриками."


def _recommendation_rows(graph_result: Mapping[str, Any], expert_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    expert_by_key = {
        f"{item.get('case_id')}::{item.get('variant_id')}": item
        for item in expert_report.get("items", []) or []
    }
    rows = []
    for result in graph_result.get("results", []) or []:
        key = f"{result.get('case_id')}::{result.get('variant_id')}"
        metrics = result.get("metrics") or {}
        expert_item = expert_by_key.get(key, {})
        expert_mean = expert_item.get("expert_mean_score")
        model_score = float(metrics.get("composite_score") or 0.0)
        rows.append(
            {
                "case_id": result.get("case_id"),
                "variant_id": result.get("variant_id"),
                "expected_pattern": result.get("expected_pattern"),
                "model_score": model_score,
                "expert_mean_score": round(float(expert_mean), 4) if expert_mean is not None else None,
                "score_gap_model_minus_expert": (
                    round(model_score - float(expert_mean), 4) if expert_mean is not None else None
                ),
                "system_recommendation": _recommendation_for_result(result),
                "missing_edges_count": result.get("missing_edges_count"),
                "incorrect_edges_count": result.get("incorrect_edges_count"),
                "missing_nodes_count": result.get("missing_nodes_count"),
                "safety_findings": result.get("safety_findings") or [],
            }
        )
    return rows


def _pattern_summary(graph_result: Mapping[str, Any], expert_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    expert_by_key = {
        f"{item.get('case_id')}::{item.get('variant_id')}": item
        for item in expert_report.get("items", []) or []
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in graph_result.get("results", []) or []:
        pattern = str(result.get("expected_pattern") or "")
        key = f"{result.get('case_id')}::{result.get('variant_id')}"
        grouped.setdefault(pattern, []).append({"result": result, "expert": expert_by_key.get(key, {})})

    rows = []
    for pattern, items in sorted(grouped.items()):
        model_scores = [float(item["result"].get("metrics", {}).get("composite_score") or 0.0) for item in items]
        expert_scores = [
            float(item["expert"].get("expert_mean_score") or 0.0)
            for item in items
            if item["expert"].get("expert_mean_score") is not None
        ]
        rows.append(
            {
                "expected_pattern": pattern,
                "n": len(items),
                "mean_model_score": round(mean(model_scores), 4) if model_scores else None,
                "mean_expert_score": round(mean(expert_scores), 4) if expert_scores else None,
                "mean_gap_model_minus_expert": (
                    round(mean(model_scores) - mean(expert_scores), 4)
                    if model_scores and expert_scores
                    else None
                ),
                "pattern_pass_rate": round(
                    sum(1 for item in items if item["result"].get("pattern_passed") is True) / len(items),
                    4,
                )
                if items
                else None,
            }
        )
    return rows


def _run_graph_benchmark_from_cases(
    cases: list[dict[str, Any]],
    *,
    use_embeddings: bool = False,
) -> dict[str, Any]:
    if not use_embeddings:
        graph_evaluator_module._compute_node_embeddings = lambda *_: {}

    results: list[dict[str, Any]] = []
    reference_quality_results: list[dict[str, Any]] = []
    for case in cases:
        reference_payload = case["reference_graph"]
        reference_graph = GraphSchema.model_validate(reference_payload)
        reference_quality = judge_reference_graph(reference_graph)
        reference_quality_results.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "quality": reference_quality,
            }
        )

        for variant in case.get("variants", []):
            student_payload = _student_graph_payload(reference_payload, variant)
            student_graph = GraphSchema.model_validate(student_payload)

            t0 = time.perf_counter()
            evaluation = GraphEvaluator.evaluate(student_graph, reference_graph)
            latency_ms = (time.perf_counter() - t0) * 1000
            metrics = {key: evaluation.get(key) for key in GRAPH_METRIC_KEYS}
            pattern_check = _graph_pattern_check(variant.get("expected_pattern"), metrics)

            results.append(
                {
                    "case_id": case.get("case_id"),
                    "variant_id": variant.get("variant_id"),
                    "expected_pattern": variant.get("expected_pattern"),
                    "pattern_passed": pattern_check["passed"],
                    "pattern_reason": pattern_check["reason"],
                    "latency_ms": round(latency_ms, 2),
                    "metrics": metrics,
                    "missing_edges_count": len(evaluation.get("missing_edges") or []),
                    "incorrect_edges_count": len(evaluation.get("incorrect_edges") or []),
                    "missing_nodes_count": len(evaluation.get("missing_nodes") or []),
                    "safety_findings": evaluation.get("safety_findings") or [],
                    "algorithm_version": evaluation.get("algorithm_version"),
                }
            )

    return {
        "summary": aggregate_graph_results(results),
        "reference_quality": {
            "summary": aggregate_graph_quality_results(reference_quality_results),
            "results": reference_quality_results,
        },
        "results": results,
    }


def _summary(
    cases: list[dict[str, Any]],
    graph_result: Mapping[str, Any],
    expert_report: Mapping[str, Any],
    rating_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    task_rows = _task_rows(cases)
    reference_summary = graph_result.get("reference_quality", {}).get("summary") or {}
    graph_summary = graph_result.get("summary") or {}
    correlation = expert_report.get("correlation_with_mean_expert") or {}
    inter_rater = expert_report.get("inter_rater") or {}
    baselines = expert_report.get("baseline_comparison") or []
    non_composite_baselines = [row for row in baselines if row.get("model") != "composite_v4_3"]
    best_baseline = max(
        non_composite_baselines,
        key=lambda row: float(row.get("spearman") or -1.0),
        default={},
    )
    averages = graph_summary.get("averages") or {}
    source_rows = _source_protocol_rows(cases)
    source_ids = {
        row.get("source_protocol_id") or row.get("database_protocol_id")
        for row in source_rows
        if row.get("source_protocol_id") is not None
        or row.get("database_protocol_id") is not None
    }
    direct_sources = [
        row for row in source_rows if row.get("source_fit") == "direct_cardiology_protocol"
    ]
    return {
        "case_count": len(cases),
        "task_count": len(task_rows),
        "variant_count": len(graph_result.get("results") or []),
        "expert_count": expert_report.get("expert_count"),
        "rating_count": len(rating_rows),
        "source_protocol_count": len(source_ids),
        "direct_cardiology_protocol_rate": (
            round(len(direct_sources) / len(source_rows), 4) if source_rows else None
        ),
        "task_quality_avg": (
            round(mean(float(row.get("task_quality_score") or 0.0) for row in task_rows), 4)
            if task_rows
            else None
        ),
        "task_acceptance_rate": (
            round(sum(1 for row in task_rows if row.get("task_quality_accepted")) / len(task_rows), 4)
            if task_rows
            else None
        ),
        "reference_accepted_rate": reference_summary.get("accepted_rate"),
        "reference_quality_avg": reference_summary.get("avg_quality_score"),
        "pattern_pass_rate": graph_summary.get("pattern_pass_rate"),
        "system_avg_composite": averages.get("composite_score"),
        "system_avg_weighted_edge_f1": averages.get("weighted_edge_f1"),
        "system_avg_directed_path": averages.get("directed_path_completeness"),
        "system_avg_safety_penalty": averages.get("safety_penalty"),
        "system_avg_diagnostic_evidence_gap": averages.get("diagnostic_evidence_gap"),
        "expert_pearson": correlation.get("pearson"),
        "expert_pearson_ci_low": correlation.get("pearson_ci_low"),
        "expert_pearson_ci_high": correlation.get("pearson_ci_high"),
        "expert_spearman": correlation.get("spearman"),
        "expert_spearman_ci_low": correlation.get("spearman_ci_low"),
        "expert_spearman_ci_high": correlation.get("spearman_ci_high"),
        "expert_kendall_tau_a": correlation.get("kendall_tau_a"),
        "expert_kendall_tau_a_ci_low": correlation.get("kendall_tau_a_ci_low"),
        "expert_kendall_tau_a_ci_high": correlation.get("kendall_tau_a_ci_high"),
        "expert_mae": correlation.get("mae"),
        "expert_mae_ci_low": correlation.get("mae_ci_low"),
        "expert_mae_ci_high": correlation.get("mae_ci_high"),
        "expert_rmse": correlation.get("rmse"),
        "expert_rmse_ci_low": correlation.get("rmse_ci_low"),
        "expert_rmse_ci_high": correlation.get("rmse_ci_high"),
        "expert_bias": correlation.get("bias"),
        "expert_bias_ci_low": correlation.get("bias_ci_low"),
        "expert_bias_ci_high": correlation.get("bias_ci_high"),
        "baseline_best_non_composite_model": best_baseline.get("model"),
        "baseline_best_non_composite_spearman": best_baseline.get("spearman"),
        "baseline_composite_delta_spearman_vs_best_baseline": (
            round(float(correlation.get("spearman")) - float(best_baseline.get("spearman")), 4)
            if correlation.get("spearman") is not None and best_baseline.get("spearman") is not None
            else None
        ),
        "baseline_composite_delta_mae_vs_best_baseline": (
            round(float(correlation.get("mae")) - float(best_baseline.get("mae")), 4)
            if correlation.get("mae") is not None and best_baseline.get("mae") is not None
            else None
        ),
        "inter_rater_spearman": inter_rater.get("mean_pairwise_spearman"),
    }


def run_cardiology_synthetic_benchmark(
    *,
    case_count: int | None = None,
    expert_count: int = 3,
    seed: int = DEFAULT_SEED,
    use_embeddings: bool = False,
    protocol_sources: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = build_cardiology_seed(case_count, protocol_sources=protocol_sources)
    t0 = time.perf_counter()
    graph_result = _run_graph_benchmark_from_cases(cases, use_embeddings=use_embeddings)
    total_latency_ms = (time.perf_counter() - t0) * 1000

    benchmark = {"graph": graph_result}
    rating_rows = simulate_synthetic_ratings(
        benchmark,
        expert_count=expert_count,
        seed=seed,
    )
    expert_report = analyze_expert_ratings(benchmark, rating_rows)
    recommendations = _recommendation_rows(graph_result, expert_report)
    pattern_summary = _pattern_summary(graph_result, expert_report)
    task_rows = _task_rows(cases)
    graph_item_count = len(graph_result.get("results") or [])
    expert_panel = _expert_panel_profile(expert_count, seed, graph_item_count)
    human_study_protocol = _prospective_human_study_protocol(graph_item_count)

    return {
        "generated_at": _generated_at(),
        "algorithm_version": CARDIOLOGY_ALGORITHM_VERSION,
        "parameters": {
            "case_count": len(cases),
            "expert_count": expert_count,
            "seed": seed,
            "use_embeddings": use_embeddings,
        },
        "summary": {
            **_summary(cases, graph_result, expert_report, rating_rows),
            "expert_panel_mode": expert_panel["panel_mode"],
            "expert_panel_is_human_subject_data": expert_panel["is_human_subject_data"],
            "expert_panel_publication_claim_allowed": expert_panel["publication_claim_allowed"],
            "expert_panel_items_per_expert": expert_panel["items_per_expert"],
            "total_runtime_ms": round(total_latency_ms, 2),
        },
        "source_protocols": _source_protocol_rows(cases),
        "tasks": task_rows,
        "cases": cases,
        "graph": graph_result,
        "expert_panel": expert_panel,
        "prospective_human_study_protocol": human_study_protocol,
        "expert": expert_report,
        "expert_ratings": rating_rows,
        "recommendations": recommendations,
        "pattern_summary": pattern_summary,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a synthetic cardiology graph-evaluation benchmark.")
    parser.add_argument("--cases", type=int, default=None, help="Number of cardiology cases to include.")
    parser.add_argument("--experts", type=int, default=3, help="Number of synthetic proxy raters.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic simulation seed.")
    parser.add_argument("--use-embeddings", action="store_true", help="Allow graph evaluator embeddings.")
    parser.add_argument("--out", default=None, help="Optional output JSON path relative to backend root.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    output = run_cardiology_synthetic_benchmark(
        case_count=args.cases,
        expert_count=args.experts,
        seed=args.seed,
        use_embeddings=args.use_embeddings,
    )
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        out_path = (BACKEND_ROOT / args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
