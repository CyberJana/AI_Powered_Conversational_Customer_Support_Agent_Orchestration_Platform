"""AICSP FastAPI application entrypoint."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

settings = get_settings()

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI Customer Support & Secure Agent Platform API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe. Checks DB connectivity."""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:  # noqa: BLE001
        db_status = "error"
    return {"status": "ok", "database": db_status}


def _include_routers() -> None:
    from app.api.v1 import (
        agents as agents_router,
        analytics as analytics_router,
        auth as auth_router,
        chat as chat_router,
        conversations as conversations_router,
        escalations as escalations_router,
        evaluations as evaluations_router,
        knowledge_base as kb_router,
        security as security_router,
        tools as tools_router,
    )

    app.include_router(auth_router.router, prefix=settings.api_v1_prefix + "/auth", tags=["auth"])
    app.include_router(chat_router.router, prefix=settings.api_v1_prefix, tags=["chat"])
    app.include_router(conversations_router.router, prefix=settings.api_v1_prefix, tags=["conversations"])
    app.include_router(kb_router.router, prefix=settings.api_v1_prefix, tags=["knowledge-base"])
    app.include_router(agents_router.router, prefix=settings.api_v1_prefix, tags=["agents"])
    app.include_router(tools_router.router, prefix=settings.api_v1_prefix, tags=["tools"])
    app.include_router(escalations_router.router, prefix=settings.api_v1_prefix, tags=["escalations"])
    app.include_router(evaluations_router.router, prefix=settings.api_v1_prefix, tags=["evaluations"])
    app.include_router(security_router.router, prefix=settings.api_v1_prefix, tags=["security"])
    app.include_router(analytics_router.router, prefix=settings.api_v1_prefix, tags=["analytics"])


_include_routers()
