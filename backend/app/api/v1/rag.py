import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas import (
    UserPublic,
    ClinicalTaskGenerateRequest,
    ClinicalTaskResponse,
    StudentAnswerRequest,
    ValidationResponse,
    RagAskRequest,
    RagAskResponse,
    RagScenariosRequest,
    RagScenariosResponse,
    RagGraphGenerateRequest,
    RagGraphGenerateResponse,
)
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/search")
async def search_protocols(query: str, limit: int = 5, db: AsyncSession = Depends(get_db)):
    """Семантический поиск по медицинским протоколам МЗ РК."""
    service = RAGService(db)
    rows = await service.retrieve_chunks(query, limit=limit)

    return [
        {
            "chunk_id": chunk.id,
            "protocol_id": chunk.protocol_id,
            "protocol_title": title,
            "text": chunk.text_content,
        }
        for chunk, title in rows
    ]


@router.post("/tasks", response_model=ClinicalTaskResponse)
async def generate_task(
    req: ClinicalTaskGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers can generate tasks")

    service = RAGService(db)
    try:
        task = await service.generate_clinical_task(req.protocol_id)
        return task
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/validate", response_model=ValidationResponse)
async def validate_answer(
    task_id: int,
    req: StudentAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    service = RAGService(db)
    try:
        attempt = await service.validate_student_answer(task_id, current_user.id, req.student_answer)
        return {
            "id": attempt.id,
            "task_id": attempt.task_id,
            "score": attempt.score,
            "validation_result": attempt.validation_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask", response_model=RagAskResponse)
async def ask_question(req: RagAskRequest, db: AsyncSession = Depends(get_db)):
    """RAG Chat Q&A с двухэтапным retrieval."""
    service = RAGService(db)
    try:
        return await service.ask_question(req.question, req.protocol_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask/stream")
async def ask_question_stream(req: RagAskRequest, db: AsyncSession = Depends(get_db)):
    """SSE-поток ответа RAG."""
    service = RAGService(db)

    async def event_generator():
        try:
            async for event in service.ask_question_stream(req.question, req.protocol_id):
                yield f"data: {event}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/scenarios", response_model=RagScenariosResponse)
async def generate_scenarios(
    req: RagScenariosRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers can generate scenarios")

    service = RAGService(db)
    try:
        scenarios = await service.generate_scenarios(req.protocol_ids)
        return {"scenarios": scenarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reference-graph", response_model=RagGraphGenerateResponse)
async def generate_reference_graph(
    req: RagGraphGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers can generate reference graphs")

    service = RAGService(db)
    try:
        result = await service.generate_reference_graph(
            req.protocol_ids,
            req.scenario_title,
            req.scenario_description,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
