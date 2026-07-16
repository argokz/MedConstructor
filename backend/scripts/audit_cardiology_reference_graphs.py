"""Build an actionable audit of cardiology reference graphs.

The expert validation artifact answers "how well does the automatic score agree
with cardiologists?". This script answers the next operational question:
"which reference graphs should a teacher revise before the next validation
round?".

Usage:
    cd backend
    python scripts/audit_cardiology_reference_graphs.py --cohort cardiology_pilot
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User, ValidationRating, ValidationVariant
from app.schemas import GraphSchema
from app.services.graph_evaluator import EVALUATION_ALGORITHM_VERSION, GraphEvaluator
from app.services.graph_generation_judge import judge_reference_graph


BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = BACKEND_ROOT / "benchmarks" / "cardiology_reference_audit_latest.json"
OUT_CSV = BACKEND_ROOT / "benchmarks" / "cardiology_reference_audit_latest.csv"


ISSUE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "clinical_connectivity",
        (
            "изол",
            "висит",
            "не ведет",
            "не связ",
            "нет связи",
            "нет стрел",
            "нет реб",
            "разорванная связь",
            "разорван",
            "path",
            "orphan",
            "isolated",
            "detached",
            "broken chain",
            "missing edge",
        ),
    ),
    (
        "diagnostic_evidence",
        (
            "не хватает диагност",
            "нет диагност",
            "отсутствует диагност",
            "диагноз не подтверж",
            "ошибочно подтверж",
            "тропонин",
            "d-dimer",
            "д-димер",
            "кт",
            "ангиограф",
            "эхо",
            "посев",
            "гемокультур",
            "gold standard",
            "duke",
            "evidence",
        ),
    ),
    (
        "safety",
        (
            "небезопас",
            "фатал",
            "смерт",
            "леталь",
            "стоить пациенту жизни",
            "опасная ошибка",
            "опасной ошибки",
            "опасная лечебная",
            "смертельно опас",
            "противопоказано назнач",
            "противопоказанное действие",
            "unsafe",
            "fatal",
            "life-threatening",
            "contraindicated action",
        ),
    ),
    (
        "category_or_semantics",
        (
            "категор",
            "тип узла",
            "semantic",
            "семантик",
            "relation",
            "связь типа",
            "шкала",
            "risk score",
        ),
    ),
    (
        "too_abstract",
        (
            "абстракт",
            "слишком общ",
            "общий блок",
            "обобщ",
            "generic",
            "abstract",
            "not specific",
        ),
    ),
    (
        "rag_readiness",
        (
            "rag",
            "генератор",
            "готов для rag",
            "rag-ready",
            "ready for rag",
            "publication",
        ),
    ),
)


RECOMMENDATIONS = {
    "clinical_connectivity": "Проверить направленные ребра: пациент/симптомы -> диагностика -> диагноз -> лечение/мониторинг; убрать изолированные узлы.",
    "diagnostic_evidence": "Уточнить диагностическую опору: связать ключевой тест или gold-standard исследование с диагнозом и не превращать скрининг в подтверждение.",
    "safety": "Провести клинический safety-review: явно разделить показанные и противопоказанные действия, убрать потенциально опасные ветки.",
    "category_or_semantics": "Проверить категории узлов и типы связей; шкалы риска, мониторинг, диагностика и терапия должны быть разведены семантически.",
    "too_abstract": "Заменить слишком общие блоки на конкретные действия, тесты, препараты или мониторинговые параметры.",
    "rag_readiness": "Проверить пригодность графа как эталона для RAG/обучения: граф должен быть понятен без внешних догадок.",
    "expert_reference_quality": "Эталон ниже экспертного порога; требуется ручная доработка преподавателем/кардиологом перед следующим раундом.",
    "model_overestimates_reference": "Сравнение графа с самим собой завышает балл; использовать отдельный reference-quality audit, а не только composite score.",
    "automated_judge_warning": "Разобрать предупреждения автоматического judge и устранить критические структурные дефекты.",
}


def _norm_score(score: float | int | None) -> float | None:
    if score is None:
        return None
    value = float(score)
    return value / 100.0 if value > 1.0 else value


def _shorten(text: str, limit: int = 420) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _comment_tags(comments: Iterable[str]) -> set[str]:
    joined = "\n".join(str(comment or "").lower() for comment in comments)
    tags: set[str] = set()
    for tag, needles in ISSUE_RULES:
        for needle in needles:
            start = 0
            while True:
                index = joined.find(needle, start)
                if index < 0:
                    break
                context = joined[max(0, index - 90): index + 140]
                start = index + len(needle)
                if _is_positive_context(tag, context):
                    continue
                tags.add(tag)
                break
            if tag in tags:
                break
    return tags


def _is_positive_context(tag: str, context: str) -> bool:
    if tag == "safety":
        return any(
            marker in context
            for marker in (
                "опасной ошибки нет",
                "опасной лечебной ветки",
                "нет фатальных",
                "безопас",
                "удален",
                "удалён",
                "устран",
                "исправ",
                "нет критических",
                "no unsafe",
            )
        )
    if tag == "clinical_connectivity":
        return any(
            marker in context
            for marker in (
                "не является изол",
                "не изол",
                "корректно интегр",
                "интегрирован",
                "исправ",
                "восстанов",
                "связано корректно",
            )
        )
    if tag == "rag_readiness":
        return any(
            marker in context
            for marker in (
                "готов",
                "подготовлен",
                "ready",
                "корректно интегр",
            )
        )
    if tag == "diagnostic_evidence":
        return any(
            marker in context
            for marker in (
                "корректно",
                "правильно",
                "достаточно",
                "интегрирован",
                "задачу выполняет",
            )
        )
    if tag == "too_abstract":
        return "не слишком" in context
    return False


def _safe_graph_schema(payload: Any) -> GraphSchema | None:
    if not isinstance(payload, dict):
        return None
    try:
        return GraphSchema.model_validate(payload)
    except Exception:
        return None


def _automated_tags(metrics: dict[str, Any], judge: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    if float(metrics.get("clinical_connectivity_gap") or 0.0) > 0:
        tags.add("clinical_connectivity")
    if float(metrics.get("diagnostic_evidence_gap") or 0.0) > 0:
        tags.add("diagnostic_evidence")
    if float(metrics.get("safety_penalty") or 0.0) > 0:
        tags.add("safety")
    actionable_warnings = [
        warning
        for warning in judge.get("warnings") or []
        if str(warning.get("severity") or "").lower() in {"warning", "critical"}
    ]
    if int(judge.get("critical_count") or 0) > 0 or actionable_warnings:
        tags.add("automated_judge_warning")
    return tags


def _automated_findings(metrics: dict[str, Any], judge: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for key in (
        "clinical_connectivity_findings",
        "diagnostic_evidence_findings",
        "safety_findings",
        "score_caps",
    ):
        value = metrics.get(key) or []
        if isinstance(value, list):
            for item in value:
                findings.append({"source": key, "detail": item})
    for warning in judge.get("warnings") or []:
        findings.append({"source": "reference_judge", "detail": warning})
    return findings


def _priority(
    *,
    expert_mean: float | None,
    accept_rate: float | None,
    model_gap: float | None,
    tags: set[str],
    judge: dict[str, Any],
) -> str:
    if (
        expert_mean is not None
        and expert_mean >= 0.85
        and (model_gap is None or model_gap <= 0.15)
        and int(judge.get("critical_count") or 0) == 0
    ):
        return "low"
    if (
        (expert_mean is not None and expert_mean < 0.79)
        or (
            accept_rate is not None
            and accept_rate < 0.75
            and expert_mean is not None
            and expert_mean < 0.82
        )
        or int(judge.get("critical_count") or 0) > 0
        or ("safety" in tags and expert_mean is not None and expert_mean < 0.82)
    ):
        return "high"
    if (
        (expert_mean is not None and expert_mean < 0.85)
        or (model_gap is not None and model_gap > 0.15)
        or tags.intersection({"clinical_connectivity", "diagnostic_evidence", "automated_judge_warning"})
    ):
        return "medium"
    return "low"


def _recommendation(tags: set[str]) -> str:
    ordered = [
        "expert_reference_quality",
        "safety",
        "diagnostic_evidence",
        "clinical_connectivity",
        "category_or_semantics",
        "too_abstract",
        "rag_readiness",
        "automated_judge_warning",
        "model_overestimates_reference",
    ]
    selected = [RECOMMENDATIONS[tag] for tag in ordered if tag in tags and tag in RECOMMENDATIONS]
    return " ".join(selected) if selected else "Эталон можно оставить в текущем виде, но перед публикацией желательно финальное преподавательское подтверждение."


async def _load(cohort: str) -> tuple[list[ValidationVariant], list[tuple[ValidationRating, User]]]:
    async with AsyncSessionLocal() as session:
        variant_rows = await session.execute(
            select(ValidationVariant)
            .where(ValidationVariant.cohort == cohort)
            .where(ValidationVariant.is_active == 1)
            .where(ValidationVariant.variant_id == "correct_reference_solution")
            .order_by(ValidationVariant.case_id)
        )
        variants = list(variant_rows.scalars().all())
        if not variants:
            return [], []

        rating_rows = await session.execute(
            select(ValidationRating, User)
            .join(User, User.id == ValidationRating.expert_id)
            .where(ValidationRating.variant_id.in_([variant.id for variant in variants]))
            .order_by(User.email)
        )
        return variants, list(rating_rows.all())


def _build_rows(
    variants: list[ValidationVariant],
    rating_rows: list[tuple[ValidationRating, User]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    ratings_by_variant: dict[int, list[tuple[ValidationRating, User]]] = {}
    for rating, expert in rating_rows:
        ratings_by_variant.setdefault(int(rating.variant_id), []).append((rating, expert))

    expert_emails = sorted({user.email or f"expert_{user.id}" for _, user in rating_rows})
    expert_codes = {
        email: f"expert_{index:02d}"
        for index, email in enumerate(expert_emails, start=1)
    }

    rows: list[dict[str, Any]] = []
    for variant in variants:
        variant_ratings = ratings_by_variant.get(int(variant.id), [])
        scores = [
            _norm_score(rating.score)
            for rating, _ in variant_ratings
            if _norm_score(rating.score) is not None
        ]
        comments = [str(rating.comment or "").strip() for rating, _ in variant_ratings if str(rating.comment or "").strip()]
        accepts = [
            str(rating.accept or "").strip().lower()
            for rating, _ in variant_ratings
            if str(rating.accept or "").strip()
        ]
        accept_yes = sum(1 for value in accepts if value == "yes")
        accept_rate = accept_yes / len(accepts) if accepts else None
        expert_mean = mean(scores) if scores else None
        expert_min = min(scores) if scores else None
        expert_max = max(scores) if scores else None

        graph = _safe_graph_schema(variant.reference_graph)
        if graph:
            metrics = GraphEvaluator.evaluate(graph, graph)
            judge = judge_reference_graph(graph)
        else:
            metrics = {}
            judge = {
                "accepted": False,
                "quality_score": 0.0,
                "critical_count": 1,
                "warning_count": 1,
                "warnings": [{"code": "invalid_reference_graph", "severity": "critical"}],
            }

        model_score = float(metrics.get("composite_score") or (variant.model_metrics or {}).get("composite_score") or 0.0)
        model_gap = model_score - expert_mean if expert_mean is not None else None

        tags = set()
        tags.update(_comment_tags(comments))
        tags.update(_automated_tags(metrics, judge))
        if expert_mean is not None and expert_mean < threshold:
            tags.add("expert_reference_quality")
        if model_gap is not None and model_gap > 0.15:
            tags.add("model_overestimates_reference")

        priority = _priority(
            expert_mean=expert_mean,
            accept_rate=accept_rate,
            model_gap=model_gap,
            tags=tags,
            judge=judge,
        )
        automated_findings = _automated_findings(metrics, judge)
        tag_counts = Counter()
        for comment in comments:
            tag_counts.update(_comment_tags([comment]))

        rows.append(
            {
                "cohort": variant.cohort,
                "case_id": variant.case_id,
                "case_title": variant.case_title,
                "review_item_id": variant.review_item_id,
                "case_prompt": variant.case_prompt,
                "audit_required": priority in {"high", "medium"},
                "priority": priority,
                "issue_tags": sorted(tags),
                "issue_tag_counts": dict(sorted(tag_counts.items())),
                "recommendation": _recommendation(tags),
                "expert_mean_score": round(expert_mean, 4) if expert_mean is not None else None,
                "expert_min_score": round(expert_min, 4) if expert_min is not None else None,
                "expert_max_score": round(expert_max, 4) if expert_max is not None else None,
                "expert_accept_rate": round(accept_rate, 4) if accept_rate is not None else None,
                "rating_count": len(scores),
                "model_score": round(model_score, 4),
                "model_minus_expert": round(model_gap, 4) if model_gap is not None else None,
                "judge_quality_score": judge.get("quality_score"),
                "judge_accepted": judge.get("accepted"),
                "judge_critical_count": judge.get("critical_count"),
                "judge_warning_count": judge.get("warning_count"),
                "clinical_connectivity_gap": metrics.get("clinical_connectivity_gap"),
                "diagnostic_evidence_gap": metrics.get("diagnostic_evidence_gap"),
                "safety_penalty": metrics.get("safety_penalty"),
                "automated_findings": automated_findings,
                "expert_comments": [
                    {
                        "expert_code": expert_codes.get(user.email or f"expert_{user.id}"),
                        "score": _norm_score(rating.score),
                        "accept": rating.accept,
                        "comment": rating.comment,
                    }
                    for rating, user in variant_ratings
                ],
                "comment_excerpt": _shorten(" | ".join(comments), 520),
            }
        )
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(
        key=lambda row: (
            order.get(str(row["priority"]), 9),
            float(row["expert_mean_score"] or 1.0),
            str(row["case_id"] or ""),
        )
    )
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    priorities = Counter(str(row["priority"]) for row in rows)
    tags = Counter(tag for row in rows for tag in row.get("issue_tags", []))
    expert_scores = [
        float(row["expert_mean_score"])
        for row in rows
        if row.get("expert_mean_score") is not None
    ]
    return {
        "case_count": len(rows),
        "audit_required_count": sum(1 for row in rows if row.get("audit_required")),
        "high_priority_count": priorities.get("high", 0),
        "medium_priority_count": priorities.get("medium", 0),
        "low_priority_count": priorities.get("low", 0),
        "mean_reference_expert_score": round(mean(expert_scores), 4) if expert_scores else None,
        "priority_counts": dict(sorted(priorities.items())),
        "issue_tag_counts": dict(tags.most_common()),
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "priority",
        "audit_required",
        "case_id",
        "case_title",
        "expert_mean_score",
        "expert_accept_rate",
        "model_score",
        "model_minus_expert",
        "judge_quality_score",
        "judge_critical_count",
        "judge_warning_count",
        "clinical_connectivity_gap",
        "diagnostic_evidence_gap",
        "safety_penalty",
        "issue_tags",
        "recommendation",
        "comment_excerpt",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {field: row.get(field) for field in fields}
            out["issue_tags"] = "; ".join(row.get("issue_tags") or [])
            writer.writerow(out)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create an actionable audit for cardiology reference graphs.")
    parser.add_argument("--cohort", default="cardiology_pilot")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--json", default=str(OUT_JSON))
    parser.add_argument("--csv", default=str(OUT_CSV))
    args = parser.parse_args()

    variants, rating_rows = await _load(args.cohort)
    rows = _build_rows(variants, rating_rows, threshold=args.threshold)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": args.cohort,
        "algorithm_version": EVALUATION_ALGORITHM_VERSION,
        "audit_threshold": args.threshold,
        "summary": _summary(rows),
        "items": rows,
    }

    json_path = Path(args.json)
    csv_path = Path(args.csv)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_csv(rows, csv_path)
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(json_path),
                "csv": str(csv_path),
                "summary": payload["summary"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
