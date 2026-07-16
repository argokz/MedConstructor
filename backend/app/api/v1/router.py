from fastapi import APIRouter

from app.api.v1 import admin, assignments, auth, benchmarks, concepts, evaluate, expert, health, hints, rag, protocols

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(assignments.router)
api_router.include_router(expert.router)
api_router.include_router(hints.router)
api_router.include_router(evaluate.router)
api_router.include_router(concepts.router)
api_router.include_router(rag.router)
api_router.include_router(protocols.router)
api_router.include_router(benchmarks.router)
