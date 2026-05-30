from fastapi import FastAPI

from app.api.routers.admin import router as admin_router
from app.api.routers.health import router as health_router
from app.api.routers.modules import router as modules_router


def create_app() -> FastAPI:
    app = FastAPI(title="XYZ LMS")
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(modules_router)
    return app


app = create_app()
