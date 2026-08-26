"""FastAPI 엔트리포인트.

실행: uvicorn apps.worker.api.main:app --reload --port 8000  (리포 루트에서)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core import get_logger, settings
from ..core import cache, db
from ..ingestion.kis_client import KISSettings
from ..streaming.chart_runtime import RealtimeChartRuntime
from .routes_chart import router as chart_router
from .routes_company import router as company_router
from .routes_score import router as score_router
from .routes_watchlist import router as watchlist_router
from .routes_watchlist import register_on_add, register_on_remove

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = settings.missing_keys()
    if missing:
        log.warning("환경변수 미설정", keys=missing)
    log.info("worker api 기동", db=db.ping(), redis=cache.ping())
    runtime: RealtimeChartRuntime | None = None
    if settings.kis_app_key and settings.kis_app_secret:
        runtime = RealtimeChartRuntime(
            KISSettings(
                app_key=settings.kis_app_key,
                app_secret=settings.kis_app_secret,
                is_mock=settings.kis_is_mock,
            ),
            max_subscriptions=settings.max_watchlist_slots,
        )
        await runtime.start()
        app.state.chart_runtime = runtime
        register_on_add(runtime.subscribe_from_watchlist)
        register_on_remove(runtime.unsubscribe_from_watchlist)
        try:
            rows = db.fetch_all(
                """
                SELECT DISTINCT c.stock_code
                FROM user_watchlist w
                JOIN dim_company c ON c.corp_code = w.corp_code
                WHERE c.stock_code IS NOT NULL
                """
            )
            for row in rows:
                await runtime.ensure_subscription(row["stock_code"])
        except Exception:
            log.warning("관심종목 초기 KIS 구독을 건너뜁니다", exc_info=True)
    else:
        log.warning("KIS 환경변수가 없어 실시간 차트 수신을 시작하지 않습니다")
    try:
        yield
    finally:
        if runtime is not None:
            await runtime.stop()
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
