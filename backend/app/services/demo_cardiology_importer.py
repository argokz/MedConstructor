from __future__ import annotations

import json
import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentTarget,
    Discipline,
    EvaluationSnapshot,
    ReferenceGraph,
    Specialty,
    StudentAttempt,
    StudentGroup,
    User,
)
from app.schemas import GraphSchema
from app.security.demo_credentials import demo_password
from app.security.passwords import hash_password
from app.services.demo_cardiology_ru import DEMO_TIME_LIMIT_MINUTES, localize_case
from app.services.graph_evaluator import GraphEvaluator


DEMO_TEACHER_EMAIL = "teacher@demo.local"
DEMO_STUDENT_EMAIL = "student@demo.local"
DEMO_SPECIALTY_CODE = "DEMO-CARDIOLOGY"
DEMO_GROUP_NAME = "Демо-группа: кардиология"
DEMO_DISCIPLINE_CODE = "CARDIOLOGY-DEMO"
DEMO_TITLE_PREFIX = "[Демо кардиология]"


PATTERN_TITLES = {
    "all_metrics_high": "корректное решение",
    "recall_and_node_coverage_drop": "пропущен важный клинический шаг",
    "category_accuracy_drop": "неверная категория узла",
    "missing_critical_action_penalty": "пропущено критическое действие",
    "directed_path_drop": "разорвана причинно-следственная цепочка",
    "unsafe_extra_action_cap": "добавлено небезопасное лишнее действие",
    "critical_relation_penalty": "ошибка в критической клинической связи",
}


@dataclass
class DemoImportResult:
    reference_graphs: int = 0
    assignments: int = 0
    attempts: int = 0
    updated_attempts: int = 0
    targets: int = 0
    teacher_id: int | None = None
    student_id: int | None = None
    group_id: int | None = None
    assignment_ids: list[int] | None = None
    attempt_ids: list[int] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "reference_graphs": self.reference_graphs,
            "assignments": self.assignments,
            "attempts": self.attempts,
            "updated_attempts": self.updated_attempts,
            "targets": self.targets,
            "teacher_id": self.teacher_id,
            "student_id": self.student_id,
            "group_id": self.group_id,
            "assignment_ids": self.assignment_ids or [],
            "attempt_ids": self.attempt_ids or [],
        }


def load_cardiology_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cardiology", payload)


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _source_protocol(case: dict[str, Any]) -> dict[str, Any]:
    task = case.get("task") or {}
    return task.get("source_protocol") or case.get("source_protocol") or {}


def _source_context(case: dict[str, Any]) -> list[dict[str, Any]]:
    source = _source_protocol(case)
    if not source:
        return []
    sections = _safe_list(source.get("protocol_sections"))
    category = source.get("protocol_category") or (sections[0] if sections else None)
    protocol_url = source.get("protocol_url")
    external_id = source.get("protocol_external_id") or source.get("external_protocol_id") or source.get("medelement_id")
    if not external_id and isinstance(protocol_url, str):
        match = re.search(r"/(\d+)(?:$|[/?#])", protocol_url)
        if match:
            external_id = match.group(1)
    return [
        {
            "protocol_id": source.get("protocol_id"),
            "protocol_external_id": str(external_id) if external_id not in (None, "") else None,
            "protocol_title": source.get("protocol_title"),
            "protocol_year": source.get("protocol_year"),
            "protocol_version": source.get("protocol_version"),
            "protocol_url": protocol_url,
            "protocol_category": category,
            "protocol_sections": sections,
            "protocol_mkb_categories": _safe_list(source.get("protocol_mkb_categories")),
            "protocol_chunk_count": source.get("protocol_chunk_count"),
            "source_fit": source.get("source_fit"),
            "source_note": source.get("source_note"),
            "case_id": case.get("case_id"),
            "source": "clinical_protocols",
        }
    ]


def _safe_list(values: Any, limit: int | None = None) -> list[str]:
    if not isinstance(values, list):
        return []
    items = [str(item) for item in values if item is not None]
    return items[:limit] if limit else items


def _task_description(case: dict[str, Any]) -> str:
    task = case.get("task") or {}
    source = _source_protocol(case)
    sections = _safe_list(task.get("expected_sections"))
    checklist = _safe_list(task.get("checklist"))
    red_flags = _safe_list(task.get("red_flags"))
    lines = [
        task.get("description") or case.get("title") or "Клиническая задача по кардиологии.",
        "",
        f"Источник: протокол #{source.get('protocol_id', '—')} — {source.get('protocol_title', '—')}",
        f"Фокус: {task.get('protocol_focus') or 'кардиологическое клиническое решение'}",
    ]
    if sections:
        lines.append("Ожидаемые разделы протокола: " + "; ".join(sections))
    if checklist:
        lines.append("Чек-лист решения: " + "; ".join(checklist))
    if red_flags:
        lines.append("Критические риски: " + "; ".join(red_flags))
    lines.append("Создано для демо-преподавателя; сдачи ниже выполнены демо-студентом.")
    return "\n".join(lines)


async def _get_or_create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: str,
    full_name: str,
) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        user = User(email=email, password_hash=hash_password(password), role=role, full_name=full_name)
        session.add(user)
        await session.flush()
        return user
    # Never reset the password of an existing account: an operator may have
    # rotated the demo credentials in production, and re-importing demo data
    # must not restore a known/weak password.
    user.role = role
    user.full_name = full_name
    return user


async def _get_or_create_specialty(session: AsyncSession) -> Specialty:
    result = await session.execute(select(Specialty).where(Specialty.code == DEMO_SPECIALTY_CODE))
    row = result.scalars().first()
    if row:
        return row
    row = Specialty(
        name="Демо-специальность: кардиология",
        code=DEMO_SPECIALTY_CODE,
        description="Демо-контур для проверки задач, эталонных графов и студенческих решений по кардиологическим протоколам.",
    )
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_group(session: AsyncSession, specialty: Specialty) -> StudentGroup:
    result = await session.execute(select(StudentGroup).where(StudentGroup.name == DEMO_GROUP_NAME))
    row = result.scalars().first()
    if row:
        row.specialty_id = specialty.id
        row.year = 6
        return row
    row = StudentGroup(name=DEMO_GROUP_NAME, specialty_id=specialty.id, year=6)
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_discipline(session: AsyncSession) -> Discipline:
    result = await session.execute(select(Discipline).where(Discipline.code == DEMO_DISCIPLINE_CODE))
    row = result.scalars().first()
    if row:
        row.name = "Кардиология"
        return row
    row = Discipline(name="Кардиология", code=DEMO_DISCIPLINE_CODE)
    session.add(row)
    await session.flush()
    return row


async def _upsert_reference_graph(
    session: AsyncSession,
    *,
    case: dict[str, Any],
    discipline: Discipline,
) -> ReferenceGraph:
    title = f"{DEMO_TITLE_PREFIX} {case['case_id']}: {case.get('title') or case['case_id']}"
    result = await session.execute(select(ReferenceGraph).where(ReferenceGraph.title == title))
    row = result.scalars().first()
    if not row:
        row = ReferenceGraph(title=title, discipline_id=discipline.id)
        session.add(row)
    row.description = _task_description(case)
    graph_data = deepcopy(case["reference_graph"])
    source_context = _source_context(case)
    if source_context and isinstance(graph_data, dict):
        metadata = graph_data.setdefault("metadata", {})
        metadata["source_protocols"] = deepcopy(source_context)
        metadata["primary_protocol"] = deepcopy(source_context[0])
    row.graph_data = graph_data
    row.discipline_id = discipline.id
    row.source_type = row.source_type or "cardiology_protocol_demo"
    row.generation_context = source_context or row.generation_context
    await session.flush()
    return row


async def _upsert_assignment(
    session: AsyncSession,
    *,
    case: dict[str, Any],
    reference_graph: ReferenceGraph,
    discipline: Discipline,
    teacher: User,
) -> Assignment:
    title = f"{DEMO_TITLE_PREFIX} {case.get('title') or case['case_id']}"
    result = await session.execute(select(Assignment).where(Assignment.title == title))
    row = result.scalars().first()
    if not row:
        row = Assignment(
            title=title,
            discipline_id=discipline.id,
            reference_graph_id=reference_graph.id,
            created_by_id=teacher.id,
        )
        session.add(row)
    row.description = _task_description(case)
    row.discipline_id = discipline.id
    row.reference_graph_id = reference_graph.id
    row.created_by_id = teacher.id
    row.time_limit_minutes = DEMO_TIME_LIMIT_MINUTES
    row.status = row.status or "published"
    row.published_at = row.published_at or datetime.now(timezone.utc)
    await session.flush()
    return row


async def _ensure_assignment_target(session: AsyncSession, assignment: Assignment, group: StudentGroup) -> bool:
    result = await session.execute(
        select(AssignmentTarget).where(
            AssignmentTarget.assignment_id == assignment.id,
            AssignmentTarget.group_id == group.id,
        )
    )
    existing = result.scalars().first()
    if existing:
        return False
    session.add(AssignmentTarget(assignment_id=assignment.id, group_id=group.id))
    await session.flush()
    return True


def _student_graph(reference_graph: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    payload = variant.get("student_graph")
    if payload == "__same_as_reference__":
        return deepcopy(reference_graph)
    if isinstance(payload, dict):
        return deepcopy(payload)
    raise ValueError(f"Variant {variant.get('variant_id')} has no student_graph payload")


def _result_by_variant(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = payload.get("graph", {}).get("results") or []
    return {(row.get("case_id"), row.get("variant_id")): row for row in rows}


def _recommendation_by_variant(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = payload.get("recommendations") or []
    return {(row.get("case_id"), row.get("variant_id")): row for row in rows}


def _review_status(metrics: dict[str, Any], result_row: dict[str, Any]) -> str:
    composite = float(metrics.get("composite_score") or metrics.get("f1_score") or 0.0)
    safety = float(metrics.get("safety_penalty") or 0.0)
    if composite >= 0.9 and safety == 0 and result_row.get("pattern_passed", True):
        return "accepted"
    return "revision_requested"


def _teacher_comment(variant: dict[str, Any], recommendation: dict[str, Any] | None, metrics: dict[str, Any]) -> str:
    pattern = variant.get("expected_pattern") or "unknown"
    pattern_title = PATTERN_TITLES.get(pattern, pattern)
    base = recommendation.get("system_recommendation") if recommendation else None
    if not base:
        base = "Проверьте полноту клинической цепочки и безопасность назначений."
    score = float(metrics.get("composite_score") or metrics.get("f1_score") or 0.0)
    return f"{base} Паттерн варианта: {pattern_title}. Автоматическая оценка: {score:.1%}."


def _metric_payload(
    *,
    case: dict[str, Any],
    variant: dict[str, Any],
    result_row: dict[str, Any],
    recommendation: dict[str, Any] | None,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    source = _source_protocol(case)
    return {
        **evaluation,
        "benchmark_case_id": case.get("case_id"),
        "benchmark_variant_id": variant.get("variant_id"),
        "expected_pattern": variant.get("expected_pattern"),
        "expected_pattern_ru": PATTERN_TITLES.get(variant.get("expected_pattern"), variant.get("expected_pattern")),
        "variant_description": variant.get("description"),
        "pattern_passed": result_row.get("pattern_passed"),
        "pattern_reason": result_row.get("pattern_reason"),
        "source_protocol_id": source.get("protocol_id"),
        "source_protocol_title": source.get("protocol_title"),
        "source_protocol_url": source.get("protocol_url"),
        "system_recommendation": recommendation.get("system_recommendation") if recommendation else None,
        "expert_mean_score": recommendation.get("expert_mean_score") if recommendation else None,
        "score_gap_model_minus_expert": recommendation.get("score_gap_model_minus_expert") if recommendation else None,
        "demo_workflow": "cardiology_protocol_benchmark",
    }


async def import_cardiology_demo_workflow(
    session: AsyncSession,
    *,
    benchmark_path: Path,
    refresh_timestamps: bool = True,
) -> dict[str, Any]:
    payload = load_cardiology_payload(benchmark_path)
    cases = payload.get("cases") or []
    if not cases:
        raise ValueError(f"No cardiology cases found in {benchmark_path}")

    # Passwords come from DEMO_*_PASSWORD env vars in local/dev. In production
    # they are absent, so a strong random password is generated: the account
    # exists to own demo data but is not an interactive login with a known
    # password. Existing accounts keep whatever password they already have.
    teacher = await _get_or_create_user(
        session,
        email=DEMO_TEACHER_EMAIL,
        password=demo_password("teacher", generate_if_missing=True),
        role="teacher",
        full_name="Демо Преподаватель",
    )
    student = await _get_or_create_user(
        session,
        email=DEMO_STUDENT_EMAIL,
        password=demo_password("student", generate_if_missing=True),
        role="student",
        full_name="Демо Студент",
    )
    specialty = await _get_or_create_specialty(session)
    group = await _get_or_create_group(session, specialty)
    discipline = await _get_or_create_discipline(session)
    student.specialty_id = specialty.id
    student.group_id = group.id

    result_rows = _result_by_variant(payload)
    recommendations = _recommendation_by_variant(payload)
    summary = DemoImportResult(
        teacher_id=teacher.id,
        student_id=student.id,
        group_id=group.id,
        assignment_ids=[],
        attempt_ids=[],
    )
    base_time = datetime.now(timezone.utc)
    attempt_index = 0

    for case in cases:
        case = localize_case(case)
        reference_graph = await _upsert_reference_graph(session, case=case, discipline=discipline)
        assignment = await _upsert_assignment(
            session,
            case=case,
            reference_graph=reference_graph,
            discipline=discipline,
            teacher=teacher,
        )
        if await _ensure_assignment_target(session, assignment, group):
            summary.targets += 1
        summary.reference_graphs += 1
        summary.assignments += 1
        summary.assignment_ids.append(assignment.id)

        ref_schema = GraphSchema.model_validate(case["reference_graph"])
        for variant in case.get("variants") or []:
            variant_id = variant.get("variant_id")
            key = f"demo-cardiology:{case['case_id']}:{variant_id}"
            student_graph_payload = _student_graph(case["reference_graph"], variant)
            student_schema = GraphSchema.model_validate(student_graph_payload)
            evaluation = GraphEvaluator.evaluate(student_schema, ref_schema)
            result_row = result_rows.get((case.get("case_id"), variant_id), {})
            recommendation = recommendations.get((case.get("case_id"), variant_id))
            metrics = _metric_payload(
                case=case,
                variant=variant,
                result_row=result_row,
                recommendation=recommendation,
                evaluation=evaluation,
            )
            review_status = _review_status(metrics, result_row)
            timestamp = base_time + timedelta(seconds=attempt_index)
            attempt_index += 1

            existing = await session.execute(
                select(StudentAttempt).where(
                    StudentAttempt.student_id == student.id,
                    StudentAttempt.idempotency_key == key,
                )
            )
            attempt = existing.scalars().first()
            if not attempt:
                attempt = StudentAttempt(student_id=student.id, idempotency_key=key)
                session.add(attempt)
            else:
                summary.updated_attempts += 1

            attempt.assignment_id = assignment.id
            attempt.reference_graph_id = reference_graph.id
            attempt.student_graph = deepcopy(student_graph_payload)
            attempt.submitted_graph = deepcopy(student_graph_payload)
            attempt.metrics = metrics
            attempt.review_status = review_status
            attempt.teacher_comment = _teacher_comment(variant, recommendation, metrics)
            attempt.reviewed_by_id = teacher.id
            attempt.reviewed_at = timestamp
            attempt.algorithm_version = evaluation.get("algorithm_version")
            attempt.embedding_model_version = "identity"
            if refresh_timestamps:
                attempt.created_at = timestamp
                attempt.updated_at = timestamp
            await session.flush()
            existing_snapshot = await session.execute(
                select(EvaluationSnapshot).where(
                    EvaluationSnapshot.attempt_id == attempt.id,
                    EvaluationSnapshot.graph_version == 1,
                )
            )
            snapshot = existing_snapshot.scalars().first()
            if not snapshot:
                snapshot = EvaluationSnapshot(attempt_id=attempt.id, graph_version=1)
                session.add(snapshot)
            snapshot.assignment_id = assignment.id
            snapshot.reference_graph_id = reference_graph.id
            snapshot.student_id = student.id
            snapshot.submitted_graph = deepcopy(student_graph_payload)
            snapshot.metrics = deepcopy(metrics)
            snapshot.recommendations = {
                "missing_edges": metrics.get("missing_edges", []),
                "incorrect_edges": metrics.get("incorrect_edges", []),
                "missing_nodes": metrics.get("missing_nodes", []),
                "safety_findings": metrics.get("safety_findings", []),
                "system_recommendation": metrics.get("system_recommendation"),
            }
            snapshot.algorithm_version = evaluation.get("algorithm_version")
            snapshot.reference_content_hash = _stable_hash(case["reference_graph"])
            snapshot.embedding_model_version = "identity"
            if refresh_timestamps:
                snapshot.created_at = timestamp
            summary.attempts += 1
            summary.attempt_ids.append(attempt.id)

    await session.commit()
    return summary.model_dump()
