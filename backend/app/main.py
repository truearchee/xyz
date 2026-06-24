from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers.analytics import router as analytics_router
from app.api.routers.admin import router as admin_router
from app.api.routers.assessments import router as assessments_router
from app.api.routers.assistant import router as assistant_router
from app.api.routers.content import router as content_router
from app.api.routers.gamification import router as gamification_router
from app.api.routers.glossary import router as glossary_router
from app.api.routers.health import router as health_router
from app.api.routers.me import router as me_router
from app.api.routers.modules import router as modules_router
from app.api.routers.progress import router as progress_router
from app.api.routers.quiz import router as quiz_router
from app.api.routers.student_summaries import router as student_summaries_router
from app.api.routers.transcripts import router as transcripts_router
from app.platform.config import settings
from app.platform.http.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.platform.http.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="XYZ LMS")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Outermost user middleware: stamp every request with a correlation id and echo
    # X-Request-ID on every response (Stage 12a).
    app.add_middleware(RequestIdMiddleware)
    # Consistent error envelope + no raw default 500 bodies (Stage 12a). Registering the
    # Starlette base catches FastAPI's HTTPException subclass too; the Exception handler is
    # the catch-all 500.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(admin_router)
    app.include_router(content_router)
    app.include_router(modules_router)
    app.include_router(transcripts_router)
    app.include_router(student_summaries_router)
    app.include_router(quiz_router)
    app.include_router(assessments_router)
    app.include_router(glossary_router)
    app.include_router(assistant_router)
    app.include_router(progress_router)
    app.include_router(gamification_router)
    app.include_router(analytics_router)
    return app


app = create_app()
