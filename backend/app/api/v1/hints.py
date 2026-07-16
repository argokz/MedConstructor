from fastapi import APIRouter

from app.api.deps import DbSession, OptionalUser, SettingsDep
from app.schemas import GraphHintsRequest, GraphHintsResponse, GraphFeedbackResponse
from app.services.hints_service import generate_graph_hints, generate_graph_feedback

router = APIRouter(tags=["hints"])


@router.post("/graph/hints", response_model=GraphHintsResponse)
async def graph_hints(
    body: GraphHintsRequest,
    db: DbSession,
    settings: SettingsDep,
    _user: OptionalUser,
) -> GraphHintsResponse:
    _ = db  # reserved for future: load assignment / rate limits
    return await generate_graph_hints(body, settings)

@router.post("/graph/feedback", response_model=GraphFeedbackResponse)
async def graph_feedback(
    body: GraphHintsRequest,
    db: DbSession,
    settings: SettingsDep,
    _user: OptionalUser,
) -> GraphFeedbackResponse:
    _ = db
    return await generate_graph_feedback(body, settings)
