from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.admin import router as admin_router
from app.api.routers.content import router as content_router
from app.api.routers.health import router as health_router
from app.api.routers.me import router as me_router
from app.api.routers.modules import router as modules_router
from app.api.routers.student_summaries import router as student_summaries_router
from app.api.routers.transcripts import router as transcripts_router
from app.platform.config import settings
from app.platform.faults.boot import assert_fault_injection_safe


def create_app() -> FastAPI:
    # Refuse to boot if a fault-injection flag is active in a hosted env (Stage 4.8 §8).
    assert_fault_injection_safe()
    app = FastAPI(title="XYZ LMS")
    # Stage 4.9e §7.2: auth is pure Bearer (rule 4) — credentials are never sent cross-origin, so
    # allow_credentials is dropped (needless surface area; it also forbids wildcards for no benefit).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(admin_router)
    app.include_router(content_router)
    app.include_router(modules_router)
    app.include_router(transcripts_router)
    app.include_router(student_summaries_router)
    # Stage 4.8c (C1): the SSE probe route exists ONLY when explicitly enabled (404 otherwise).
    if settings.ENABLE_INTERNAL_SSE_PROBE:
        from app.api.routers.sse_probe import router as sse_probe_router

        app.include_router(sse_probe_router)
    return app


app = create_app()
