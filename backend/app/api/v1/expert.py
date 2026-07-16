from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import (
    Assignment,
    ExpertReview,
    ReferenceGraph,
    StudentAttempt,
    User,
    ValidationRating,
    ValidationVariant,
)
from app.schemas import (
    ExpertReviewItem,
    ExpertReviewItemListResponse,
    ExpertReviewListResponse,
    ExpertReviewPublic,
    ExpertReviewUpsert,
    ValidationItemsResponse,
    ValidationRatingPublic,
    ValidationRatingUpsert,
    ValidationVariantBlinded,
)

router = APIRouter(prefix="/expert", tags=["expert-review"])


def _require_reviewer(user: CurrentUser) -> None:
    if user.role not in ("expert", "teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only experts, teachers and admins can use the expert review workspace.",
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _review_public(review: ExpertReview, reviewer: User | None = None) -> ExpertReviewPublic:
    tags = review.issue_tags or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return ExpertReviewPublic(
        id=review.id,
        reviewer_id=review.reviewer_id,
        reviewer_email=reviewer.email if reviewer else None,
        reviewer_name=reviewer.full_name if reviewer else None,
        item_type=review.item_type,
        item_id=review.item_id,
        assignment_id=review.assignment_id,
        reference_graph_id=review.reference_graph_id,
        student_attempt_id=review.student_attempt_id,
        score=review.score,
        step_scores=review.step_scores,
        issue_tags=[str(item) for item in tags],
        comment=review.comment,
        recommendation=review.recommendation,
        status=review.status or "submitted",
        created_at=_iso(review.created_at),
        updated_at=_iso(review.updated_at),
    )


async def _reviews_for_user(db: DbSession, user_id: int) -> dict[tuple[str, int], ExpertReviewPublic]:
    rows = await db.execute(select(ExpertReview).where(ExpertReview.reviewer_id == user_id))
    return {
        (row.item_type, row.item_id): _review_public(row)
        for row in rows.scalars().all()
    }


def _reference_warnings(reference_graph: ReferenceGraph | None) -> list[str]:
    if not reference_graph:
        return []
    warnings = reference_graph.validation_warnings or []
    if isinstance(warnings, list):
        return [str(item) for item in warnings]
    return [str(warnings)]


@router.get("/items", response_model=ExpertReviewItemListResponse)
async def list_expert_review_items(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 200,
) -> ExpertReviewItemListResponse:
    _require_reviewer(current_user)
    existing = await _reviews_for_user(db, current_user.id)
    items: list[ExpertReviewItem] = []

    attempt_rows = await db.execute(
        select(StudentAttempt, Assignment, User, ReferenceGraph)
        .outerjoin(Assignment, Assignment.id == StudentAttempt.assignment_id)
        .join(User, User.id == StudentAttempt.student_id)
        .outerjoin(ReferenceGraph, ReferenceGraph.id == StudentAttempt.reference_graph_id)
        .order_by(StudentAttempt.created_at.desc())
        .limit(limit)
    )
    for attempt, assignment, student, reference_graph in attempt_rows.all():
        title = assignment.title if assignment else f"Student attempt #{attempt.id}"
        items.append(
            ExpertReviewItem(
                item_type="student_attempt",
                item_id=attempt.id,
                title=title,
                status=attempt.review_status or "needs_review",
                assignment_id=attempt.assignment_id,
                assignment_title=assignment.title if assignment else None,
                reference_graph_id=attempt.reference_graph_id,
                student_attempt_id=attempt.id,
                student_id=attempt.student_id,
                student_email=student.email,
                student_name=student.full_name,
                reference_graph=reference_graph.graph_data if reference_graph else None,
                student_graph=attempt.submitted_graph or attempt.student_graph,
                metrics=attempt.metrics,
                validation_warnings=_reference_warnings(reference_graph),
                generation_quality=reference_graph.generation_quality if reference_graph else None,
                existing_review=existing.get(("student_attempt", attempt.id)),
            )
        )

    assignment_rows = await db.execute(
        select(Assignment, ReferenceGraph)
        .join(ReferenceGraph, ReferenceGraph.id == Assignment.reference_graph_id)
        .order_by(Assignment.created_at.desc())
        .limit(limit)
    )
    for assignment, reference_graph in assignment_rows.all():
        items.append(
            ExpertReviewItem(
                item_type="assignment",
                item_id=assignment.id,
                title=assignment.title,
                status=assignment.status or "published",
                assignment_id=assignment.id,
                assignment_title=assignment.title,
                reference_graph_id=reference_graph.id,
                reference_graph=reference_graph.graph_data,
                validation_warnings=_reference_warnings(reference_graph),
                generation_quality=reference_graph.generation_quality,
                existing_review=existing.get(("assignment", assignment.id)),
            )
        )
        items.append(
            ExpertReviewItem(
                item_type="reference_graph",
                item_id=reference_graph.id,
                title=reference_graph.title,
                status=reference_graph.status or "teacher_approved",
                assignment_id=assignment.id,
                assignment_title=assignment.title,
                reference_graph_id=reference_graph.id,
                reference_graph=reference_graph.graph_data,
                validation_warnings=_reference_warnings(reference_graph),
                generation_quality=reference_graph.generation_quality,
                existing_review=existing.get(("reference_graph", reference_graph.id)),
            )
        )

    return ExpertReviewItemListResponse(items=items)


@router.get("/reviews", response_model=ExpertReviewListResponse)
async def list_expert_reviews(
    db: DbSession,
    current_user: CurrentUser,
) -> ExpertReviewListResponse:
    _require_reviewer(current_user)
    query = select(ExpertReview, User).join(User, User.id == ExpertReview.reviewer_id)
    if current_user.role == "expert":
        query = query.where(ExpertReview.reviewer_id == current_user.id)
    query = query.order_by(ExpertReview.updated_at.desc())
    rows = await db.execute(query)
    return ExpertReviewListResponse(
        items=[_review_public(review, reviewer) for review, reviewer in rows.all()]
    )


async def _resolve_review_target(
    db: DbSession,
    item_type: str,
    item_id: int,
) -> tuple[int | None, int | None, int | None]:
    if item_type == "student_attempt":
        attempt = await db.get(StudentAttempt, item_id)
        if not attempt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student attempt not found")
        return attempt.assignment_id, attempt.reference_graph_id, attempt.id
    if item_type == "reference_graph":
        reference_graph = await db.get(ReferenceGraph, item_id)
        if not reference_graph:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference graph not found")
        row = await db.execute(select(Assignment).where(Assignment.reference_graph_id == item_id).limit(1))
        assignment = row.scalars().first()
        return assignment.id if assignment else None, reference_graph.id, None
    if item_type == "assignment":
        assignment = await db.get(Assignment, item_id)
        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        return assignment.id, assignment.reference_graph_id, None
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported expert review item type")


@router.post("/reviews", response_model=ExpertReviewPublic)
async def upsert_expert_review(
    payload: ExpertReviewUpsert,
    db: DbSession,
    current_user: CurrentUser,
) -> ExpertReviewPublic:
    _require_reviewer(current_user)
    assignment_id, reference_graph_id, attempt_id = await _resolve_review_target(
        db,
        payload.item_type,
        payload.item_id,
    )
    existing = await db.execute(
        select(ExpertReview).where(
            ExpertReview.reviewer_id == current_user.id,
            ExpertReview.item_type == payload.item_type,
            ExpertReview.item_id == payload.item_id,
        )
    )
    review = existing.scalars().first()
    if not review:
        review = ExpertReview(
            reviewer_id=current_user.id,
            item_type=payload.item_type,
            item_id=payload.item_id,
        )
        db.add(review)

    review.assignment_id = assignment_id
    review.reference_graph_id = reference_graph_id
    review.student_attempt_id = attempt_id
    review.score = payload.score
    review.step_scores = payload.step_scores
    review.issue_tags = payload.issue_tags
    review.comment = payload.comment
    review.recommendation = payload.recommendation
    review.status = payload.status

    await db.commit()
    await db.refresh(review)
    return _review_public(review, current_user)


# --- Blinded expert validation study (in-system variant rating) ---

def _rating_public(variant: ValidationVariant, rating: ValidationRating | None) -> ValidationRatingPublic | None:
    if not rating:
        return None
    return ValidationRatingPublic(
        review_item_id=variant.review_item_id,
        score=rating.score,
        accept=rating.accept,
        confidence=rating.confidence,
        comment=rating.comment,
        status=rating.status or "submitted",
        updated_at=_iso(rating.updated_at),
    )


@router.get("/validation/items", response_model=ValidationItemsResponse)
async def list_validation_items(
    db: DbSession,
    current_user: CurrentUser,
    cohort: str = "cardiology_pilot_v2",
) -> ValidationItemsResponse:
    """Blinded variants for the current expert. Never exposes the expected error
    pattern or model metrics, so the rating stays an independent expert judgement."""
    _require_reviewer(current_user)

    variant_rows = await db.execute(
        select(ValidationVariant)
        .where(ValidationVariant.cohort == cohort, ValidationVariant.is_active == 1)
        .order_by(ValidationVariant.display_order.asc().nulls_last(), ValidationVariant.id.asc())
    )
    variants = variant_rows.scalars().all()

    rating_rows = await db.execute(
        select(ValidationRating).where(ValidationRating.expert_id == current_user.id)
    )
    ratings_by_variant = {row.variant_id: row for row in rating_rows.scalars().all()}

    items: list[ValidationVariantBlinded] = []
    rated = 0
    for variant in variants:
        rating = ratings_by_variant.get(variant.id)
        if rating is not None and rating.score is not None:
            rated += 1
        items.append(
            ValidationVariantBlinded(
                review_item_id=variant.review_item_id,
                case_title=variant.case_title,
                case_prompt=variant.case_prompt,
                graph_under_review=variant.graph_under_review,
                student_graph=variant.student_graph,
                display_order=variant.display_order,
                my_rating=_rating_public(variant, rating),
            )
        )

    return ValidationItemsResponse(
        cohort=cohort,
        total=len(variants),
        rated=rated,
        items=items,
    )


@router.post("/validation/ratings", response_model=ValidationRatingPublic)
async def upsert_validation_rating(
    payload: ValidationRatingUpsert,
    db: DbSession,
    current_user: CurrentUser,
) -> ValidationRatingPublic:
    _require_reviewer(current_user)

    variant_row = await db.execute(
        select(ValidationVariant).where(ValidationVariant.review_item_id == payload.review_item_id)
    )
    variant = variant_row.scalars().first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation variant not found")

    existing = await db.execute(
        select(ValidationRating).where(
            ValidationRating.variant_id == variant.id,
            ValidationRating.expert_id == current_user.id,
        )
    )
    rating = existing.scalars().first()
    if not rating:
        rating = ValidationRating(variant_id=variant.id, expert_id=current_user.id)
        db.add(rating)

    rating.score = payload.score
    rating.accept = payload.accept
    rating.confidence = payload.confidence
    rating.comment = payload.comment
    rating.status = payload.status

    await db.commit()
    await db.refresh(rating)
    return _rating_public(variant, rating)
