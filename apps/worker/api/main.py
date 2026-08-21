"""FastAPI 엔트리포인트.

실행: uvicorn apps.worker.api.main:app --reload --port 8000  (리포 루트에서)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core import get_logger, settings
from ..core import cache, db
from .routes_chart import router as chart_router
from .routes_company import router as company_router
from .routes_score import router as score_router
from .routes_watchlist import router as watchlist_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = settings.missing_keys()
    if missing:
        log.warning("환경변수 미설정", keys=missing)
    log.info("worker api 기동", db=db.ping(), redis=cache.ping())
    yield
    log.info("worker api 종료")


app = FastAPI(title="InvestScope API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(score_router)
app.include_router(watchlist_router)
app.include_router(chart_router)
app.include_router(company_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "db": db.ping(),
        "redis": cache.ping(),
        "missing_env": settings.missing_keys(),
    }
