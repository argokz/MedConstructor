from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)
settings = get_settings()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        if settings.enable_structlog:
            try:
                import structlog

                structlog.contextvars.bind_contextvars(request_id=request_id)
            except Exception:  # pragma: no cover
                pass
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            if settings.enable_structlog:
                try:
                    import structlog

                    structlog.contextvars.unbind_contextvars("request_id")
                except Exception:  # pragma: no cover
                    pass
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_completed request_id=%s path=%s method=%s duration_ms=%s",
            request_id,
            request.url.path,
            request.method,
            round(duration_ms, 2),
        )
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


configure_logging(settings.enable_structlog)

app = FastAPI(title="Medical Clinical Reasoning", lifespan=lifespan)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

if settings.enable_prometheus:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/api/v1/metrics", include_in_schema=False)
    except Exception as exc:  # pragma: no cover
        logger.warning("Prometheus instrumentation skipped: %s", exc)

@app.exception_handler(HTTPException)
async def http_problem_details(request: Request, exc: HTTPException):
    """Единый JSON для ошибок API (удобно фронту и логам)."""
    rid = getattr(request.state, "request_id", None)
    body = {
        "title": "Request failed",
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": str(request.url.path),
    }
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=exc.status_code, content=body)


if settings.enable_otel:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry FastAPI instrumentation enabled")
    except ImportError:
        logger.warning(
            "ENABLE_OTEL is true but OpenTelemetry packages are not installed; "
            "pip install opentelemetry-instrumentation-fastapi opentelemetry-sdk opentelemetry-exporter-otlp"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("OpenTelemetry instrumentation skipped: %s", exc)
