"""
Fraud Detection Platform — Production-grade FastAPI application.

Layers:
1. Raw transaction and authorization events
2. Customer, card, merchant, device, and account dimensions
3. Point-in-time feature store for online and offline ML
4. Real-time decision and rule/model score storage
5. Fraud case, label, dispute, and chargeback lifecycle
6. Model governance, evaluation, drift, and auditability
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from src.api.middleware.rate_limit import RateLimitMiddleware
from src.core.config import get_settings
from src.core.database import init_db, shutdown_db
from src.core.logging import setup_logging
from src.core.secrets import inject_secrets
from src.services.observability.telemetry import setup_telemetry
from src.api.routes import authorize, cases, features, graph, feedback, model, dashboard, ui, replay, economics, governance, observability

inject_secrets()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    setup_telemetry(app)
    yield
    await shutdown_db()


settings = get_settings()

app = FastAPI(
    title="Fraud Detection Platform",
    description=(
        "FAANG-grade fraud decisioning platform with real-time scoring, "
        "graph intelligence, investigator copilot, model governance, "
        "and immutable auditability."
    ),
    version="2.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(authorize.router)
app.include_router(cases.router)
app.include_router(features.router)
app.include_router(replay.replay_router)
app.include_router(replay.parity_router)
app.include_router(graph.router)
app.include_router(feedback.router)
app.include_router(model.router)
app.include_router(economics.router)
app.include_router(governance.router)
app.include_router(observability.router)
app.include_router(dashboard.router)
app.include_router(ui.router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "fraud-detection-platform",
        "version": "2.0.0",
    }


@app.get("/")
async def root():
    return {
        "service": "Fraud Detection Platform",
        "version": "2.0.0",
        "endpoints": {
            "ui": "/ui/",
            "scoring": "/authorize/score",
            "cases": "/case/create, /case/review, /case/{id}/investigate",
            "features": "/features/get/{id}, /features/compute",
            "graph": "/graph/risk, /graph/rings, /graph/expand/{id}",
            "feedback": "/feedback/label, /feedback/chargeback",
            "governance": "/model/register, /model/promote, /model/evaluate",
            "dashboard": "/dashboard/transaction/{id}, /dashboard/ops/summary",
            "health": "/health",
            "docs": "/docs",
        },
    }
