from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, OptionalUser, SettingsDep
from app.schemas import GraphEvaluationRequest, GraphEvaluationResponse
from app.services.evaluation_service import EvaluationService

router = APIRouter(tags=["evaluation"])


@router.post("/evaluate", response_model=GraphEvaluationResponse)
async def evaluate_graph(
    payload: GraphEvaluationRequest,
    db: DbSession,
    settings: SettingsDep,
    user: OptionalUser,
) -> GraphEvaluationResponse:
    student_id = user.id if user else payload.student_id
    if not student_id:
        raise HTTPException(
            status_code=422,
            detail="Provide numeric student_id or authenticate with a Bearer token.",
        )
    merged = payload.model_copy(update={"student_id": student_id})
    service = EvaluationService(db, settings)
    return await service.evaluate(merged)
