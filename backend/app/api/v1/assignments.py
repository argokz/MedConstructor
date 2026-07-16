from datetime import datetime, timedelta, timezone
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, get_current_user
from app.models import AssignmentTarget, EvaluationSnapshot, ReferenceGraph, Assignment, Discipline, StudentAttempt, StudentAssignmentProgress, User
from app.repositories.assignment import AssignmentRepository
from app.schemas import (
    AssignmentApproveReferenceRequest,
    AssignmentProgressPublic,
    AssignmentDraftUpdate,
    AssignmentDraftResponse,
    AssignmentListResponse,
    AssignmentPublishRequest,
    AssignmentPublic,
    AssignmentReviewBundle,
    AssignmentTargetPublic,
    AssignmentTargetsUpdate,
    GraphSchema,
    ReferenceGraphPublic,
    StudentAttemptListResponse,
    StudentAttemptPublic,
    StudentAttemptReviewUpdate,
    UserPublic,
    AssignmentCreate,
    AssignmentFromRagRequest,
    EvaluationSnapshotListResponse,
    EvaluationSnapshotPublic,
)
from app.services.assignment_generator_service import generate_assignment_with_llm
from app.services.concept_palette import build_assignment_palette
from app.services.curriculum_service import ensure_curriculum_baseline
from app.services.graph_generation_judge import format_quality_warning, judge_reference_graph

router = APIRouter(tags=["assignments"])


def _target_public(target: AssignmentTarget) -> AssignmentTargetPublic:
    return AssignmentTargetPublic(
        id=target.id,
        assignment_id=target.assignment_id,
        specialty_id=target.specialty_id,
        group_id=target.group_id,
    )


async def _targets_by_assignment(db: DbSession, assignment_ids: list[int]) -> dict[int, list[AssignmentTarget]]:
    if not assignment_ids:
        return {}
    rows = await db.execute(
        select(AssignmentTarget).where(AssignmentTarget.assignment_id.in_(assignment_ids))
    )
    result: dict[int, list[AssignmentTarget]] = {}
    for target in rows.scalars().all():
        result.setdefault(target.assignment_id, []).append(target)
    return result


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _assignment_status(assignment: Assignment) -> str:
    status_value = assignment.status or "published"
    if status_value == "review_ready":
        return "needs_teacher_review"
    if status_value == "approved":
        return "teacher_approved"
    return status_value


def _reference_status(reference_graph: ReferenceGraph) -> str:
    status_value = reference_graph.status or "teacher_approved"
    if status_value == "review_ready":
        return "needs_teacher_review"
    if status_value == "approved":
        return "teacher_approved"
    return status_value


def _reference_warnings(reference_graph: ReferenceGraph) -> list[str]:
    warnings = reference_graph.validation_warnings or []
    if isinstance(warnings, list):
        return [str(item) for item in warnings]
    return [str(warnings)]


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, tuple):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if str(value) else []


def _external_protocol_id(entry: dict[str, Any]) -> str | None:
    explicit = (
        entry.get("protocol_external_id")
        or entry.get("external_protocol_id")
        or entry.get("medelement_id")
        or entry.get("source_protocol_external_id")
    )
    if explicit not in (None, ""):
        return str(explicit)
    url = entry.get("protocol_url") or entry.get("source_protocol_url") or entry.get("url")
    if isinstance(url, str):
        match = re.search(r"/(\d+)(?:$|[/?#])", url)
        if match:
            return match.group(1)
    return None


def _source_protocols(context: Any) -> list[dict[str, Any]]:
    if not isinstance(context, list):
        return []

    sources: list[dict[str, Any]] = []
    seen: set[tuple[int | None, str | None]] = set()
    for entry in context:
        if not isinstance(entry, dict):
            continue

        protocol_id = _int_or_none(entry.get("protocol_id") or entry.get("source_protocol_id"))
        protocol_title = entry.get("protocol_title") or entry.get("source_protocol_title") or entry.get("title")
        protocol_title = str(protocol_title) if protocol_title not in (None, "") else None
        if protocol_id is None and protocol_title is None:
            continue

        sections = (
            _str_list(entry.get("protocol_sections"))
            or _str_list(entry.get("medical_sections"))
            or _str_list(entry.get("sections"))
        )
        section = entry.get("section")
        if section not in (None, "") and str(section) not in sections:
            sections.append(str(section))
        category = (
            entry.get("protocol_category")
            or entry.get("category")
            or (sections[0] if sections else None)
        )
        key = (protocol_id, protocol_title)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "protocol_id": protocol_id,
                "protocol_external_id": _external_protocol_id(entry),
                "protocol_title": protocol_title,
                "protocol_year": _int_or_none(entry.get("protocol_year") or entry.get("year")),
                "protocol_version": entry.get("protocol_version") or entry.get("version"),
                "protocol_url": entry.get("protocol_url") or entry.get("source_protocol_url") or entry.get("url"),
                "protocol_category": str(category) if category not in (None, "") else None,
                "protocol_sections": sections,
                "protocol_chunk_count": _int_or_none(entry.get("protocol_chunk_count") or entry.get("chunk_count")),
                "source_fit": entry.get("source_fit"),
                "source_note": entry.get("source_note"),
            }
        )
    return sources


def _protocol_summary(reference_graph: ReferenceGraph | None) -> dict[str, Any]:
    if reference_graph is None:
        return {
            "protocol_id": None,
            "protocol_external_id": None,
            "protocol_title": None,
            "protocol_year": None,
            "protocol_version": None,
            "protocol_url": None,
            "protocol_category": None,
            "protocol_sections": [],
            "source_protocols": [],
        }

    sources = _source_protocols(reference_graph.generation_context)
    first = sources[0] if sources else {}
    return {
        "protocol_id": first.get("protocol_id"),
        "protocol_external_id": first.get("protocol_external_id"),
        "protocol_title": first.get("protocol_title"),
        "protocol_year": first.get("protocol_year"),
        "protocol_version": first.get("protocol_version"),
        "protocol_url": first.get("protocol_url"),
        "protocol_category": first.get("protocol_category"),
        "protocol_sections": first.get("protocol_sections") or [],
        "source_protocols": sources,
    }


def _attempt_score(attempt: StudentAttempt | None) -> float | None:
    if not attempt or not attempt.metrics:
        return None
    value = attempt.metrics.get("composite_score", attempt.metrics.get("f1_score"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _progress_status(progress: StudentAssignmentProgress | None, latest_attempt: StudentAttempt | None = None) -> str:
    if progress and progress.status:
        return progress.status
    if latest_attempt:
        if latest_attempt.review_status == "accepted":
            return "completed"
        if latest_attempt.review_status == "revision_requested":
            return "needs_revision"
        return "submitted"
    return "not_started"


def _reference_public(reference_graph: ReferenceGraph) -> ReferenceGraphPublic:
    protocol = _protocol_summary(reference_graph)
    return ReferenceGraphPublic(
        id=reference_graph.id,
        title=reference_graph.title,
        description=reference_graph.description,
        graph_data=reference_graph.graph_data,
        discipline_id=reference_graph.discipline_id,
        status=_reference_status(reference_graph),
        source_type=reference_graph.source_type,
        generation_context=reference_graph.generation_context,
        generation_quality=reference_graph.generation_quality,
        **protocol,
        validation_warnings=_reference_warnings(reference_graph),
        review_notes=reference_graph.review_notes,
        approved_by_id=reference_graph.approved_by_id,
        approved_at=_iso(reference_graph.approved_at),
    )


def _assignment_public(
    assignment: Assignment,
    targets: list[AssignmentTarget] | None = None,
    creator: User | None = None,
    reference_graph: ReferenceGraph | None = None,
    progress: StudentAssignmentProgress | None = None,
    latest_attempt: StudentAttempt | None = None,
) -> AssignmentPublic:
    protocol = _protocol_summary(reference_graph)
    return AssignmentPublic(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        discipline_id=assignment.discipline_id,
        reference_graph_id=assignment.reference_graph_id,
        created_by_id=assignment.created_by_id,
        created_by_email=creator.email if creator else None,
        created_by_name=creator.full_name if creator else None,
        status=_assignment_status(assignment),
        review_notes=assignment.review_notes,
        approved_by_id=assignment.approved_by_id,
        approved_at=_iso(assignment.approved_at),
        published_at=_iso(assignment.published_at),
        time_limit_minutes=assignment.time_limit_minutes,
        reference_status=_reference_status(reference_graph) if reference_graph else None,
        reference_validation_warnings=_reference_warnings(reference_graph) if reference_graph else [],
        reference_generation_quality=reference_graph.generation_quality if reference_graph else None,
        **protocol,
        targets=[_target_public(target) for target in (targets or [])],
        progress_status=_progress_status(progress, latest_attempt),
        latest_attempt_id=(progress.latest_attempt_id if progress else None) or (latest_attempt.id if latest_attempt else None),
        latest_score=_attempt_score(latest_attempt),
        started_at=_iso(progress.started_at) if progress else None,
        submitted_at=_iso(progress.submitted_at) if progress else None,
        completed_at=_iso(progress.completed_at) if progress else None,
        deadline_at=_iso(progress.deadline_at) if progress else None,
    )


def _attempt_public(attempt: StudentAttempt, assignment: Assignment | None = None, student: User | None = None) -> StudentAttemptPublic:
    created_at = attempt.created_at.isoformat() if attempt.created_at else None
    reviewed_at = attempt.reviewed_at.isoformat() if attempt.reviewed_at else None
    return StudentAttemptPublic(
        id=attempt.id,
        assignment_id=attempt.assignment_id,
        assignment_title=assignment.title if assignment else None,
        assignment_description=assignment.description if assignment else None,
        assignment_time_limit_minutes=assignment.time_limit_minutes if assignment else None,
        reference_graph_id=attempt.reference_graph_id,
        student_id=attempt.student_id,
        student_email=student.email if student else None,
        student_name=student.full_name if student else None,
        submitted_graph=attempt.submitted_graph,
        metrics=attempt.metrics,
        review_status=attempt.review_status,
        teacher_comment=attempt.teacher_comment,
        teacher_score=attempt.teacher_score,
        teacher_rubric=attempt.teacher_rubric,
        reviewed_by_id=attempt.reviewed_by_id,
        reviewed_at=reviewed_at,
        created_at=created_at,
    )


def _snapshot_public(snapshot: EvaluationSnapshot) -> EvaluationSnapshotPublic:
    return EvaluationSnapshotPublic(
        id=snapshot.id,
        attempt_id=snapshot.attempt_id,
        assignment_id=snapshot.assignment_id,
        reference_graph_id=snapshot.reference_graph_id,
        student_id=snapshot.student_id,
        graph_version=snapshot.graph_version,
        submitted_graph=snapshot.submitted_graph,
        metrics=snapshot.metrics,
        recommendations=snapshot.recommendations,
        algorithm_version=snapshot.algorithm_version,
        reference_content_hash=snapshot.reference_content_hash,
        embedding_model_version=snapshot.embedding_model_version,
        created_at=_iso(snapshot.created_at),
    )


def _user_can_access_assignment(user: User, targets: list[AssignmentTarget], assignment: Assignment | None = None) -> bool:
    if user.role in ("teacher", "admin", "expert"):
        return True
    if assignment is not None and _assignment_status(assignment) != "published":
        return False
    if not targets:
        return True
    return any(
        (target.group_id is not None and target.group_id == user.group_id)
        or (target.specialty_id is not None and target.specialty_id == user.specialty_id)
        for target in targets
    )


async def _progress_by_assignment(
    db: DbSession,
    user: User,
    assignment_ids: list[int],
) -> tuple[dict[int, StudentAssignmentProgress], dict[int, StudentAttempt]]:
    if not assignment_ids or user.role != "student":
        return {}, {}

    progress_rows = await db.execute(
        select(StudentAssignmentProgress)
        .where(StudentAssignmentProgress.student_id == user.id)
        .where(StudentAssignmentProgress.assignment_id.in_(assignment_ids))
    )
    progress_map = {row.assignment_id: row for row in progress_rows.scalars().all()}

    attempt_rows = await db.execute(
        select(StudentAttempt)
        .where(StudentAttempt.student_id == user.id)
        .where(StudentAttempt.assignment_id.in_(assignment_ids))
        .order_by(StudentAttempt.created_at.desc(), StudentAttempt.id.desc())
    )
    latest_attempts: dict[int, StudentAttempt] = {}
    for attempt in attempt_rows.scalars().all():
        if attempt.assignment_id is not None and attempt.assignment_id not in latest_attempts:
            latest_attempts[attempt.assignment_id] = attempt
    return progress_map, latest_attempts


def _progress_public(
    progress: StudentAssignmentProgress,
    latest_attempt: StudentAttempt | None = None,
) -> AssignmentProgressPublic:
    return AssignmentProgressPublic(
        assignment_id=progress.assignment_id,
        student_id=progress.student_id,
        status=_progress_status(progress, latest_attempt),
        latest_attempt_id=progress.latest_attempt_id or (latest_attempt.id if latest_attempt else None),
        latest_score=_attempt_score(latest_attempt),
        started_at=_iso(progress.started_at),
        submitted_at=_iso(progress.submitted_at),
        completed_at=_iso(progress.completed_at),
        deadline_at=_iso(progress.deadline_at),
    )


@router.get("/assignments", response_model=AssignmentListResponse)
async def list_assignments(db: DbSession, current_user: CurrentUser) -> AssignmentListResponse:
    await ensure_curriculum_baseline(db)
    repo = AssignmentRepository(db)
    rows = await repo.list_active()
    targets_map = await _targets_by_assignment(db, [row.id for row in rows])
    creator_ids = sorted({row.created_by_id for row in rows if row.created_by_id})
    reference_ids = sorted({row.reference_graph_id for row in rows if row.reference_graph_id})
    creators: dict[int, User] = {}
    references: dict[int, ReferenceGraph] = {}
    if creator_ids:
        creator_rows = await db.execute(select(User).where(User.id.in_(creator_ids)))
        creators = {creator.id: creator for creator in creator_rows.scalars().all()}
    if reference_ids:
        ref_rows = await db.execute(select(ReferenceGraph).where(ReferenceGraph.id.in_(reference_ids)))
        references = {ref.id: ref for ref in ref_rows.scalars().all()}
    progress_map, latest_attempts = await _progress_by_assignment(db, current_user, [row.id for row in rows])
    items = []
    for assignment in rows:
        targets = targets_map.get(assignment.id, [])
        if _user_can_access_assignment(current_user, targets, assignment):
            items.append(
                _assignment_public(
                    assignment,
                    targets,
                    creators.get(assignment.created_by_id),
                    references.get(assignment.reference_graph_id),
                    progress_map.get(assignment.id),
                    latest_attempts.get(assignment.id),
                )
            )
    return AssignmentListResponse(items=items)


@router.get("/assignments/{assignment_id}", response_model=AssignmentPublic)
async def get_assignment(
    assignment_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentPublic:
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    targets = (await _targets_by_assignment(db, [assignment_id])).get(assignment_id, [])
    if not _user_can_access_assignment(current_user, targets, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment is not available for this user")
    creator = await db.get(User, assignment.created_by_id) if assignment.created_by_id else None
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    progress_map, latest_attempts = await _progress_by_assignment(db, current_user, [assignment_id])
    return _assignment_public(
        assignment,
        targets,
        creator,
        reference_graph,
        progress_map.get(assignment_id),
        latest_attempts.get(assignment_id),
    )


@router.post("/assignments/{assignment_id}/start", response_model=AssignmentProgressPublic)
async def start_assignment(
    assignment_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentProgressPublic:
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    targets = (await _targets_by_assignment(db, [assignment_id])).get(assignment_id, [])
    if not _user_can_access_assignment(current_user, targets, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment is not available for this user")
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students can start assigned tasks")

    now = datetime.now(timezone.utc)
    row = await db.execute(
        select(StudentAssignmentProgress)
        .where(StudentAssignmentProgress.assignment_id == assignment_id)
        .where(StudentAssignmentProgress.student_id == current_user.id)
    )
    progress = row.scalars().first()
    if not progress:
        deadline_at = None
        if assignment.time_limit_minutes:
            deadline_at = now + timedelta(minutes=assignment.time_limit_minutes)
        progress = StudentAssignmentProgress(
            assignment_id=assignment_id,
            student_id=current_user.id,
            status="in_progress",
            started_at=now,
            deadline_at=deadline_at,
        )
        db.add(progress)
    elif progress.status in ("not_started", "needs_revision"):
        progress.status = "in_progress"
        progress.started_at = progress.started_at or now
        progress.completed_at = None
        if assignment.time_limit_minutes and not progress.deadline_at:
            progress.deadline_at = (progress.started_at or now) + timedelta(minutes=assignment.time_limit_minutes)

    await db.commit()
    await db.refresh(progress)
    latest_attempt = await db.get(StudentAttempt, progress.latest_attempt_id) if progress.latest_attempt_id else None
    return _progress_public(progress, latest_attempt)


@router.get("/attempts/me", response_model=StudentAttemptListResponse)
async def list_my_attempts(db: DbSession, current_user: CurrentUser) -> StudentAttemptListResponse:
    rows = await db.execute(
        select(StudentAttempt, Assignment)
        .outerjoin(Assignment, Assignment.id == StudentAttempt.assignment_id)
        .where(StudentAttempt.student_id == current_user.id)
        .order_by(StudentAttempt.created_at.desc())
    )
    return StudentAttemptListResponse(
        items=[_attempt_public(attempt, assignment=assignment) for attempt, assignment in rows.all()]
    )


@router.get("/attempts", response_model=StudentAttemptListResponse)
async def list_attempts(db: DbSession, current_user: CurrentUser) -> StudentAttemptListResponse:
    if current_user.role not in ("teacher", "expert", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers, experts and admins can inspect attempts")
    rows = await db.execute(
        select(StudentAttempt, Assignment, User)
        .outerjoin(Assignment, Assignment.id == StudentAttempt.assignment_id)
        .join(User, User.id == StudentAttempt.student_id)
        .order_by(StudentAttempt.created_at.desc())
        .limit(500)
    )
    return StudentAttemptListResponse(
        items=[
            _attempt_public(attempt, assignment=assignment, student=student)
            for attempt, assignment, student in rows.all()
        ]
    )


@router.get("/attempts/{attempt_id}", response_model=StudentAttemptPublic)
async def get_attempt(
    attempt_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentAttemptPublic:
    rows = await db.execute(
        select(StudentAttempt, Assignment, User)
        .outerjoin(Assignment, Assignment.id == StudentAttempt.assignment_id)
        .join(User, User.id == StudentAttempt.student_id)
        .where(StudentAttempt.id == attempt_id)
    )
    row = rows.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    attempt, assignment, student = row
    if current_user.role not in ("teacher", "expert", "admin") and attempt.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Attempt is not available for this user")
    return _attempt_public(attempt, assignment=assignment, student=student)


@router.get("/attempts/{attempt_id}/snapshots", response_model=EvaluationSnapshotListResponse)
async def list_attempt_snapshots(
    attempt_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> EvaluationSnapshotListResponse:
    rows = await db.execute(
        select(StudentAttempt)
        .where(StudentAttempt.id == attempt_id)
    )
    attempt = rows.scalars().first()
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    if current_user.role not in ("teacher", "expert", "admin") and attempt.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Attempt is not available for this user")

    snapshot_query = select(EvaluationSnapshot).where(EvaluationSnapshot.student_id == attempt.student_id)
    if attempt.assignment_id is not None:
        snapshot_query = snapshot_query.where(EvaluationSnapshot.assignment_id == attempt.assignment_id)
    elif attempt.reference_graph_id is not None:
        snapshot_query = snapshot_query.where(EvaluationSnapshot.reference_graph_id == attempt.reference_graph_id)
    else:
        snapshot_query = snapshot_query.where(EvaluationSnapshot.attempt_id == attempt_id)

    snapshot_rows = await db.execute(
        snapshot_query.order_by(
            EvaluationSnapshot.graph_version.asc(),
            EvaluationSnapshot.created_at.asc(),
            EvaluationSnapshot.id.asc(),
        ).limit(200)
    )
    return EvaluationSnapshotListResponse(
        items=[_snapshot_public(snapshot) for snapshot in snapshot_rows.scalars().all()]
    )


@router.patch("/attempts/{attempt_id}/review", response_model=StudentAttemptPublic)
async def review_attempt(
    attempt_id: int,
    payload: StudentAttemptReviewUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentAttemptPublic:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can review attempts")

    rows = await db.execute(
        select(StudentAttempt, Assignment, User)
        .outerjoin(Assignment, Assignment.id == StudentAttempt.assignment_id)
        .join(User, User.id == StudentAttempt.student_id)
        .where(StudentAttempt.id == attempt_id)
    )
    row = rows.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    attempt, assignment, student = row
    attempt.review_status = payload.review_status
    attempt.teacher_comment = payload.teacher_comment
    rubric = payload.teacher_rubric.model_dump(exclude_none=True) if payload.teacher_rubric else None
    teacher_score = payload.teacher_score
    if teacher_score is None and rubric:
        teacher_score = sum(rubric.values()) / len(rubric)
    attempt.teacher_score = teacher_score
    attempt.teacher_rubric = rubric
    attempt.reviewed_by_id = current_user.id
    attempt.reviewed_at = datetime.now(timezone.utc)
    if attempt.assignment_id:
        progress_row = await db.execute(
            select(StudentAssignmentProgress)
            .where(StudentAssignmentProgress.assignment_id == attempt.assignment_id)
            .where(StudentAssignmentProgress.student_id == attempt.student_id)
        )
        progress = progress_row.scalars().first()
        if not progress:
            progress = StudentAssignmentProgress(
                assignment_id=attempt.assignment_id,
                student_id=attempt.student_id,
                started_at=attempt.created_at or attempt.reviewed_at,
                submitted_at=attempt.created_at or attempt.reviewed_at,
            )
            db.add(progress)
        progress.latest_attempt_id = attempt.id
        if payload.review_status == "accepted":
            progress.status = "completed"
            progress.completed_at = attempt.reviewed_at
        elif payload.review_status == "revision_requested":
            progress.status = "needs_revision"
            progress.completed_at = None
        else:
            progress.status = "submitted"
    await db.commit()
    await db.refresh(attempt)
    return _attempt_public(attempt, assignment=assignment, student=student)


@router.get("/assignments/{assignment_id}/attempts", response_model=StudentAttemptListResponse)
async def list_assignment_attempts(
    assignment_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentAttemptListResponse:
    if current_user.role not in ("teacher", "expert", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers, experts and admins can inspect attempts")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    rows = await db.execute(
        select(StudentAttempt, User)
        .join(User, User.id == StudentAttempt.student_id)
        .where(StudentAttempt.assignment_id == assignment_id)
        .order_by(StudentAttempt.created_at.desc())
    )
    return StudentAttemptListResponse(
        items=[
            _attempt_public(attempt, assignment=assignment, student=student)
            for attempt, student in rows.all()
        ]
    )


@router.post("/assignments/{reference_graph_id}/generate", response_model=AssignmentDraftResponse)
async def generate_assignment(
    reference_graph_id: int,
    db: DbSession,
    current_user: UserPublic = Depends(get_current_user)
) -> AssignmentDraftResponse:
    if current_user.role != "teacher" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только преподаватели могут генерировать задания"
        )

    res = await db.execute(select(ReferenceGraph).where(ReferenceGraph.id == reference_graph_id))
    ref = res.scalars().first()
    if not ref:
        raise HTTPException(status_code=404, detail="Эталонный граф не найден.")
    draft = await generate_assignment_with_llm(
        reference_graph_id=reference_graph_id,
        graph_title=ref.title,
        graph_description=ref.description,
        graph_data=ref.graph_data,
    )
    return AssignmentDraftResponse(**draft)


@router.post("/assignments", response_model=AssignmentPublic)
async def create_assignment(
    req: AssignmentCreate,
    db: DbSession,
    current_user: UserPublic = Depends(get_current_user)
) -> AssignmentPublic:
    if current_user.role != "teacher" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только преподаватели могут утверждать задания"
        )

    # Check if reference graph exists
    res = await db.execute(select(ReferenceGraph).where(ReferenceGraph.id == req.reference_graph_id))
    ref = res.scalars().first()
    if not ref:
        raise HTTPException(status_code=404, detail="Эталонный граф не найден.")

    requested_status = "needs_teacher_review" if req.status == "review_ready" else (req.status or "published")
    if requested_status == "published" and _reference_status(ref) not in ("teacher_approved", "published"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reference graph must be teacher-approved before assignment publication.",
        )

    now = datetime.now(timezone.utc)

    assignment = Assignment(
        title=req.title,
        description=req.description,
        discipline_id=req.discipline_id,
        reference_graph_id=req.reference_graph_id,
        created_by_id=current_user.id,
        time_limit_minutes=req.time_limit_minutes,
        status=requested_status,
        approved_by_id=current_user.id if requested_status == "published" else None,
        approved_at=now if requested_status == "published" else None,
        published_at=now if requested_status == "published" else None,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return _assignment_public(assignment, reference_graph=ref)


@router.get("/assignments/{assignment_id}/review-bundle", response_model=AssignmentReviewBundle)
async def get_assignment_review_bundle(
    assignment_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentReviewBundle:
    if current_user.role not in ("teacher", "admin", "expert"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers, experts and admins can inspect draft tasks")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    if not reference_graph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference graph not found")
    targets = (await _targets_by_assignment(db, [assignment.id])).get(assignment.id, [])
    creator = await db.get(User, assignment.created_by_id) if assignment.created_by_id else None
    return AssignmentReviewBundle(
        assignment=_assignment_public(assignment, targets, creator, reference_graph),
        reference_graph=_reference_public(reference_graph),
    )


def _quality_warning_texts(quality: dict) -> list[str]:
    warnings = quality.get("warnings") or []
    return [format_quality_warning(item) for item in warnings]


def _validate_reference_graph_for_teacher_decision(
    reference_graph: ReferenceGraph,
    *,
    force: bool,
    documented_reason: str | None = None,
) -> dict:
    if not reference_graph.graph_data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reference graph is empty")

    try:
        graph = GraphSchema.model_validate(reference_graph.graph_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Reference graph schema is invalid: {exc}")

    quality = judge_reference_graph(graph)
    reference_graph.generation_quality = quality
    reference_graph.validation_warnings = _quality_warning_texts(quality)
    if quality.get("critical_count", 0) > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Reference graph has critical clinical warnings. Review or approve with force after documented expert decision.",
                "warnings": reference_graph.validation_warnings,
            },
        )
    if quality.get("critical_count", 0) > 0 and force and not str(documented_reason or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "A documented clinical justification is required to override critical reference-graph warnings.",
                "warnings": reference_graph.validation_warnings,
            },
        )
    return quality


@router.patch("/assignments/{assignment_id}/draft", response_model=AssignmentReviewBundle)
async def update_assignment_draft(
    assignment_id: int,
    payload: AssignmentDraftUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentReviewBundle:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can edit draft tasks")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    if not reference_graph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference graph not found")

    if payload.title is not None:
        assignment.title = payload.title.strip()
        reference_graph.title = payload.title.strip()
    if payload.description is not None:
        assignment.description = payload.description
        reference_graph.description = payload.description
    if payload.time_limit_minutes is not None:
        assignment.time_limit_minutes = payload.time_limit_minutes
    if payload.review_notes is not None:
        assignment.review_notes = payload.review_notes
        reference_graph.review_notes = payload.review_notes
    if payload.status is not None and payload.status != "published":
        normalized_status = "needs_teacher_review" if payload.status == "review_ready" else payload.status
        if normalized_status == "teacher_approved":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Use the approve-reference endpoint to confirm a reference graph.",
            )
        assignment.status = normalized_status
        if normalized_status in ("ai_generated", "needs_teacher_review", "draft", "archived"):
            reference_graph.status = normalized_status
    if payload.graph_data is not None:
        reference_graph.graph_data = payload.graph_data.model_dump()
        quality = judge_reference_graph(payload.graph_data)
        reference_graph.generation_quality = quality
        reference_graph.validation_warnings = _quality_warning_texts(quality)
        reference_graph.status = "needs_teacher_review" if quality.get("critical_count", 0) == 0 else "draft"
        assignment.status = "needs_teacher_review" if quality.get("critical_count", 0) == 0 else "draft"

    await db.commit()
    await db.refresh(assignment)
    await db.refresh(reference_graph)
    targets = (await _targets_by_assignment(db, [assignment.id])).get(assignment.id, [])
    creator = await db.get(User, assignment.created_by_id) if assignment.created_by_id else None
    return AssignmentReviewBundle(
        assignment=_assignment_public(assignment, targets, creator, reference_graph),
        reference_graph=_reference_public(reference_graph),
    )


@router.post("/assignments/{assignment_id}/approve-reference", response_model=AssignmentReviewBundle)
async def approve_assignment_reference(
    assignment_id: int,
    payload: AssignmentApproveReferenceRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentReviewBundle:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can approve reference graphs")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    if not reference_graph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference graph not found")

    _validate_reference_graph_for_teacher_decision(
        reference_graph,
        force=payload.force,
        documented_reason=payload.review_notes if payload.review_notes is not None else assignment.review_notes,
    )

    now = datetime.now(timezone.utc)
    assignment.status = "teacher_approved"
    assignment.review_notes = payload.review_notes if payload.review_notes is not None else assignment.review_notes
    assignment.approved_by_id = current_user.id
    assignment.approved_at = now
    assignment.published_at = None
    reference_graph.status = "teacher_approved"
    reference_graph.review_notes = payload.review_notes if payload.review_notes is not None else reference_graph.review_notes
    reference_graph.approved_by_id = current_user.id
    reference_graph.approved_at = now

    await db.commit()
    await db.refresh(assignment)
    await db.refresh(reference_graph)
    targets = (await _targets_by_assignment(db, [assignment.id])).get(assignment.id, [])
    creator = await db.get(User, assignment.created_by_id) if assignment.created_by_id else None
    return AssignmentReviewBundle(
        assignment=_assignment_public(assignment, targets, creator, reference_graph),
        reference_graph=_reference_public(reference_graph),
    )


@router.post("/assignments/{assignment_id}/publish", response_model=AssignmentReviewBundle)
async def publish_assignment(
    assignment_id: int,
    payload: AssignmentPublishRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentReviewBundle:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can publish tasks")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    if not reference_graph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference graph not found")

    reference_status = _reference_status(reference_graph)
    if reference_status not in ("teacher_approved", "published"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Reference graph must be teacher-approved before publication.",
                "warnings": reference_graph.validation_warnings or [],
            },
        )

    _validate_reference_graph_for_teacher_decision(
        reference_graph,
        force=payload.force,
        documented_reason=payload.review_notes if payload.review_notes is not None else assignment.review_notes,
    )
    if (reference_graph.generation_quality or {}).get("critical_count", 0) > 0 and not payload.force:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Reference graph has critical clinical warnings. Review or publish with force after documented expert decision.",
                "warnings": reference_graph.validation_warnings,
            },
        )

    now = datetime.now(timezone.utc)
    assignment.status = "published"
    assignment.review_notes = payload.review_notes if payload.review_notes is not None else assignment.review_notes
    assignment.approved_by_id = current_user.id
    assignment.approved_at = now
    assignment.published_at = now
    reference_graph.status = "published"
    reference_graph.review_notes = payload.review_notes if payload.review_notes is not None else reference_graph.review_notes
    reference_graph.approved_by_id = current_user.id
    reference_graph.approved_at = now

    await db.commit()
    await db.refresh(assignment)
    await db.refresh(reference_graph)
    targets = (await _targets_by_assignment(db, [assignment.id])).get(assignment.id, [])
    creator = await db.get(User, assignment.created_by_id) if assignment.created_by_id else None
    return AssignmentReviewBundle(
        assignment=_assignment_public(assignment, targets, creator, reference_graph),
        reference_graph=_reference_public(reference_graph),
    )


@router.put("/assignments/{assignment_id}/targets", response_model=AssignmentPublic)
async def update_assignment_targets(
    assignment_id: int,
    req: AssignmentTargetsUpdate,
    db: DbSession,
    current_user: UserPublic = Depends(get_current_user),
) -> AssignmentPublic:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can assign tasks")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    existing = await db.execute(select(AssignmentTarget).where(AssignmentTarget.assignment_id == assignment_id))
    for target in existing.scalars().all():
        await db.delete(target)

    for specialty_id in sorted(set(req.specialty_ids)):
        db.add(AssignmentTarget(assignment_id=assignment_id, specialty_id=specialty_id))
    for group_id in sorted(set(req.group_ids)):
        db.add(AssignmentTarget(assignment_id=assignment_id, group_id=group_id))

    await db.commit()
    await db.refresh(assignment)
    targets = (await _targets_by_assignment(db, [assignment.id])).get(assignment.id, [])
    reference_graph = await db.get(ReferenceGraph, assignment.reference_graph_id)
    return _assignment_public(assignment, targets, reference_graph=reference_graph)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: int,
    db: DbSession,
    current_user: UserPublic = Depends(get_current_user),
) -> None:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and admins can delete tasks")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    await db.delete(assignment)
    await db.commit()


@router.get("/assignments/{assignment_id}/reference")
async def get_reference_graph(assignment_id: int, db: DbSession, current_user: CurrentUser):
    targets = (await _targets_by_assignment(db, [assignment_id])).get(assignment_id, [])
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if not _user_can_access_assignment(current_user, targets, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment is not available for this user")
    res = await db.execute(
        select(ReferenceGraph)
        .join(Assignment, Assignment.reference_graph_id == ReferenceGraph.id)
        .where(Assignment.id == assignment_id)
    )
    ref = res.scalars().first()
    if not ref:
        raise HTTPException(status_code=404, detail="Эталонный граф не найден.")
    return ref.graph_data

@router.get("/assignments/{assignment_id}/initial-nodes")
async def get_initial_nodes(assignment_id: int, db: DbSession, current_user: CurrentUser):
    targets = (await _targets_by_assignment(db, [assignment_id])).get(assignment_id, [])
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if not _user_can_access_assignment(current_user, targets, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment is not available for this user")
    res = await db.execute(
        select(ReferenceGraph)
        .join(Assignment, Assignment.reference_graph_id == ReferenceGraph.id)
        .where(Assignment.id == assignment_id)
    )
    ref = res.scalars().first()
    if not ref:
        raise HTTPException(status_code=404, detail="Эталонный граф не найден.")

    graph_data = ref.graph_data
    if not graph_data or not isinstance(graph_data, dict):
        return []

    nodes = graph_data.get("nodes", [])
    initial_nodes = []

    # Filter only PATIENT_PROFILE and SYMPTOM
    allowed_categories = {"PATIENT_PROFILE", "SYMPTOM"}
    for node in nodes:
        node_data = node.get("data", {})
        category = node_data.get("category", "").upper().strip()
        if category in allowed_categories:
            initial_nodes.append(node)

    return initial_nodes


@router.get("/assignments/{assignment_id}/palette")
async def get_assignment_palette(
    assignment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    per_category: int = Query(24, ge=1, le=80),
) -> dict:
    targets = (await _targets_by_assignment(db, [assignment_id])).get(assignment_id, [])
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if not _user_can_access_assignment(current_user, targets, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment is not available for this user")

    res = await db.execute(
        select(ReferenceGraph)
        .join(Assignment, Assignment.reference_graph_id == ReferenceGraph.id)
        .where(Assignment.id == assignment_id)
    )
    ref = res.scalars().first()
    if not ref:
        raise HTTPException(status_code=404, detail="Эталонный граф не найден.")

    return await build_assignment_palette(db, assignment, ref, per_category=per_category)


@router.post("/assignments/from-rag", response_model=AssignmentPublic)
async def create_assignment_from_rag(
    req: AssignmentFromRagRequest,
    db: DbSession,
    current_user: UserPublic = Depends(get_current_user)
) -> AssignmentPublic:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Только преподаватели могут создавать задания")

    # Get or create General Medicine discipline
    res = await db.execute(select(Discipline).where(Discipline.name == "Общая медицина"))
    discipline = res.scalars().first()
    if not discipline:
        discipline = Discipline(name="Общая медицина", code="GM01")
        db.add(discipline)
        await db.commit()
        await db.refresh(discipline)

    quality = judge_reference_graph(req.graph_data)

    # Create ReferenceGraph
    ref_graph = ReferenceGraph(
        title=req.title,
        description=req.description,
        graph_data=req.graph_data.model_dump(),
        discipline_id=discipline.id,
        status="ai_generated",
        source_type="rag_generated",
        generation_context=req.generation_context,
        generation_quality=quality,
        validation_warnings=[*req.validation_warnings, *_quality_warning_texts(quality)],
    )
    db.add(ref_graph)
    await db.commit()
    await db.refresh(ref_graph)

    # Create Assignment
    assignment = Assignment(
        title=req.title,
        description=req.description,
        discipline_id=discipline.id,
        reference_graph_id=ref_graph.id,
        created_by_id=current_user.id,
        time_limit_minutes=req.time_limit_minutes,
        status="needs_teacher_review" if quality.get("critical_count", 0) == 0 else "draft",
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return _assignment_public(assignment, reference_graph=ref_graph)
